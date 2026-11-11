"""Run with: python -m app.stripe_demo --idempotency-key demo-order-001"""

import argparse
import asyncio

import httpx

from app.config import get_settings
from app.providers.stripe import StripeClient


async def main(idempotency_key: str, payment_method: str) -> None:
    async with StripeClient(get_settings()) as client:
        try:
            payment = await client.create_payment(
                amount_minor=100,
                currency="eur",
                idempotency_key=idempotency_key,
                payment_method=payment_method,
            )
            print("Created:", payment.model_dump_json())
            payment = await client.get_payment(payment.id)
            print("Retrieved:", payment.model_dump_json())
        except httpx.RequestError:
            raise SystemExit(
                "Network error: outcome may be unknown. "
                "Do not create another payment with a new idempotency key."
            ) from None
        except httpx.HTTPStatusError as exc:
            try:
                error = exc.response.json().get("error", {})
                details = "; ".join(
                    f"{field}: {error[field]}"
                    for field in ("type", "code", "param", "message")
                    if error.get(field)
                )
            except (ValueError, AttributeError, TypeError):
                details = "Stripe returned an unexpected error response."
            request_id = exc.response.headers.get("Request-Id", "unavailable")
            raise SystemExit(
                f"Stripe returned HTTP {exc.response.status_code}.\n"
                f"{details}\nRequest ID: {request_id}\n"
                "No automatic retry was performed."
            ) from None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a 1 EUR Stripe Sandbox payment")
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--payment-method", default="pm_card_visa")
    args = parser.parse_args()
    asyncio.run(main(args.idempotency_key, args.payment_method))
