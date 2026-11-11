import unittest
from urllib.parse import parse_qs

import httpx

from app.config import Settings
from app.providers.stripe import StripeClient


PAYMENT = {"id": "pi_test123", "status": "succeeded", "amount": 100, "currency": "eur"}


class StripeClientTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, handler):
        settings = Settings(_env_file=None, stripe_api_key="sk_test_dummy")
        return StripeClient(settings, transport=httpx.MockTransport(handler))

    async def test_create_and_retrieve_payment(self):
        """Stripe: создать платёж, проверить параметры запроса, получить тот же платёж по ID."""
        requests = []

        def handler(request):
            requests.append(request)
            if request.method == "POST":
                self.assertEqual(request.url.path, "/v1/payment_intents")
                self.assertEqual(request.headers["Idempotency-Key"], "order-123")
                fields = parse_qs(request.content.decode())
                self.assertEqual(fields["amount"], ["100"])
                self.assertEqual(fields["currency"], ["eur"])
                self.assertEqual(fields["payment_method"], ["pm_card_visa"])
                self.assertEqual(fields["confirm"], ["true"])
                self.assertNotIn("payment_method_types[]", fields)
                self.assertEqual(fields["automatic_payment_methods[enabled]"], ["true"])
                self.assertEqual(fields["automatic_payment_methods[allow_redirects]"], ["never"])
            else:
                self.assertEqual(request.method, "GET")
                self.assertEqual(request.url.path, "/v1/payment_intents/pi_test123")
            return httpx.Response(200, json=PAYMENT)

        async with self.make_client(handler) as client:
            created = await client.create_payment(
                amount_minor=100, currency="EUR", idempotency_key="order-123"
            )
            self.assertEqual(created.status, "succeeded")
            self.assertEqual(await client.get_payment(created.id), created)
        self.assertEqual(len(requests), 2)

    async def test_decline_and_server_error_propagate_without_retry(self):
        """Stripe: вернуть 402 и 500; проверить передачу ошибки и отсутствие повторного вызова."""
        for status_code in (402, 500):
            with self.subTest(status_code=status_code):
                requests = []

                def handler(request):
                    requests.append(request)
                    return httpx.Response(status_code, json={"error": {"type": "test_error"}})

                async with self.make_client(handler) as client:
                    with self.assertRaises(httpx.HTTPStatusError) as error:
                        await client.create_payment(
                            amount_minor=100, currency="eur", idempotency_key="order-123"
                        )
                self.assertEqual(error.exception.response.status_code, status_code)
                self.assertEqual(len(requests), 1)

    async def test_timeout_propagates_without_retry(self):
        """Stripe: имитировать таймаут; проверить исключение и ровно один запрос."""
        requests = []

        def handler(request):
            requests.append(request)
            raise httpx.ReadTimeout("Simulated timeout", request=request)

        async with self.make_client(handler) as client:
            with self.assertRaises(httpx.ReadTimeout):
                await client.create_payment(
                    amount_minor=100, currency="eur", idempotency_key="order-123"
                )
        self.assertEqual(len(requests), 1)

    async def test_invalid_amount_does_not_send_request(self):
        """Stripe: передать неверные суммы; отклонить их до отправки HTTP-запроса."""
        def handler(request):
            self.fail("Invalid input must not reach Stripe")

        async with self.make_client(handler) as client:
            for amount in (0, -1, True, 1.5):
                with self.subTest(amount=amount), self.assertRaises(ValueError):
                    await client.create_payment(
                        amount_minor=amount, currency="eur", idempotency_key="order-123"
                    )
