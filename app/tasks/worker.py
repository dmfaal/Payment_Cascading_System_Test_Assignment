"""Unused queue placeholder. No broker, task execution, or delivery guarantees."""

from typing import Any


def run_cascade_async(payment_data: dict[str, Any]) -> dict[str, Any]:
    """Return a stub response; actual cascade execution is awaited by the API."""
    return {"status": "not_implemented", "payment_id": payment_data.get("id")}
