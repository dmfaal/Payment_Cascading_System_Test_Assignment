import unittest
from unittest.mock import AsyncMock

import httpx

from app.config import Settings
from app.providers.base import PaymentRequest
from app.providers.mock import MockProvider
from app.providers.stripe import StripeClient, StripeProvider
from app.services.payments import cascade_payment


class CascadeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.payment = PaymentRequest(
            amount_minor=100, currency="eur", idempotency_key="cascade-test-001"
        )

    async def test_fallback_after_explicit_safe_rejection(self):
        backup = MockProvider("backup", "succeeded")
        backup.pay = AsyncMock(wraps=backup.pay)
        result = await cascade_payment(
            self.payment, [MockProvider("primary", "unavailable"), backup]
        )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual([a.provider for a in result.attempts], ["primary", "backup"])
        backup.pay.assert_awaited_once_with(self.payment)

    async def test_terminal_outcomes_do_not_call_backup(self):
        for outcome in ("succeeded", "failed", "unknown"):
            with self.subTest(outcome=outcome):
                backup = MockProvider("backup", "succeeded")
                backup.pay = AsyncMock(wraps=backup.pay)
                result = await cascade_payment(
                    self.payment, [MockProvider("primary", outcome), backup]
                )
                self.assertEqual(result.status, outcome)
                self.assertEqual(len(result.attempts), 1)
                backup.pay.assert_not_awaited()

    async def test_all_unavailable_means_failed(self):
        result = await cascade_payment(self.payment, [
            MockProvider("primary", "unavailable"), MockProvider("backup", "unavailable")
        ])
        self.assertEqual(result.status, "failed")
        self.assertEqual(len(result.attempts), 2)

    async def test_empty_route_is_invalid(self):
        with self.assertRaises(ValueError):
            await cascade_payment(self.payment, [])

    async def test_stripe_outcomes_stop_cascade(self):
        cases = [
            (200, {"id": "pi_test", "status": "succeeded", "amount": 100, "currency": "eur"}, "succeeded"),
            (200, {"id": "pi_test", "status": "requires_action", "amount": 100, "currency": "eur"}, "unknown"),
            (200, {"unexpected": "response"}, "unknown"),
            (402, {"error": {"code": "card_declined"}}, "failed"),
            (409, {"error": {"type": "idempotency_error"}}, "unknown"),
            (500, {"error": {}}, "unknown"),
            (None, None, "unknown"),
        ]
        for code, body, expected in cases:
            with self.subTest(code=code, body=body):
                def handler(request):
                    self.assertEqual(request.headers["Idempotency-Key"], self.payment.idempotency_key)
                    if code is None:
                        raise httpx.ReadTimeout("Simulated timeout", request=request)
                    return httpx.Response(code, json=body)

                settings = Settings(_env_file=None, stripe_api_key="sk_test_dummy")
                backup = MockProvider("backup", "succeeded")
                backup.pay = AsyncMock(wraps=backup.pay)
                async with StripeClient(settings, transport=httpx.MockTransport(handler)) as client:
                    result = await cascade_payment(self.payment, [StripeProvider(client), backup])
                self.assertEqual(result.status, expected)
                self.assertEqual(len(result.attempts), 1)
                backup.pay.assert_not_awaited()
