#!/usr/bin/env python3
"""Verify the demo contract and, when authorized, its evidence inside SigNoz."""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from _client import JsonValue, ServiceError, list_from, request_json, scalar_items
from _verification_scope import (
    RunScope,
    alert_history_path,
    build_run_scope,
    find_rule_id,
    verify_firing_transition,
)
from _workflow import (
    assert_policy_violation,
    assert_repair,
    get_incident,
    incident_id,
)

EXPECTED_SPANS = {
    "recallgraph.memory.write",
    "recallgraph.memory.use",
    "recallgraph.outcome.evaluate",
    "recallgraph.replay",
}


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: str
    detail: str


def pass_check(name: str, detail: str) -> Check:
    return Check(name, "PASS", detail)


def fail_check(name: str, detail: str) -> Check:
    return Check(name, "FAIL", detail)


def skip_check(name: str, detail: str) -> Check:
    return Check(name, "SKIP", detail)


def graph_lists(value: JsonValue) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(value, dict):
        return [], []
    graph = value.get("graph", value)
    if not isinstance(graph, dict):
        return [], []
    return list_from(graph.get("nodes"), "nodes"), list_from(graph.get("edges"), "edges")


def node_role(node: dict[str, Any]) -> str:
    for key in ("type", "kind", "node_type", "category"):
        value = node.get(key)
        if value:
            return str(value).lower().replace("-", "_")
    return ""


def check_application(*, require_signoz: bool = False) -> tuple[list[Check], RunScope]:
    checks: list[Check] = []
    health = request_json("GET", "/health")
    checks.append(pass_check("API health", f"responded with {health!r}"))

    incident = get_incident()
    identifier = incident_id(incident)
    if not identifier:
        raise ServiceError("RecallRoot API", "incident response is missing an ID")
    assert_policy_violation(incident)
    checks.append(pass_check("policy violation", f"incident {identifier} is a violation"))

    graph = request_json("GET", f"/incidents/{identifier}/graph")
    nodes, edges = graph_lists(graph)
    roles = {node_role(node) for node in nodes}
    required_groups = {
        "source": {"source", "external_source"},
        "memory": {"memory", "memory_record", "memory_write", "memory_use"},
        "decision": {"decision", "agent_decision"},
        "action": {"action", "tool_action", "execute_tool"},
        "outcome": {"outcome", "policy_outcome", "policy_evaluation"},
    }
    missing = [
        label
        for label, accepted in required_groups.items()
        if not any(role in accepted or any(token in role for token in accepted) for role in roles)
    ]
    if missing:
        checks.append(
            fail_check(
                "causal graph",
                f"missing node roles: {', '.join(missing)}; observed: {sorted(roles)}",
            )
        )
    elif not edges:
        checks.append(fail_check("causal graph", "graph contains nodes but no edges"))
    else:
        checks.append(pass_check("causal graph", f"{len(nodes)} nodes and {len(edges)} edges"))

    flattened = scalar_items(graph)
    has_trace_evidence = any(
        "trace" in key.lower() and isinstance(value, str) and len(value) >= 16
        for key, value in flattened
    )
    has_signoz_evidence = any(
        "signoz" in key.lower() or "signoz" in str(value).lower() for key, value in flattened
    )
    if has_trace_evidence and has_signoz_evidence:
        checks.append(
            pass_check(
                "graph evidence",
                "trace identifiers and SigNoz evidence links are present",
            )
        )
    else:
        checks.append(
            fail_check(
                "graph evidence",
                "graph must expose trace identifiers and SigNoz evidence/deep links",
            )
        )

    if require_signoz:
        graph_source = graph.get("source") if isinstance(graph, dict) else None
        if graph_source == "signoz":
            checks.append(pass_check("graph source", "causal graph came from SigNoz Query Builder"))
        else:
            checks.append(
                fail_check(
                    "graph source",
                    f"strict verification requires source=signoz; observed {graph_source!r}",
                )
            )

        investigation = request_json("POST", f"/incidents/{identifier}/investigate")
        investigation_source = (
            investigation.get("source") if isinstance(investigation, dict) else None
        )
        if investigation_source == "signoz_mcp":
            checks.append(
                pass_check(
                    "investigation source",
                    "incident investigation came from SigNoz MCP",
                )
            )
        else:
            checks.append(
                fail_check(
                    "investigation source",
                    "strict verification requires source=signoz_mcp; "
                    f"observed {investigation_source!r}",
                )
            )

    comparison = request_json("GET", f"/incidents/{identifier}/comparison")
    assert_repair(comparison)
    checks.append(pass_check("replay", "comparison exposes an improved/pass/approval outcome"))
    if not isinstance(incident, dict):
        raise ServiceError("RecallRoot API", "current incident response was not an object")
    return checks, build_run_scope(incident, comparison)


