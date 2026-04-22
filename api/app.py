from __future__ import annotations

import os
import uuid

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from adapters.adk_agent import AgentRunner
from core.repository import get_repository

load_dotenv()
logger = structlog.get_logger()

app = FastAPI(
    title="Send Money Agent API",
    version="1.0.0",
    description="Stateful Send Money Agent built with FastAPI + Google ADK",
)

# -------------------------
# Dependencies
# -------------------------
repository = get_repository(backend=os.getenv("STATE_BACKEND", "memory"))
runner = AgentRunner(
    repository=repository
)


# -------------------------
# Request / Response Schemas
# -------------------------
class ChatRequest(BaseModel):
    session_id: str | None = Field(None, description="Auto-generated if not provided")
    message: str = Field(..., min_length=1, description="User message")


class ChatResponse(BaseModel):
    session_id: str
    response: str
    state: dict
    done: bool


class HealthResponse(BaseModel):
    status: str
    model: str


class ResetResponse(BaseModel):
    success: bool
    message: str


# -------------------------
# Middleware
# -------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info("api.request.start", method=request.method, path=request.url.path)
    response = await call_next(request)
    logger.info(
        "api.request.end",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
    )
    return response


# -------------------------
# Routes
# -------------------------
@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        model=os.getenv("MODEL", "gemini-2.0-flash"),
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    session_id = payload.session_id or str(uuid.uuid4())

    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        result = await runner.run_async(
            session_id=session_id,
            message=payload.message,
        )
        return ChatResponse(
            session_id=session_id,
            response=result["response"],
            state=result["state"],
            done=result.get("done", False),
        )
    except Exception as exc:
        logger.exception("api.chat.error", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Internal server error.") from exc


@app.delete("/chat/{session_id}", response_model=ResetResponse)
async def reset_chat(session_id: str) -> ResetResponse:
    try:
        runner.reset(session_id)
        logger.info("api.chat.reset", session_id=session_id)
        return ResetResponse(
            success=True,
            message=f"Session '{session_id}' reset successfully.",
        )
    except Exception as exc:
        logger.exception("api.chat.reset.error", session_id=session_id, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail="Internal server error while resetting session.",
        ) from exc
        
        
@app.get("/state/{session_id}")
def get_state(session_id: str):
    state = repository.get(session_id)

    return {
        "session_id": session_id,
        "state": state.model_dump(),
        "is_complete": state.is_complete(),
        "missing_fields": state.missing_fields(),
    }
