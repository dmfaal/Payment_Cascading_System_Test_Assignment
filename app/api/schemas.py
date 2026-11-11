"""Pydantic schemas for the Payment API."""

from pydantic import BaseModel, Field


class PaymentCreateRequest(BaseModel):
    """Request body for creating a payment."""

    amount: int = Field(gt=0, strict=True, description="Payment amount in minor units (cents)")
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    payment_method: str = Field(default="pm_card_visa", description="Stripe test PaymentMethod ID")
    idempotency_key: str = Field(min_length=1, max_length=255, pattern=r"\S")
    providers: list[str] = Field(default_factory=lambda: ["stripe"], min_length=1)


class PaymentResponse(BaseModel):
    """Response for a payment operation."""

    id: str
    status: str
    provider: str | None = None
    attempts: list[dict] = Field(default_factory=list)


class PaymentStatusResponse(BaseModel):
    """Response for payment status lookup."""

    id: str
    status: str
    provider: str | None = None
    result: str | None = None