def signoz_api_request(
    method: str,
    path: str,
    payload: JsonValue | None = None,
) -> JsonValue:
    api_key = os.getenv("SIGNOZ_API_KEY", "").strip()
    if not api_key:
        raise ServiceError("SigNoz verification", "SIGNOZ_API_KEY is not set")
    return request_json(
        method,
        path,
        payload=payload,
        base_url=os.getenv("SIGNOZ_URL", "http://localhost:3301"),
        headers={"SIGNOZ-API-KEY": api_key},
        service="SigNoz API",
        timeout=30,
    )


def signoz_request(payload: JsonValue) -> JsonValue:
    return signoz_api_request("POST", "/api/v5/query_range", payload)


def now_ms() -> int:
    return int(time.time() * 1_000)


def scoped_start(start_ms: int, end_ms: int, lookback_minutes: int) -> int:
    return max(start_ms, end_ms - lookback_minutes * 60_000)


def trace_payload(scope: RunScope, lookback_minutes: int) -> dict[str, Any]:
    end = now_ms()
    start = scoped_start(scope.trace_start_ms, end, lookback_minutes)
    names = ", ".join(f"'{name}'" for name in sorted(EXPECTED_SPANS))
    trace_ids = ", ".join(
        f"'{trace_id}'"
        for trace_id in (
            scope.action_trace_id,
            scope.origin_trace_id,
            scope.replay_trace_id,
        )
    )
    select_fields = [
        {
            "name": "trace_id",
            "fieldDataType": "string",
            "signal": "traces",
            "fieldContext": "span",
        },
        {
            "name": "span_id",
            "fieldDataType": "string",
            "signal": "traces",
            "fieldContext": "span",
        },
        {
            "name": "name",
            "fieldDataType": "string",
            "signal": "traces",
            "fieldContext": "span",
        },
        {
            "name": "recallgraph.memory.origin.trace_id",
            "fieldDataType": "string",
            "signal": "traces",
            "fieldContext": "tag",
        },
        {
            "name": "recallgraph.memory.origin.span_id",
            "fieldDataType": "string",
            "signal": "traces",
            "fieldContext": "tag",
        },
    ]
    return {
        "schemaVersion": "v1",
        "start": start,
        "end": end,
        "requestType": "raw",
        "compositeQuery": {
            "queries": [
                {
                    "type": "builder_query",
                    "spec": {
                        "name": "A",
                        "signal": "traces",
                        "disabled": False,
                        "limit": 100,
                        "offset": 0,
                        "order": [{"key": {"name": "timestamp"}, "direction": "desc"}],
                        "having": {"expression": ""},
                        "filter": {
                            "expression": f"name IN ({names}) AND trace_id IN ({trace_ids})"
                        },
                        "selectFields": select_fields,
                    },
                }
            ]
        },
        "formatOptions": {"formatTableResultForUI": False, "fillGaps": False},
        "variables": {},
    }


def log_payload(scope: RunScope, lookback_minutes: int) -> dict[str, Any]:
    end = now_ms()
    start = scoped_start(scope.log_start_ms, end, lookback_minutes)
    return {
        "schemaVersion": "v1",
        "start": start,
        "end": end,
        "requestType": "raw",
        "compositeQuery": {
            "queries": [
                {
                    "type": "builder_query",
                    "spec": {
                        "name": "A",
                        "signal": "logs",
                        "disabled": False,
                        "limit": 100,
                        "offset": 0,
                        "order": [
                            {"key": {"name": "timestamp"}, "direction": "desc"},
                            {"key": {"name": "id"}, "direction": "desc"},
                        ],
                        "having": {"expression": ""},
                        "filter": {
                            # `event` is an OTel attribute, but a fresh SigNoz
                            # workspace may not have promoted it as a searchable
                            # field yet. The log body is stable and indexed.
                            "expression": (
                                "body CONTAINS 'policy_violation_detected' AND "
                                f"trace_id = '{scope.action_trace_id}'"
                            )
                        },
                        "selectFields": [
                            {
                                "name": "trace_id",
                                "fieldDataType": "string",
                                "signal": "logs",
                                "fieldContext": "log",
                            },
                            {
                                "name": "span_id",
                                "fieldDataType": "string",
                                "signal": "logs",
                                "fieldContext": "log",
                            },
                            {
                                "name": "body",
                                "fieldDataType": "string",
                                "signal": "logs",
                                "fieldContext": "log",
                            },
                        ],
                    },
                }
            ]
        },
        "formatOptions": {"formatTableResultForUI": False, "fillGaps": False},
        "variables": {},
    }


