from __future__ import annotations

import structlog
from typing import Any, Optional, List

from core.state import (
    TransferState,
    ClarificationItem,
    SUPPORTED_COUNTRIES,
    SUPPORTED_CURRENCIES,
    SUPPORTED_METHODS,
    COUNTRY_DEFAULT_CURRENCY,
    FIELD_QUESTIONS,
)

logger = structlog.get_logger()

ALLOWED_FIELDS = {
    "country",
    "recipient_name",
    "amount",
    "currency",
    "delivery_method",
}


# ---------------------------------------------------------------------------
# Tool: update_state
# ---------------------------------------------------------------------------

def update_state(
    state: TransferState,
    field: str,
    value: Any,
) -> tuple[TransferState, dict]:
    """
    Update a single confident field. One call per field.
    Validation is handled entirely by Pydantic validators in TransferState.

    Returns (new_state, result):
      success=True  → { success, field, normalized_value }
      success=False → { success, error }
    """
    if field not in ALLOWED_FIELDS:
        logger.warning("update_state.invalid_field", field=field)
        return state, {
            "success": False,
            "error": f"'{field}' is not a valid field. Allowed: {', '.join(sorted(ALLOWED_FIELDS))}.",
        }

    try:
        new_state = state.safe_update({field: value})
        new_state.advance_status()
        normalized = getattr(new_state, field)
        logger.info("update_state.success", field=field, raw=value, normalized=normalized)
        return new_state, {
            "success": True,
            "field": field,
            "normalized_value": normalized,
        }

    except Exception as exc:
        logger.warning("update_state.failed", field=field, value=value, error=str(exc))
        return state, {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: clarify
# ---------------------------------------------------------------------------

def clarify(
    state: TransferState,
    items: List[dict],
) -> tuple[TransferState, dict]:
    """
    Queue one or more ambiguous values and return the first question to ask.

    Each item: { field, tentative, question }
      - field:     the field name, or null if the field itself is ambiguous
      - tentative: best guess value, or null if no guess is possible
      - question:  the question to surface to the user

    The first item's question is returned immediately.
    Remaining items are stored in state.pending_clarifications for future turns.

    Returns (new_state, result):
      { question, field, tentative, remaining_count }
    """
    if not items:
        logger.warning("clarify.empty_items")
        return state, {"error": "No clarification items provided."}

    parsed = [ClarificationItem(**i) for i in items]
    first = parsed[0]
    rest  = parsed[1:]

    # Store ALL items — index 0 is the one currently being asked.
    # resolve_clarification will pop index 0 when the user answers.
    new_state = state.with_clarifications(parsed)

    logger.info(
        "clarify.queued",
        asking=first.question,
        queued=[i.field for i in rest],
    )

    return new_state, {
        "question":         first.question,
        "field":            first.field,
        "tentative":        first.tentative,
        "remaining_count":  len(rest),
    }


# ---------------------------------------------------------------------------
# Tool: resolve_clarification
# ---------------------------------------------------------------------------

def resolve_clarification(
    state: TransferState,
    confirmed_value: Optional[str],
) -> tuple[TransferState, dict]:
    """
    Resolve the first pending clarification.

    Call when the user has answered the current clarification question.
    - confirmed_value: the confirmed value, or None if the user rejected the tentative.

    Pops the first item from the queue. If confirmed_value is provided and the
    item has a known field, immediately calls update_state to persist it.

    Returns (new_state, result):
      {
        resolved: { field, confirmed_value },
        next_clarification: { question, field, tentative } | None,
      }
    """
    item, new_state = state.pop_clarification()

    if item is None:
        logger.warning("resolve_clarification.no_pending")
        return state, {
            "error": "no_pending_clarifications",
            "instruction": "Do NOT call resolve_clarification again. Call next_field() instead."
        }

    # If we know the field and have a confirmed value, persist it
    if item.field and confirmed_value is not None:

        # 🔥 GUARD: block semantic / non-structured answers
        invalid_phrases = [
            "part of the recipient",
            "recipient's name",
            "part of the name",
            "name",
            "not sure",
            "i think",
        ]

        value_lower = confirmed_value.lower()

        if any(phrase in value_lower for phrase in invalid_phrases):
            logger.warning(
                "resolve_clarification.invalid_semantic_answer",
                value=confirmed_value
            )

            # 🔁 re-queue the same clarification
            new_items = [item] + new_state.pending_clarifications
            new_state = new_state.with_clarifications(new_items)

            return new_state, {
                "error": "invalid_answer",
                "message": item.question
            }

        new_state, update_result = update_state(new_state, item.field, confirmed_value)

        if not update_result["success"]:
            logger.warning(
                "resolve_clarification.update_failed",
                error=update_result["error"]
            )

            new_items = [item] + new_state.pending_clarifications
            new_state = new_state.with_clarifications(new_items)

            return new_state, {
                "error": "validation_failed",
                "message": item.question
            }

    logger.info(
        "resolve_clarification.resolved",
        field=item.field,
        confirmed=confirmed_value,
    )

    # Surface next pending clarification if any
    next_item = new_state.pending_clarifications[0] if new_state.pending_clarifications else None

    return new_state, {
        "resolved": {
            "field":           item.field,
            "confirmed_value": confirmed_value,
        },
        "next_clarification": {
            "question":  next_item.question,
            "field":     next_item.field,
            "tentative": next_item.tentative,
        } if next_item else None,
    }


# ---------------------------------------------------------------------------
# Tool: next_field
# ---------------------------------------------------------------------------

def next_field(state: TransferState) -> dict:
    """
    Return the next missing field and a context-aware suggested question.
    Call only when no pending clarifications and clarify() was not called this turn.

    Returns:
      { done: False, field, suggestion }  — ask this
      { done: True }                       — all fields set, ready to validate
    """
    missing = state.missing_fields()

    if not missing:
        logger.info("next_field.done")
        return {"done": True}

    field      = missing[0]
    suggestion = _build_suggestion(field, state)

    logger.info("next_field.suggest", field=field, suggestion=suggestion)
    return {"done": False, "field": field, "suggestion": suggestion}


def _build_suggestion(field: str, state: TransferState) -> str:
    if field == "currency" and state.country in COUNTRY_DEFAULT_CURRENCY:
        default = COUNTRY_DEFAULT_CURRENCY[state.country]
        return (
            f"Since you're sending to {state.country_name()}, "
            f"shall I use {default}? Or would you prefer a different currency?"
        )
    if field == "delivery_method":
        return f"How should the recipient receive it? ({', '.join(sorted(SUPPORTED_METHODS))})"
    return FIELD_QUESTIONS[field]


# ---------------------------------------------------------------------------
# Tool: validate_transfer
# ---------------------------------------------------------------------------

def validate_transfer(state: TransferState) -> dict:
    """
    Check completeness. Call only when state.missing_fields() is empty.

    Returns:
      { valid: True,  missing: [],    summary: str  }
      { valid: False, missing: [...], summary: None }
    """
    missing  = state.missing_fields()
    is_valid = len(missing) == 0
    logger.info("validate_transfer", valid=is_valid, missing=missing)
    return {
        "valid":   is_valid,
        "missing": missing,
        "summary": state.to_summary() if is_valid else None,
    }


# ---------------------------------------------------------------------------
# Tool: submit_transfer
# ---------------------------------------------------------------------------

def submit_transfer(state: TransferState) -> dict:
    """
    Finalize and submit. Call only after explicit user confirmation.
    Re-validates internally as a safety net.

    Returns:
      success=True  → { success, payload, message }
      success=False → { success, error, details }
    """
    validation = validate_transfer(state)

    if not validation["valid"]:
        logger.warning("submit_transfer.blocked", missing=validation["missing"])
        return {
            "success": False,
            "error":   "Transfer is not ready to submit.",
            "details": validation,
        }

    payload = {
        "amount":       state.amount,
        "currency":     state.currency,
        "recipient":    state.recipient_name,
        "country_code": state.country,
        "country_name": state.country_name(),
        "method":       state.delivery_method,
        "status":       "submitted",
    }

    message = (
        f"Transfer of {state.amount:,.2f} {state.currency} "
        f"to {state.recipient_name} in {state.country_name()} submitted successfully!"
    )

    logger.info("submit_transfer.success", payload=payload)
    return {"success": True, "payload": payload, "message": message}


# ---------------------------------------------------------------------------
# Tool: get_supported_options
# ---------------------------------------------------------------------------

def get_supported_options() -> dict:
    """Live list of supported countries, currencies, and methods. Never answer from memory."""
    return {
        "countries":        [{"code": c, "name": n} for c, n in SUPPORTED_COUNTRIES.items()],
        "currencies":       sorted(SUPPORTED_CURRENCIES),
        "delivery_methods": sorted(SUPPORTED_METHODS),
    }
    
    