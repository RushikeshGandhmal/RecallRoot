"""Deterministic RecallRoot demo workflow and response assertions."""

from __future__ import annotations

import os
import re
from typing import Any

from _client import (
    JsonValue,
    ServiceError,
    list_from,
    nested,
    request_json,
    scalar_items,
)

UNSAFE_MEMORY_ID = "mem_unsafe_refund_policy"
_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")


def refund_payload() -> dict[str, Any]:
    amount_raw = os.getenv("DEMO_REFUND_AMOUNT", "35000")
    try:
        amount = float(amount_raw)
    except ValueError as exc:
        raise ServiceError("configuration", "DEMO_REFUND_AMOUNT must be numeric") from exc
    return {
        "customer_id": os.getenv("DEMO_CUSTOMER_ID", "demo-customer"),
        "amount": amount,
        "reason": os.getenv("DEMO_REFUND_REASON", "Duplicate charge"),
    }


def reset() -> JsonValue:
    return request_json("POST", "/demo/reset")


def seed_trusted_policy() -> JsonValue:
    return request_json("POST", "/demo/seed-trusted-policy")


def ingest_unsafe_memory() -> JsonValue:
    return request_json("POST", "/demo/ingest-unsafe-memory")


def submit_refund() -> JsonValue:
    return request_json("POST", "/agent/refund", payload=refund_payload())


def incident_id(value: JsonValue) -> str | None:
    candidate = nested(
        value,
        ("incident_id",),
        ("id",),
        ("incident", "id"),
        ("incident", "incident_id"),
    )
    return str(candidate) if candidate else None


def memory_id(value: JsonValue) -> str | None:
    candidate = nested(
        value,
        ("memory_id",),
        ("memory", "id"),
        ("memory", "memory_id"),
        ("influence", "memory_id"),
    )
    return str(candidate) if candidate else None


def list_incidents() -> list[dict[str, Any]]:
    response = request_json("GET", "/incidents")
    return list_from(response, "incidents", "items")


def get_incident(preferred_id: str | None = None) -> dict[str, Any]:
    incidents = list_incidents()
    if preferred_id:
        for incident in incidents:
            if incident_id(incident) == preferred_id:
                return incident

    def is_violation(item: dict[str, Any]) -> bool:
        fields = scalar_items(item)
        return any(
            "policy" in key.lower() and "violation" in str(value).lower() for key, value in fields
        )

    violations = [item for item in incidents if is_violation(item)]
    candidates = violations or incidents
    if not candidates:
        raise ServiceError("RecallRoot API", "no incident was created by the refund run")
    return candidates[0]


def assert_policy_violation(*values: JsonValue) -> None:
    fields = [field for value in values for field in scalar_items(value)]
    if any("violation" in str(value).lower() for _, value in fields):
        return
    raise ServiceError(
        "RecallRoot API",
        "unsafe run did not expose a verifiable policy violation in its response or incident",
    )


def investigate(identifier: str) -> JsonValue:
    return request_json("POST", f"/incidents/{identifier}/investigate")


def quarantine(identifier: str) -> JsonValue:
    return request_json("POST", f"/memories/{identifier}/quarantine")


def replay(identifier: str) -> JsonValue:
    return request_json("POST", f"/incidents/{identifier}/replay")


def comparison(identifier: str) -> JsonValue:
    return request_json("GET", f"/incidents/{identifier}/comparison")


def assert_repair(*values: JsonValue) -> None:
    def text_at(value: JsonValue, *paths: tuple[str, ...]) -> str:
        return str(nested(value, *paths) or "").strip().lower()

    def number_at(value: JsonValue, *paths: tuple[str, ...]) -> float | None:
        candidate = nested(value, *paths)
        if isinstance(candidate, bool):
            return None
        try:
            return float(candidate)
        except (TypeError, ValueError):
            return None

    def invariant_failures(value: JsonValue) -> list[str]:
        if not isinstance(value, dict):
            return ["response is not an object"]

        failures: list[str] = []
        if text_at(value, ("result",)) != "improved":
            failures.append("result is not improved")
        if nested(value, ("memory_quarantined",)) is not True:
            failures.append("causal memory is not marked quarantined")
        if text_at(value, ("before", "policy_outcome")) != "violation":
            failures.append("original policy outcome is not violation")
        if text_at(value, ("after", "policy_outcome")) != "pass":
            failures.append("replay policy outcome is not pass")
        if text_at(value, ("after", "tool")) != "request_manager_approval":
            failures.append("replay did not request manager approval")
        if text_at(value, ("causal_memory", "before_status")) != "active":
            failures.append("causal memory was not active before remediation")
        if text_at(value, ("causal_memory", "after_status")) != "quarantined":
            failures.append("causal memory was not quarantined")
        if text_at(value, ("operative_replay_memory", "source_trust")) != "trusted":
            failures.append("operative replay memory is not trusted")
        if text_at(value, ("operative_replay_memory", "status")) != "active":
            failures.append("operative replay memory is not active")

        before_risk = number_at(value, ("before", "risk_score"))
        after_risk = number_at(value, ("after", "risk_score"))
        if before_risk is None or after_risk is None or after_risk >= before_risk:
            failures.append("replay risk score did not decrease")

        original_trace = text_at(value, ("original_trace_id",))
        before_trace = text_at(value, ("before", "trace_id"))
        replay_trace = text_at(value, ("replay_trace_id",))
        after_trace = text_at(value, ("after", "trace_id"))
        trace_ids = (original_trace, before_trace, replay_trace, after_trace)
        if not all(_TRACE_ID.fullmatch(trace_id) for trace_id in trace_ids):
            failures.append("comparison is missing valid hexadecimal trace IDs")
        elif original_trace != before_trace:
            failures.append("before.trace_id does not match original_trace_id")
        elif replay_trace != after_trace:
            failures.append("after.trace_id does not match replay_trace_id")
        elif original_trace == replay_trace:
            failures.append("replay trace is not distinct from the original trace")
        return failures

    closest_failures: list[str] | None = None
    for value in values:
        failures = invariant_failures(value)
        if not failures:
            return
        if closest_failures is None or len(failures) < len(closest_failures):
            closest_failures = failures
    raise ServiceError(
        "RecallRoot API",
        "replay verification failed: " + "; ".join(closest_failures or ["no response"]),
    )


def remediate(incident: dict[str, Any]) -> tuple[JsonValue, JsonValue, JsonValue]:
    identifier = incident_id(incident)
    if not identifier:
        raise ServiceError("RecallRoot API", "incident response is missing an ID")

    unsafe_memory = memory_id(incident)
    if not unsafe_memory:
        details = request_json("GET", f"/incidents/{identifier}")
        unsafe_memory = memory_id(details)
    unsafe_memory = unsafe_memory or UNSAFE_MEMORY_ID

    quarantined = quarantine(unsafe_memory)
    replayed = replay(identifier)
    compared = comparison(identifier)
    assert_repair(replayed, compared)
    return quarantined, replayed, compared
