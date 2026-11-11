from typing import Literal

from app.providers.base import PaymentRequest, ProviderResult


class MockProvider:
    """Demo stub: returns a configured outcome; never moves money or calls an API."""

    def __init__(
        self,
        name: str,
        outcome: Literal["succeeded", "failed", "unavailable", "unknown"],
    ) -> None:
        self.name = name
        self.outcome = outcome

    async def pay(self, payment: PaymentRequest) -> ProviderResult:
        return ProviderResult(
            provider=self.name,
            status=self.outcome,
            reason="Simulated outcome; unavailable means rejected before processing",
        )
