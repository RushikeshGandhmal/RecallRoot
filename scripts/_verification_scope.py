"""Current-run identifiers and alert-history validation for telemetry checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

from _client import JsonValue, ServiceError, list_from, nested

ALERT_RULE_NAME = "High-risk agent action influenced by unsafe memory"
_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID = re.compile(r"^[0-9a-f]{16}$")
_RULE_ID = re.compile(r"^[A-Za-z0-9-]{16,80}$")


@dataclass(frozen=True, slots=True)
class RunScope:
    incident_id: str
    detected_at_ms: int
    replay_at_ms: int
    origin_created_at_ms: int
    action_trace_id: str
    origin_trace_id: str
    origin_span_id: str
    replay_trace_id: str

    @property
    def trace_start_ms(self) -> int:
        return min(self.origin_created_at_ms, self.detected_at_ms)

    @property
    def log_start_ms(self) -> int:
        # The violation log is emitted immediately before the incident row is
        # created. Trace-ID filtering keeps this small clock/order allowance
        # specific to the current run.
        return max(0, self.detected_at_ms - 5_000)


def _timestamp_ms(value: object, field: str) -> int:
    if isinstance(value, bool) or value is None:
        raise ServiceError("RecallRoot API", f"current run is missing {field}")
    if isinstance(value, (int, float)):
        numeric = float(value)
        return int(numeric * 1_000 if numeric < 100_000_000_000 else numeric)
    if not isinstance(value, str) or not value.strip():
        raise ServiceError("RecallRoot API", f"current run has an invalid {field}")
    text = value.strip()
    try:
        numeric = float(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ServiceError("RecallRoot API", f"current run has an invalid {field}") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return int(parsed.timestamp() * 1_000)
    return int(numeric * 1_000 if numeric < 100_000_000_000 else numeric)


def _required_trace_id(value: object, field: str) -> str:
    candidate = str(value or "").lower()
    if not _TRACE_ID.fullmatch(candidate):
        raise ServiceError("RecallRoot API", f"current run is missing a valid {field}")
    return candidate


def _required_span_id(value: object, field: str) -> str:
    candidate = str(value or "").lower()
    if not _SPAN_ID.fullmatch(candidate):
        raise ServiceError("RecallRoot API", f"current run is missing a valid {field}")
    return candidate


def build_run_scope(incident: dict[str, object], comparison: JsonValue) -> RunScope:
    identifier = nested(incident, ("incident_id",), ("id",))
    if not identifier:
        raise ServiceError("RecallRoot API", "current run is missing an incident ID")

    detected = _timestamp_ms(
        nested(incident, ("detected_at",), ("created_at",)),
        "incident detected_at",
    )
    resolved = nested(incident, ("resolved_at",))
    replay_at = _timestamp_ms(resolved, "incident resolved_at") if resolved else detected
    origin_created = _timestamp_ms(
        nested(incident, ("memory", "created_at")),
        "memory created_at",
    )
    return RunScope(
        incident_id=str(identifier),
        detected_at_ms=detected,
        replay_at_ms=max(detected, replay_at),
        origin_created_at_ms=origin_created,
        action_trace_id=_required_trace_id(
            nested(incident, ("action", "trace_id"), ("trace_id",)),
            "action trace ID",
        ),
        origin_trace_id=_required_trace_id(
            nested(incident, ("memory", "created_trace_id")),
            "memory-origin trace ID",
        ),
        origin_span_id=_required_span_id(
            nested(incident, ("memory", "created_span_id")),
            "memory-origin span ID",
        ),
        replay_trace_id=_required_trace_id(
            nested(
                comparison,
                ("replay_trace_id",),
                ("replay", "trace_id"),
                ("comparison", "replay", "trace_id"),
                ("after", "trace_id"),
            ),
            "replay trace ID",
        ),
    )


def find_rule_id(value: JsonValue, expected_name: str = ALERT_RULE_NAME) -> str:
    matches = [
        item
        for item in list_from(value, "rules", "items")
        if str(item.get("alert") or item.get("name") or item.get("ruleName") or "") == expected_name
    ]
    if not matches:
        raise ServiceError("SigNoz alert history", f"alert rule {expected_name!r} was not found")
    if len(matches) > 1:
        raise ServiceError(
            "SigNoz alert history",
            f"multiple alert rules named {expected_name!r} were found",
        )
    identifier = str(
        matches[0].get("id") or matches[0].get("ruleId") or matches[0].get("uuid") or ""
    )
    if not _RULE_ID.fullmatch(identifier):
        raise ServiceError("SigNoz alert history", "matching alert rule has an invalid ID")
    return identifier


def alert_history_path(rule_id: str, *, start_ms: int, end_ms: int) -> str:
    if not _RULE_ID.fullmatch(rule_id):
        raise ServiceError("SigNoz alert history", "alert rule has an invalid ID")
    query = urlencode(
        {
            "start": start_ms,
            "end": end_ms,
            "state": "firing",
            "limit": 100,
            "order": "asc",
        }
    )
    return f"/api/v2/rules/{rule_id}/history/timeline?{query}"


def verify_firing_transition(value: JsonValue, *, start_ms: int) -> tuple[bool, str]:
    transitions: list[int] = []
    for item in list_from(value, "items"):
        try:
            timestamp = int(item.get("unixMilli", 0))
        except (TypeError, ValueError):
            continue
        state_transition = item.get("state") == "firing" and item.get("stateChanged") is True
        overall_transition = (
            item.get("overallState") == "firing" and item.get("overallStateChanged") is True
        )
        if timestamp >= start_ms and (state_transition or overall_transition):
            transitions.append(timestamp)
    if transitions:
        return (
            True,
            f"firing transition recorded {min(transitions) - start_ms}ms after incident",
        )
    return False, "no firing transition was recorded after the current incident"
