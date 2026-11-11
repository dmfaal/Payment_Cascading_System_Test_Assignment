from typing import Literal, Protocol

from pydantic import BaseModel, Field


class PaymentRequest(BaseModel):
    amount_minor: int = Field(gt=0, strict=True)
    currency: str = Field(pattern=r"^[a-z]{3}$")
    idempotency_key: str = Field(min_length=1, max_length=255)
    payment_method: str = "pm_card_visa"


class ProviderResult(BaseModel):
    provider: str
    status: Literal["succeeded", "failed", "unavailable", "unknown"]
    payment_id: str | None = None
    reason: str | None = None


class PaymentProvider(Protocol):
    async def pay(self, payment: PaymentRequest) -> ProviderResult:
        """Only unavailable guarantees no payment was attempted and permits fallback."""
        ...