def metric_payload(
    metric_name: str,
    start_ms: int,
    end_ms: int,
    *,
    filter_expression: str = "",
) -> dict[str, Any]:
    return {
        "schemaVersion": "v1",
        "start": start_ms,
        "end": end_ms,
        "requestType": "scalar",
        "compositeQuery": {
            "queries": [
                {
                    "type": "builder_query",
                    "spec": {
                        "name": "A",
                        "signal": "metrics",
                        "stepInterval": 60,
                        "disabled": False,
                        "aggregations": [
                            {
                                "metricName": metric_name,
                                "timeAggregation": "sum",
                                "spaceAggregation": "sum",
                            }
                        ],
                        "limit": 100,
                        "order": [{"key": {"name": "__result"}, "direction": "desc"}],
                        "filter": {"expression": filter_expression},
                        "groupBy": [],
                    },
                }
            ]
        },
        "formatOptions": {"formatTableResultForUI": False, "fillGaps": False},
        "variables": {},
    }


def rows(value: JsonValue) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(item: JsonValue) -> None:
        if isinstance(item, dict):
            candidate = item.get("rows")
            if isinstance(candidate, list):
                for row in candidate:
                    if not isinstance(row, dict):
                        continue
                    data = row.get("data")
                    if isinstance(data, dict):
                        found.append(data)
                    else:
                        found.append(row)
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return found


def field_value(row: dict[str, Any], field: str) -> Any:
    if field in row:
        return row[field]
    normalized = field.replace(".", "_").lower()
    for key, value in row.items():
        if key.replace(".", "_").lower() == normalized:
            return value
    return None


def verify_trace_result(value: JsonValue, scope: RunScope) -> tuple[bool, str]:
    result_rows = rows(value)
    expected = (
        ("recallgraph.memory.write", scope.origin_trace_id, scope.origin_span_id),
        ("recallgraph.memory.use", scope.action_trace_id, None),
        ("recallgraph.outcome.evaluate", scope.action_trace_id, None),
        ("recallgraph.replay", scope.replay_trace_id, None),
    )
    missing = [
        name
        for name, trace_id, span_id in expected
        if not any(
            field_value(row, "name") == name
            and field_value(row, "trace_id") == trace_id
            and (span_id is None or field_value(row, "span_id") == span_id)
            for row in result_rows
        )
    ]
    if missing:
        return False, f"missing current-run spans: {', '.join(sorted(missing))}"

    uses = [
        row
        for row in result_rows
        if field_value(row, "name") == "recallgraph.memory.use"
        and field_value(row, "trace_id") == scope.action_trace_id
    ]
    has_origin = any(
        field_value(row, "recallgraph.memory.origin.trace_id") == scope.origin_trace_id
        and field_value(row, "recallgraph.memory.origin.span_id") == scope.origin_span_id
        for row in uses
    )
    if not has_origin:
        return (
            False,
            "memory-use span does not reference the exact current memory-origin span",
        )
    return (
        True,
        "found all expected spans on the current origin, action, and replay traces",
    )


def verify_log_result(value: JsonValue, scope: RunScope) -> tuple[bool, str]:
    result_rows = rows(value)
    correlated = [
        row
        for row in result_rows
        if field_value(row, "trace_id") == scope.action_trace_id and field_value(row, "span_id")
    ]
    if not correlated:
        return (
            False,
            "policy_violation_detected log with trace_id/span_id was not found",
        )
    return True, f"found {len(correlated)} trace-correlated violation log(s)"


def positive_result(value: JsonValue) -> tuple[bool, str]:
    candidates = [
        float(raw)
        for key, raw in scalar_items(value)
        if key.rsplit(".", 1)[-1].lower() in {"value", "__result", "result"}
        and isinstance(raw, (int, float))
        and not isinstance(raw, bool)
    ]
    if any(candidate > 0 for candidate in candidates):
        return True, f"observed positive aggregate {max(candidates):g}"
    return False, "query returned no positive aggregate value"


