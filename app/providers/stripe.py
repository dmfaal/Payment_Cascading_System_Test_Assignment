"""Minimal Stripe Sandbox client. HTTP errors and timeouts propagate to the caller."""

from types import TracebackType

import httpx
from pydantic import BaseModel

from app.config import Settings
from app.providers.base import PaymentRequest, ProviderResult


class PaymentIntent(BaseModel):
    id: str
    status: str
    amount: int
    currency: str


class StripeClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url="https://api.stripe.com/v1/",
            auth=httpx.BasicAuth(settings.stripe_api_key.get_secret_value(), ""),
            headers={"Stripe-Version": "2026-10-28.endive"},
            timeout=httpx.Timeout(10.0, connect=5.0),
            transport=transport,
        )

    async def __aenter__(self) -> "StripeClient":
        await self._http.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._http.__aexit__(exc_type, exc_value, traceback)

    async def create_payment(
        self,
        *,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
        payment_method: str = "pm_card_visa",
    ) -> PaymentIntent:
        """Create and confirm a test card payment; amounts use minor currency units.

        Keep the same idempotency key for the same operation. A timeout is an
        unknown outcome, not proof of a declined payment. No automatic retries.
        """
        if (
            isinstance(amount_minor, bool)
            or not isinstance(amount_minor, int)
            or amount_minor <= 0
        ):
            raise ValueError("amount_minor must be a positive integer")
        if not currency.isascii() or not currency.isalpha() or len(currency) != 3:
            raise ValueError("currency must be a three-letter currency code")
        if not idempotency_key.strip() or len(idempotency_key) > 255:
            raise ValueError("idempotency_key must contain 1 to 255 characters")

        response = await self._http.post(
            "payment_intents",
            headers={"Idempotency-Key": idempotency_key},
            data={
                "amount": str(amount_minor),
                "currency": currency.lower(),
                "payment_method": payment_method,
                "automatic_payment_methods[enabled]": "true",
                "automatic_payment_methods[allow_redirects]": "never",
                "confirm": "true",
            },
        )
        response.raise_for_status()
        return PaymentIntent.model_validate(response.json())

    async def get_payment(self, payment_intent_id: str) -> PaymentIntent:
        """Retrieve the current provider status without attempting payment again."""
        if (
            not payment_intent_id.startswith("pi_")
            or not payment_intent_id.isascii()
            or not payment_intent_id.replace("_", "").isalnum()
        ):
            raise ValueError("Expected a Stripe PaymentIntent ID (pi_...)")
        response = await self._http.get(f"payment_intents/{payment_intent_id}")
        response.raise_for_status()
        return PaymentIntent.model_validate(response.json())


class StripeProvider:
    """Translate Stripe responses into conservative cascade decisions."""

    def __init__(self, client: StripeClient) -> None:
        self.client = client

    async def pay(self, payment: PaymentRequest) -> ProviderResult:
        try:
            intent = await self.client.create_payment(**payment.model_dump())
        except httpx.HTTPStatusError as exc:
            # Even a definite card decline does not permit automatic rerouting.
            status = "failed" if exc.response.status_code in (400, 401, 402, 403, 404) else "unknown"
            return ProviderResult(
                provider="stripe", status=status,
                reason=f"Stripe HTTP {exc.response.status_code}; cascade stopped",
            )
        except (httpx.RequestError, ValueError):
            return ProviderResult(
                provider="stripe", status="unknown",
                reason="Network error or invalid response; reconcile with Stripe",
            )
        return ProviderResult(
            provider="stripe",
            status="succeeded" if intent.status == "succeeded" else "unknown",
            payment_id=intent.id,
            reason=f"Stripe status: {intent.status}",
        )

