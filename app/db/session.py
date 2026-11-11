"""Process-local storage. Reservations are atomic in a single async event loop."""

from typing import Any
from uuid import uuid4


class InMemoryStorage:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._keys: dict[str, str] = {}

    def reserve(self, key: str, request: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Return an existing payment or reserve its key before any external call."""
        if key in self._keys:
            record = self._store[self._keys[key]]
            if record["request"] != request:
                raise ValueError("Idempotency key already used with different parameters")
            return record, False
        payment_id = str(uuid4())
        record = {
            "id": payment_id,
            "request": request,
            "status": "processing",
            "provider": None,
            "attempts": [],
        }
        self._store[payment_id] = record
        self._keys[key] = payment_id
        return record, True

    def save(self, payment_id: str, data: dict[str, Any]) -> None:
        self._store[payment_id].update(data)

    def get(self, payment_id: str) -> dict[str, Any] | None:
        return self._store.get(payment_id)


storage = InMemoryStorage()
