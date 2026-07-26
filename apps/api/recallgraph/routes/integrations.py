from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status

from recallgraph.database import SessionDep
from recallgraph.schemas import AlertWebhookResponse
from recallgraph.telemetry.attributes import SCENARIO
from recallgraph.telemetry.logging import emit_event
from recallgraph.telemetry.tracing import recorded_span

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.post(
    "/signoz-alerts",
    response_model=AlertWebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def receive_signoz_alert(
    payload: dict[str, Any],
    session: SessionDep,
) -> AlertWebhookResponse:
    """Accept local demo notifications without forwarding external data."""

    alert_status = str(payload.get("status", "unknown"))[:40]
    alerts = payload.get("alerts")
    alert_count = len(alerts) if isinstance(alerts, list) else 0
    with recorded_span(
        session,
        "recallgraph.integration.signoz_alert",
        attributes={
            "recallgraph.scenario": SCENARIO,
            "recallgraph.integration.type": "signoz_webhook",
            "recallgraph.alert.status": alert_status,
            "recallgraph.alert.count": alert_count,
        },
    ):
        emit_event(
            session,
            "signoz_alert_received",
            alert_status=alert_status,
            alert_count=alert_count,
        )
    return AlertWebhookResponse(
        status="accepted",
        message="Local SigNoz alert notification received.",
    )
