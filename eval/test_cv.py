from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog

from adapters.adk_agent import AgentRunner
from core.repository import InMemoryRepository

logger = structlog.get_logger()

# ── paths ──────────────────────────────────────────────────────────────────────
TESTS_DIR = Path(__file__).parent
CASES_FILE = TESTS_DIR / "data_tests" / "conversation_test.json"
RESULTS_DIR = TESTS_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── config ─────────────────────────────────────────────────────────────────────
COST_PER_1K_TOKENS = 0.002  # relative cost (approximation)


# ──────────────────────────────────────────────────────────────────────────────
# Single test runner
# ──────────────────────────────────────────────────────────────────────────────
async def run_test_case(runner: AgentRunner, test: dict) -> dict:
    test_id = test["test_id"]
    turns_in = test["input"]["turns"]
    session_id = str(uuid.uuid4())

    logger.info("runner.test.start", test_id=test_id, session_id=session_id)

    trace = []
    total_latency_ms = 0.0
    total_tokens = 0.0

    for i, turn in enumerate(turns_in, start=1):
        user_message = turn["user"]

        t0 = time.perf_counter()

        try:
            result = await runner.run_async(
                session_id=session_id,
                message=user_message,
            )
            success = True
            error = None
        except Exception as exc:
            logger.exception("runner.turn.error", test_id=test_id, turn=i, error=str(exc))
            result = {
                "response": "",
                "state": {},
                "done": False,
                "tools_used": [],
            }
            success = False
            error = str(exc)

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        total_latency_ms += latency_ms

        response_text = result.get("response", "")

        # ✅ TOKEN ESTIMATION (WORD-BASED)
        tokens_used = len(response_text.split())
        total_tokens += tokens_used

        trace.append({
            "turn": i,
            "user": user_message,
            "response": response_text,
            "tools_used": result.get("tools_used", []),
            "state": result.get("state", {}),
            "done": result.get("done", False),
            "latency_ms": latency_ms,
            "token_usage": tokens_used,
            "success": success,
            "error": error,
        })

        logger.info(
            "runner.turn.done",
            test_id=test_id,
            turn=i,
            latency_ms=latency_ms,
            done=result.get("done", False),
        )

        if result.get("done", False):
            break

    final_state = trace[-1]["state"] if trace else {}
    final_done = trace[-1]["done"] if trace else False

    # ✅ SYSTEM METRICS
    system_metrics = {
        "latency_ms": round(total_latency_ms, 2),
        "token_usage": total_tokens,
        "cost": float((total_tokens / 1000) * COST_PER_1K_TOKENS),
    }

    record = {
        "test_id": test_id,
        "trace": trace,
        "final": {
            "state": final_state,
            "done": final_done,
        },
        "system": system_metrics,
    }

    logger.info(
        "runner.test.done",
        test_id=test_id,
        total_turns=len(trace),
        latency_ms=system_metrics["latency_ms"],
        done=final_done,
    )

    return record


# ──────────────────────────────────────────────────────────────────────────────
# Suite runner
# ──────────────────────────────────────────────────────────────────────────────
async def run_suite(
    test_cases: list[dict],
    filter_id: str | None = None,
    filter_category: str | None = None,
) -> list[dict]:

    if filter_id:
        test_cases = [t for t in test_cases if t["test_id"] == filter_id]

    if filter_category:
        test_cases = [t for t in test_cases if t.get("category") == filter_category]

    if not test_cases:
        logger.warning("runner.suite.empty")
        return []

    logger.info("runner.suite.start", total_tests=len(test_cases))

    results = []

    for idx, test in enumerate(test_cases):
        repository = InMemoryRepository()
        runner = AgentRunner(repository=repository)

        result = await run_test_case(runner, test)
        results.append(result)

        # small delay between tests
        if idx < len(test_cases) - 1:
            print(f"Sleeping 1 second after {test['test_id']}...")
            await asyncio.sleep(1)

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Save + summary
# ──────────────────────────────────────────────────────────────────────────────
def save_results(results: list[dict]) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_file = RESULTS_DIR / f"run_{timestamp}.json"

    output = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_tests": len(results),
        "results": results,
    }

    output_file.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("runner.results.saved", path=str(output_file))
    return output_file


def print_summary(results: list[dict]) -> None:
    print("\n" + "=" * 80)
    print(f"{'TEST ID':<35} {'TURNS':>5} {'LATENCY':>12} {'TOKENS':>10} {'DONE':>8}")
    print("=" * 80)

    for r in results:
        print(
            f"{r['test_id']:<35} "
            f"{len(r['trace']):>5} "
            f"{r['system']['latency_ms']:>11.0f}ms "
            f"{r['system']['token_usage']:>10.0f} "
            f"{str(r['final']['done']):>8}"
        )

    total_latency = sum(r["system"]["latency_ms"] for r in results)
    total_tokens = sum(r["system"]["token_usage"] for r in results)

    print("=" * 80)
    print(f"Total tests: {len(results)} | Total time: {total_latency:.0f}ms | Total tokens: {total_tokens:.0f}")
    print("=" * 80 + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────
async def main(filter_id: str | None, filter_category: str | None) -> None:
    if not CASES_FILE.exists():
        raise FileNotFoundError(f"Test cases file not found: {CASES_FILE}")

    raw = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    test_cases = raw.get("test_suite", raw)

    logger.info("runner.loaded", total_cases=len(test_cases))

    results = await run_suite(
        test_cases=test_cases,
        filter_id=filter_id,
        filter_category=filter_category,
    )

    if not results:
        print("No tests matched the filter.")
        return

    output_file = save_results(results)
    print_summary(results)
    print(f"Results saved to: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run send money agent test suite")
    parser.add_argument("--test-id")
    parser.add_argument("--category")
    args = parser.parse_args()

    asyncio.run(main(filter_id=args.test_id, filter_category=args.category))