"""Small cascade demo; only Stripe makes real HTTP calls, using sandbox keys."""

import argparse
import asyncio
import logging

from app.config import get_settings
from app.providers.base import PaymentRequest
from app.providers.mock import MockProvider
from app.providers.stripe import StripeClient, StripeProvider
from app.services.payments import cascade_payment


async def main(scenario: str, key: str, payment_method: str) -> None:
    payment = PaymentRequest(
        amount_minor=100, currency="eur",
        idempotency_key=key, payment_method=payment_method,
    )
    async with StripeClient(get_settings()) as client:
        stripe = StripeProvider(client)
        routes = {
            "fallback": [MockProvider("mock-primary", "unavailable"), stripe],
            "stripe": [stripe, MockProvider("mock-backup", "succeeded")],
            "unknown": [MockProvider("mock-primary", "unknown"), stripe],
            "exhausted": [
                MockProvider("mock-primary", "unavailable"),
                MockProvider("mock-backup", "unavailable"),
            ],
        }
        result = await cascade_payment(payment, routes[scenario])
        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Payment cascade demo: 1 EUR in sandbox")
    parser.add_argument("--scenario", choices=("fallback", "stripe", "unknown", "exhausted"), required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--payment-method", default="pm_card_visa")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(main(args.scenario, args.idempotency_key, args.payment_method))
