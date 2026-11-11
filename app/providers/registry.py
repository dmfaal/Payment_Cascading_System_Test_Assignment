"""Small factory; mock simulates rejection before processing."""

from app.providers.base import PaymentProvider
from app.providers.mock import MockProvider
from app.providers.stripe import StripeClient, StripeProvider


class SimpleProviderRegistry:
    names = ("stripe", "mock")

    def __init__(self, client: StripeClient) -> None:
        self.client = client

    def get(self, name: str) -> PaymentProvider:
        if name == "stripe":
            return StripeProvider(self.client)
        if name == "mock":
            return MockProvider(name="mock", outcome="unavailable")
        raise ValueError(f"Unknown provider: {name}")
