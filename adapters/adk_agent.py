from __future__ import annotations

import os
import structlog
import asyncio
from typing import Any
from dotenv import load_dotenv

from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types as genai_types

from core.state import TransferState
from core.prompt import build_system_prompt
from core.tools import (
    update_state as _update_state,
    validate_transfer as _validate_transfer,
    submit_transfer as _submit_transfer,
    get_supported_options as _get_supported_options,
    clarify as _clarify,
    resolve_clarification as _resolve_clarification,
    next_field as _next_field,
)
from core.repository import StateRepository

import time
import json
from datetime import datetime

load_dotenv()
logger = structlog.get_logger()

APP_NAME = "send_money_agent"
MODEL = os.getenv("MODEL", "gemini-2.5-flash")


class AgentRunner:
    def __init__(self, repository: StateRepository):
        self.repository = repository
        self.session_service = InMemorySessionService()

    async def _ensure_session(self, session_id: str) -> None:
        existing = await self.session_service.get_session(
            app_name=APP_NAME,
            user_id=session_id,
            session_id=session_id,
        )
        if existing is None:
            await self.session_service.create_session(
                app_name=APP_NAME,
                user_id=session_id,
                session_id=session_id,
            )

    def _build_agent(self, state: TransferState):
        current_state = state
        latest_submit_result: dict[str, Any] | None = None

        # ── Tool names must match exactly what the prompt instructs the model to call.
        # ADK uses the Python function's __name__ as the tool name exposed to the model.
        # Do NOT add _tool suffix here — it causes "Tool 'clarify' not found" errors.

        resolve_no_pending_count = 0  # circuit breaker for the resolve loop bug

        def update_state(field: str, value: Any):
            nonlocal current_state
            current_state, result = _update_state(current_state, field, value)
            return result

        def validate_transfer():
            return _validate_transfer(current_state)

        def submit_transfer():
            nonlocal current_state, latest_submit_result
            result = _submit_transfer(current_state)
            latest_submit_result = result
            if result.get("success"):
                current_state = current_state.safe_update({"status": "done"})
            return result

        def get_supported_options():
            return _get_supported_options()

        
        def clarify(items: list[dict]):
            """Queue one or more unsure values. Asks the first question, stores the rest."""
            nonlocal current_state
            current_state, result = _clarify(current_state, items)
            return result

        def resolve_clarification(confirmed_value: str | None):
            """Resolve the current pending clarification with the user's answer."""
            nonlocal current_state, resolve_no_pending_count
            current_state, result = _resolve_clarification(current_state, confirmed_value)

            # Circuit breaker: if there's nothing to resolve and the model keeps retrying,
            # raise after 2 attempts so the turn ends instead of looping until timeout.
            if result.get("error") == "no_pending_clarifications":
                resolve_no_pending_count += 1
                if resolve_no_pending_count >= 2:
                    raise RuntimeError(
                        "Agent stuck: resolve_clarification called with no pending items. "
                        "Call next_field() instead."
                    )
            else:
                resolve_no_pending_count = 0  # reset on success

            return result

        def next_field():
            """Return the next missing field and a suggested question."""
            return _next_field(current_state)

        agent = LlmAgent(
            name="send_money_agent",
            model=MODEL,
            instruction=build_system_prompt(current_state),
            tools=[
                update_state,
                validate_transfer,
                submit_transfer,
                get_supported_options,
                clarify,
                resolve_clarification,
                next_field,
            ],
        )

        return agent, lambda: current_state, lambda: latest_submit_result

    # ── public interface ────────────────────────────────────────────────────

    async def run_async(self, session_id: str, message: str) -> dict:
        return await self.run(session_id=session_id, user_message=message)

    async def run(self, session_id: str, user_message: str) -> dict:
        start_time = time.time()
        state = self.repository.get(session_id)

        logger.info(
            "agent.turn.start",
            session_id=session_id,
            message=user_message,
            status=state.status,
        )

        # ── hard cancel keywords handled before touching the model
        if user_message.strip().lower() in {"cancel", "start over", "restart"}:
            self.repository.delete(session_id)
            logger.info("agent.cancelled", session_id=session_id)
            return {
                "response": "Transfer cancelled. Start over whenever you're ready.",
                "state": TransferState().model_dump(),
                "done": False,
                "tools_used": [],
            }

        agent, get_state, get_submit_result = self._build_agent(state)

        await self._ensure_session(session_id)

        runner = Runner(
            agent=agent,
            app_name=APP_NAME,
            session_service=self.session_service,
        )

        content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=user_message)],
        )

        # ── run with retry on 503/429 and a hard exit on the resolve loop bug
        reply_text = ""
        tools_used: list[dict] = []
        max_retries = 4
        delay = 5  # seconds, doubles each attempt: 5 → 10 → 20 → 40
        for attempt in range(max_retries):
            try:
                reply_text = ""
                tools_used = []

                async for event in runner.run_async(
                    user_id=session_id,
                    session_id=session_id,
                    new_message=content,
                ):
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if getattr(part, "text", None):
                                reply_text += part.text
                            if getattr(part, "function_call", None):
                                tools_used.append({
                                    "tool": part.function_call.name,
                                    "args": dict(part.function_call.args),
                                })

                break  # success — exit retry loop

            except RuntimeError as exc:
                # Circuit breaker fired inside resolve_clarification wrapper
                if "stuck" in str(exc):
                    logger.warning(
                        "agent.loop.broken",
                        session_id=session_id,
                        reason=str(exc),
                    )
                    reply_text = "I didn't catch that — could you rephrase?"
                    break
                raise

            except Exception as exc:
                err_str = str(exc)
                is_retryable = any(token in err_str for token in [
                    "503", "UNAVAILABLE",
                    "429", "RESOURCE_EXHAUSTED",
                ])

                if is_retryable and attempt < max_retries - 1:
                    logger.warning(
                        "agent.retrying",
                        session_id=session_id,
                        attempt=attempt + 1,
                        wait_seconds=delay,
                        error=err_str[:200],
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    logger.error(
                        "agent.failed",
                        session_id=session_id,
                        attempt=attempt + 1,
                        error=err_str[:200],
                    )
                    raise

        new_state = get_state()
        submit_result = get_submit_result()

        self.repository.save(session_id, new_state)

        # ── transfer just completed
        if submit_result and submit_result.get("success"):
            logger.info("agent.turn.end", session_id=session_id, status="done", done=True)
            return {
                "response": submit_result.get("message", ""),
                "state": new_state.model_dump(),
                "done": True,
                "tools_used": tools_used,
            }

        done = new_state.status == "done"

        logger.info(
            "agent.turn.end",
            session_id=session_id,
            status=new_state.status,
            done=done,
        )
        
        latency = (time.time() - start_time) * 1000
        tokens = len(reply_text.split())  # simple approximation
        cost = tokens * 0.001

        log = {
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "latency_ms": latency,
            "tokens": tokens,
            "cost": cost,
            "status": "completed" if done else "in_progress",
            "tools_used": tools_used,
            "error": False
        }

        with open("logs.json", "a") as f:
            f.write(json.dumps(log) + "\n")

        return {
            "response": reply_text.strip() or "I didn't catch that — could you rephrase?",
            "state": new_state.model_dump(),
            "done": done,
            "tools_used": tools_used,
        }

    def reset(self, session_id: str) -> None:
        self.repository.delete(session_id)
        logger.info("agent.session.reset", session_id=session_id)
        
        
    
    
