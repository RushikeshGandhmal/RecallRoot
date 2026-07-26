from __future__ import annotations

from typing import Any

from recallgraph.ids import new_id


def issue_refund(amount: float, customer_id: str) -> dict[str, Any]:
    """Fake local refund tool; the persisted Action row is its durable receipt."""

    return {
        "status": "succeeded",
        "transaction_id": new_id("txn"),
        "customer_id": customer_id,
        "amount": amount,
        "provider": "local-demo",
    }


def request_manager_approval(amount: float, customer_id: str) -> dict[str, Any]:
    """Fake local approval tool; no external workflow is invoked."""

    return {
        "status": "pending_approval",
        "approval_request_id": new_id("apr"),
        "customer_id": customer_id,
        "amount": amount,
        "provider": "local-demo",
    }
