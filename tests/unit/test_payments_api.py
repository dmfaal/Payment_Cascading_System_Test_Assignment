import asyncio
import unittest
from unittest.mock import patch

import httpx

from app.config import Settings
from app.db.session import InMemoryStorage
from app.main import create_app
from app.providers.stripe import StripeClient


class PaymentApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.body = {"amount": 100, "currency": "EUR", "idempotency_key": "api-test-001"}
        self.reply = {"id": "pi_test", "status": "succeeded", "amount": 100, "currency": "eur"}
        self.http_status = 200
        self.entered = None
        self.release = None

        async def handler(request):
            self.requests.append(request)
            if self.entered is not None:
                self.entered.set()
                await self.release.wait()
            return httpx.Response(self.http_status, json=self.reply)

        settings = Settings(_env_file=None, stripe_api_key="sk_test_dummy")
        self.patches = [
            patch("app.api.payments.storage", InMemoryStorage()),
            patch("app.api.payments.get_settings", return_value=settings),
            patch(
                "app.api.payments.StripeClient",
                side_effect=lambda settings: StripeClient(settings, transport=httpx.MockTransport(handler)),
            ),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)

    async def test_create_get_and_repeat(self):
        """API: создать платёж, повторить POST, прочитать GET; проверить один вызов Stripe."""
        created = await self.client.post("/v1/payments", json=self.body)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["status"], "succeeded")
        repeated = await self.client.post("/v1/payments", json=self.body)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json(), created.json())
        found = await self.client.get(f"/v1/payments/{created.json()['id']}")
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json()["status"], "succeeded")
        self.assertEqual(len(self.requests), 1)

    async def test_changed_parameters_conflict(self):
        """API: повторить ключ с другой суммой или маршрутом; получить 409 без нового списания."""
        await self.client.post("/v1/payments", json=self.body)
        for change in ({"amount": 200}, {"providers": ["mock", "stripe"]}):
            response = await self.client.post("/v1/payments", json=self.body | change)
            self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.requests), 1)

    async def test_invalid_requests_do_not_call_stripe(self):
        """API: передать неверные сумму, маршрут и ключ; получить 422 без вызова Stripe."""
        for change in (
            {"providers": []},
            {"providers": ["missing"]},
            {"amount": True},
            {"amount": 1.5},
            {"amount": 0},
            {"idempotency_key": "   "},
        ):
            with self.subTest(change=change):
                response = await self.client.post("/v1/payments", json=self.body | change)
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.requests, [])

    async def test_invalid_idempotency_keys_do_not_call_stripe(self):
        """API: кириллица, пробелы, спецсимволы и неверная длина ключа дают 422 до HTTP."""
        for key in (
            "платёж-001",
            "café",
            "demo 001",
            " demo",
            "demo ",
            "demo\n",
            "demo\r\nX-Test: 1",
            "demo\t001",
            "demo/001",
            "demo.001",
            "",
            "a" * 256,
        ):
            with self.subTest(key=repr(key)):
                response = await self.client.post("/v1/payments", json=self.body | {"idempotency_key": key})
                self.assertEqual(response.status_code, 422)
                self.assertTrue(any(error["loc"][-1] == "idempotency_key" for error in response.json()["detail"]))
        self.assertEqual(self.requests, [])

    async def test_valid_idempotency_keys_are_forwarded_unchanged(self):
        """API: допустимые ключи длиной 1-255 символов передаются в заголовок Stripe без изменений."""
        for key in ("a", "Order_001-test", "550e8400-e29b-41d4-a716-446655440000", "a" * 255):
            with self.subTest(key=key):
                response = await self.client.post("/v1/payments", json=self.body | {"idempotency_key": key})
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.json()["status"], "succeeded")
                self.assertEqual(self.requests[-1].headers["Idempotency-Key"], key)
        self.assertEqual(len(self.requests), 4)

    async def test_mock_fallback_to_stripe(self):
        """API: mock возвращает unavailable; Stripe завершает платёж; проверить порядок попыток."""
        response = await self.client.post("/v1/payments", json=self.body | {"providers": ["mock", "stripe"]})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "succeeded")
        self.assertEqual(
            [(a["provider"], a["status"]) for a in response.json()["attempts"]],
            [("mock", "unavailable"), ("stripe", "succeeded")],
        )
        self.assertEqual(len(self.requests), 1)

    async def test_mock_only_route(self):
        """API: вызвать только mock; получить failed без обращения к Stripe."""
        response = await self.client.post("/v1/payments", json=self.body | {"providers": ["mock"]})
        self.assertEqual(response.json()["status"], "failed")
        self.assertEqual(self.requests, [])

    async def test_concurrent_repeat_observes_processing(self):
        """API: задержать первый POST, отправить повтор; получить 202 и один вызов Stripe."""
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        first = asyncio.create_task(self.client.post("/v1/payments", json=self.body))
        try:
            await asyncio.wait_for(self.entered.wait(), timeout=2)
            repeated = await self.client.post("/v1/payments", json=self.body)
            self.assertEqual(repeated.status_code, 202)
            self.assertEqual(repeated.json()["status"], "processing")
            found = await self.client.get(f"/v1/payments/{repeated.json()['id']}")
            self.assertEqual(found.json()["status"], "processing")
        finally:
            self.release.set()
            completed = await first
        self.assertEqual(completed.json()["id"], repeated.json()["id"])
        self.assertEqual(completed.json()["status"], "succeeded")
        self.assertEqual(len(self.requests), 1)

    async def test_unknown_is_saved_and_not_retried(self):
        """API: имитировать HTTP 500 Stripe, повторить POST; вернуть сохранённый unknown."""
        self.http_status = 500
        self.reply = {"error": {"type": "api_error"}}
        first = await self.client.post("/v1/payments", json=self.body)
        repeated = await self.client.post("/v1/payments", json=self.body)
        self.assertEqual(first.json()["status"], "unknown")
        self.assertEqual(repeated.json(), first.json())
        self.assertEqual(len(self.requests), 1)

    async def test_missing_payment(self):
        """API: запросить отсутствующий ID; получить 404."""
        response = await self.client.get("/v1/payments/missing")
        self.assertEqual(response.status_code, 404)
