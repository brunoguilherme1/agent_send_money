from __future__ import annotations

from typing import Optional, Literal, List
from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

SUPPORTED_COUNTRIES: dict[str, str] = {
    "MX": "Mexico",
    "CO": "Colombia",
    "BR": "Brazil",
    "AR": "Argentina",
    "PE": "Peru",
    "CL": "Chile",
    "EC": "Ecuador",
    "US": "United States"
}

COUNTRY_NAME_TO_CODE: dict[str, str] = {
    name.strip().lower(): code
    for code, name in SUPPORTED_COUNTRIES.items()
}

SUPPORTED_CURRENCIES: set[str] = {"USD", "EUR", "BRL", "MXN", "COP"}

SUPPORTED_METHODS: set[str] = {
    "bank_deposit",
    "cash_pickup",
    "mobile_wallet",
    "bank_transfer",
}

MAX_AMOUNT: float = 10_000.0

# Maps country code → default currency for next_field() suggestions.
COUNTRY_DEFAULT_CURRENCY: dict[str, str] = {
    "BR": "BRL",
    "MX": "MXN",
    "CO": "COP",
    "US": "USD",
    "ES": "EUR",
    # AR, PE, CL, EC use currencies outside the supported set — ask open-endedly.
}

# Canonical fallback questions per field.
FIELD_QUESTIONS: dict[str, str] = {
    "country": "Which country are you sending to?",
    "recipient_name": "Who are you sending it to? (full name)",
    "amount": "How much would you like to send?",
    "currency": "Which currency would you like to use?",
    "delivery_method": "How should the recipient receive it? (bank_transfer, cash_pickup, mobile_wallet, bank_deposit)",
}

TransferStatus = Literal["collecting", "confirming", "done", "cancelled"]


# ---------------------------------------------------------------------------
# Clarification queue item
# ---------------------------------------------------------------------------

class ClarificationItem(BaseModel):
    field: Optional[str] = None      # None when the field itself is ambiguous (e.g. "Santiago")
    tentative: Optional[str] = None  # Best guess, or None when no guess is possible
    question: str                    # Question to surface to the user


# ---------------------------------------------------------------------------
# TransferState
# ---------------------------------------------------------------------------

class TransferState(BaseModel):
    country: Optional[str] = None
    recipient_name: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    delivery_method: Optional[str] = None
    status: TransferStatus = "collecting"
    pending_clarifications: List[ClarificationItem] = []

    # -- Validators ----------------------------------------------------------

    @field_validator("country")
    @classmethod
    def validate_country(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        raw = v.strip()
        upper = raw.upper()
        if upper in SUPPORTED_COUNTRIES:
            return upper
        code = COUNTRY_NAME_TO_CODE.get(raw.lower())
        if code:
            return code
        supported_names = ", ".join(SUPPORTED_COUNTRIES.values())
        raise ValueError(
            f"'{v}' is not a supported country. "
            f"Supported countries: {supported_names}."
        )

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if v <= 0:
            raise ValueError("Amount must be greater than zero.")
        if v > MAX_AMOUNT:
            raise ValueError(
                f"Amount {v} exceeds the maximum allowed transfer of {MAX_AMOUNT:,.0f}."
            )
        return round(v, 2)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = v.strip().upper()
        if normalized not in SUPPORTED_CURRENCIES:
            raise ValueError(
                f"'{v}' is not a supported currency. "
                f"Supported currencies: {', '.join(sorted(SUPPORTED_CURRENCIES))}."
            )
        return normalized

    @field_validator("delivery_method")
    @classmethod
    def validate_delivery_method(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = v.strip().lower().replace(" ", "_")
        if normalized not in SUPPORTED_METHODS:
            raise ValueError(
                f"'{v}' is not a supported delivery method. "
                f"Supported methods: {', '.join(sorted(SUPPORTED_METHODS))}."
            )
        return normalized

    @field_validator("recipient_name")
    @classmethod
    def validate_recipient_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        stripped = v.strip()
        if len(stripped) < 2:
            raise ValueError("Recipient name is too short.")
        if stripped.isdigit():
            raise ValueError("Recipient name cannot be numeric.")
        if len(v.split()) <=1:
            raise ValueError("Recipient name must include at least one surname")
        return stripped

    # -- State helpers -------------------------------------------------------

    def is_complete(self) -> bool:
        return all([
            self.country,
            self.recipient_name,
            self.amount is not None,
            self.currency,
            self.delivery_method,
        ])

    def missing_fields(self) -> List[str]:
        order = ["country", "recipient_name", "amount", "currency", "delivery_method"]
        return [f for f in order if getattr(self, f) is None]

    def safe_update(self, updates: dict) -> "TransferState":
        """Return a new TransferState with fields updated. Raises on invalid values."""
        data = self.model_dump()
        data.update(updates)
        return TransferState(**data)

    def advance_status(self) -> None:
        """Mutate status in place based on completeness."""
        if self.is_complete():
            self.status = "confirming"
        else:
            self.status = "collecting"

    def country_name(self) -> Optional[str]:
        if not self.country:
            return None
        return SUPPORTED_COUNTRIES.get(self.country, self.country)

    def to_summary(self) -> str:
        if not self.is_complete():
            return "Transfer is incomplete."
        return (
            f"Sending {self.amount:,.2f} {self.currency} "
            f"to {self.recipient_name} "
            f"in {self.country_name()} "
            f"via {self.delivery_method}."
        )


    def with_clarifications(self, items: List[ClarificationItem]) -> "TransferState":
        """Return a new state with the clarification queue replaced."""
        data = self.model_dump()
        data["pending_clarifications"] = [i.model_dump() for i in items]
        return TransferState(**data)

    def pop_clarification(self) -> tuple[Optional[ClarificationItem], "TransferState"]:
        """Remove and return the first pending clarification.
        Returns (item, new_state). Item is None if queue is empty.
        """
        if not self.pending_clarifications:
            return None, self
        first = self.pending_clarifications[0]
        rest = self.pending_clarifications[1:]
        new_state = self.with_clarifications(rest)
        return first, new_state