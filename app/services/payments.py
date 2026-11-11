import logging
from collections.abc import Sequence

from pydantic import BaseModel

from app.providers.base import PaymentProvider, PaymentRequest, ProviderResult


logger = logging.getLogger(__name__)


class CascadeResult(BaseModel):
    status: str
    attempts: list[ProviderResult]


async def cascade_payment(
    payment: PaymentRequest, providers: Sequence[PaymentProvider]
) -> CascadeResult:
    if not providers:
        raise ValueError("At least one provider is required")
    attempts = []
    for provider in providers:
        result = await provider.pay(payment)
        attempts.append(result)
        logger.info("Payment attempt: provider=%s status=%s", result.provider, result.status)
        if result.status != "unavailable":
            return CascadeResult(status=result.status, attempts=attempts)
    return CascadeResult(status="failed", attempts=attempts)