def retry_check(
    name: str,
    operation: Callable[[], JsonValue],
    validator: Callable[[JsonValue], tuple[bool, str]],
    deadline_seconds: float,
    *,
    poll_seconds: float = 2.0,
) -> Check:
    deadline = time.monotonic() + max(deadline_seconds, 0)
    detail = "no result"
    next_progress = 0.0
    while True:
        try:
            valid, detail = validator(operation())
        except ServiceError as exc:
            detail = str(exc)
            valid = False
        if valid:
            return pass_check(name, detail)
        current = time.monotonic()
        if current >= deadline:
            return fail_check(name, detail)
        if current >= next_progress:
            remaining = max(0, round(deadline - current))
            print(
                f"WAIT  {name}  {detail}; up to {remaining}s remaining",
                file=sys.stderr,
                flush=True,
            )
            next_progress = current + 30
        time.sleep(min(poll_seconds, max(0.0, deadline - current)))


def alert_history(scope: RunScope) -> JsonValue:
    rules = signoz_api_request("GET", "/api/v2/rules")
    rule_id = find_rule_id(rules)
    return signoz_api_request(
        "GET",
        alert_history_path(
            rule_id,
            start_ms=scope.detected_at_ms,
            end_ms=now_ms(),
        ),
    )


def check_signoz(
    scope: RunScope,
    lookback_minutes: int,
    retry_seconds: float,
    *,
    require_alert: bool,
    alert_retry_seconds: float,
) -> list[Check]:
    checks = [
        retry_check(
            "SigNoz traces",
            lambda: signoz_request(trace_payload(scope, lookback_minutes)),
            lambda value: verify_trace_result(value, scope),
            retry_seconds,
        ),
        retry_check(
            "SigNoz correlated log",
            lambda: signoz_request(log_payload(scope, lookback_minutes)),
            lambda value: verify_log_result(value, scope),
            retry_seconds,
        ),
        retry_check(
            "SigNoz violation metric",
            lambda: signoz_request(
                metric_payload(
                    "recallgraph.policy.violations",
                    scope.detected_at_ms,
                    now_ms(),
                )
            ),
            positive_result,
            retry_seconds,
        ),
        retry_check(
            "SigNoz replay metric",
            lambda: signoz_request(
                metric_payload(
                    "recallgraph.replays",
                    scope.replay_at_ms,
                    now_ms(),
                    filter_expression="result = 'improved'",
                )
            ),
            positive_result,
            retry_seconds,
        ),
    ]
    if require_alert:
        checks.append(
            retry_check(
                "SigNoz alert firing",
                lambda: alert_history(scope),
                lambda value: verify_firing_transition(
                    value,
                    start_ms=scope.detected_at_ms,
                ),
                alert_retry_seconds,
                poll_seconds=5.0,
            )
        )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-signoz",
        action="store_true",
        help="fail rather than skip direct SigNoz checks when SIGNOZ_API_KEY is absent",
    )
    parser.add_argument(
        "--lookback-minutes",
        type=int,
        default=int(os.getenv("TELEMETRY_LOOKBACK_MINUTES", "30")),
    )
    parser.add_argument(
        "--retry-seconds",
        type=float,
        default=float(os.getenv("TELEMETRY_RETRY_SECONDS", "45")),
        help="maximum eventual-consistency wait for each direct SigNoz query",
    )
    parser.add_argument(
        "--alert-retry-seconds",
        type=float,
        default=float(os.getenv("TELEMETRY_ALERT_RETRY_SECONDS", "240")),
        help="maximum wait for the one-minute alert evaluator and its delayed window",
    )
    args = parser.parse_args()

    checks: list[Check] = []
    scope: RunScope | None = None
    try:
        application_checks, scope = check_application(require_signoz=args.require_signoz)
        checks.extend(application_checks)
    except ServiceError as exc:
        checks.append(fail_check("application evidence", str(exc)))

    api_key = os.getenv("SIGNOZ_API_KEY", "").strip()
    if api_key and scope is not None:
        checks.extend(
            check_signoz(
                scope,
                args.lookback_minutes,
                args.retry_seconds,
                require_alert=args.require_signoz,
                alert_retry_seconds=args.alert_retry_seconds,
            )
        )
    elif api_key:
        checks.append(
            fail_check(
                "direct SigNoz evidence",
                "current incident/replay scope could not be established",
            )
        )
    elif args.require_signoz:
        checks.append(fail_check("direct SigNoz evidence", "SIGNOZ_API_KEY is not set"))
    else:
        checks.append(
            skip_check(
                "direct SigNoz evidence",
                "set SIGNOZ_API_KEY or run make verify-signoz to require direct queries",
            )
        )

    width = max(len(check.name) for check in checks)
    for check in checks:
        print(f"{check.status:4}  {check.name:<{width}}  {check.detail}")
    if any(check.status == "FAIL" for check in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
