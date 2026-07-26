from __future__ import annotations

import importlib
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

scope_helpers = importlib.import_module("_verification_scope")
verifier = importlib.import_module("verify_telemetry")

ACTION_TRACE = "a" * 32
ORIGIN_TRACE = "b" * 32
ORIGIN_SPAN = "1" * 16
REPLAY_TRACE = "c" * 32
RULE_ID = "019f8875-0450-7253-b452-ce42f1412086"


def current_incident() -> dict[str, object]:
    return {
        "id": "inc_current",
        "incident_id": "inc_current",
        "policy_outcome": "violation",
        "detected_at": "2026-07-22T06:13:18Z",
        "created_at": "2026-07-22T06:13:18Z",
        "resolved_at": "2026-07-22T06:14:10Z",
        "trace_id": ACTION_TRACE,
        "action": {"trace_id": ACTION_TRACE},
        "memory": {
            "created_at": "2026-07-22T06:12:00Z",
            "created_trace_id": ORIGIN_TRACE,
            "created_span_id": ORIGIN_SPAN,
        },
    }


def current_comparison() -> dict[str, object]:
    return {
        "result": "improved",
        "memory_quarantined": True,
        "original_trace_id": ACTION_TRACE,
        "replay_trace_id": REPLAY_TRACE,
        "before": {
            "policy_outcome": "violation",
            "risk_score": 90,
            "trace_id": ACTION_TRACE,
        },
        "after": {
            "policy_outcome": "pass",
            "risk_score": 10,
            "tool": "request_manager_approval",
            "trace_id": REPLAY_TRACE,
        },
        "causal_memory": {
            "before_status": "active",
            "after_status": "quarantined",
        },
        "operative_replay_memory": {
            "source_trust": "trusted",
            "status": "active",
        },
    }


def current_scope():
    return scope_helpers.build_run_scope(current_incident(), current_comparison())


def result_rows(*items: dict[str, object]) -> dict[str, object]:
    return {"data": {"rows": [{"data": item} for item in items]}}


def test_queries_are_scoped_to_current_run(monkeypatch: pytest.MonkeyPatch) -> None:
    scope = current_scope()
    end_ms = scope.detected_at_ms + 120_000
    monkeypatch.setattr(verifier, "now_ms", lambda: end_ms)

    trace = verifier.trace_payload(scope, 30)
    trace_spec = trace["compositeQuery"]["queries"][0]["spec"]
    expression = trace_spec["filter"]["expression"]
    assert trace["start"] == scope.origin_created_at_ms
    assert trace["end"] == end_ms
    assert ACTION_TRACE in expression
    assert ORIGIN_TRACE in expression
    assert REPLAY_TRACE in expression
    assert scope.origin_span_id == ORIGIN_SPAN

    log = verifier.log_payload(scope, 30)
    log_spec = log["compositeQuery"]["queries"][0]["spec"]
    assert log["start"] == scope.detected_at_ms - 5_000
    assert f"trace_id = '{ACTION_TRACE}'" in log_spec["filter"]["expression"]

    violation = verifier.metric_payload(
        "recallgraph.policy.violations",
        scope.detected_at_ms,
        end_ms,
    )
    replay = verifier.metric_payload("recallgraph.replays", scope.replay_at_ms, end_ms)
    assert violation["start"] == scope.detected_at_ms
    assert replay["start"] == scope.replay_at_ms


def test_run_scope_requires_exact_memory_origin_span() -> None:
    incident = current_incident()
    memory = incident["memory"]
    assert isinstance(memory, dict)
    memory["created_span_id"] = "not-a-span-id"

    with pytest.raises(scope_helpers.ServiceError, match="memory-origin span ID"):
        scope_helpers.build_run_scope(incident, current_comparison())


def test_trace_and_log_validation_reject_other_runs() -> None:
    scope = current_scope()
    traces = result_rows(
        {"name": "recallgraph.memory.write", "trace_id": ORIGIN_TRACE, "span_id": ORIGIN_SPAN},
        {
            "name": "recallgraph.memory.use",
            "trace_id": ACTION_TRACE,
            "span_id": "2" * 16,
            "recallgraph.memory.origin.trace_id": ORIGIN_TRACE,
            "recallgraph.memory.origin.span_id": ORIGIN_SPAN,
        },
        {
            "name": "recallgraph.outcome.evaluate",
            "trace_id": ACTION_TRACE,
            "span_id": "4" * 16,
        },
        {"name": "recallgraph.replay", "trace_id": REPLAY_TRACE, "span_id": "5" * 16},
    )
    assert verifier.verify_trace_result(traces, scope)[0] is True

    wrong_origin_span = result_rows(
        *[
            {
                **row["data"],
                **(
                    {"recallgraph.memory.origin.span_id": "f" * 16}
                    if row["data"].get("name") == "recallgraph.memory.use"
                    else {}
                ),
            }
            for row in traces["data"]["rows"]
        ]
    )
    assert verifier.verify_trace_result(wrong_origin_span, scope)[0] is False

    wrong_write_span = result_rows(
        *[
            {
                **row["data"],
                **(
                    {"span_id": "e" * 16}
                    if row["data"].get("name") == "recallgraph.memory.write"
                    else {}
                ),
            }
            for row in traces["data"]["rows"]
        ]
    )
    assert verifier.verify_trace_result(wrong_write_span, scope)[0] is False

    stale_traces = result_rows(
        *[{**row["data"], "trace_id": "d" * 32} for row in traces["data"]["rows"]]
    )
    assert verifier.verify_trace_result(stale_traces, scope)[0] is False

    assert verifier.verify_log_result(
        result_rows({"trace_id": ACTION_TRACE, "span_id": "6" * 16}),
        scope,
    )[0]
    assert not verifier.verify_log_result(
        result_rows({"trace_id": "d" * 32, "span_id": "6" * 16}),
        scope,
    )[0]


def test_repair_verification_requires_exact_invariants() -> None:
    verifier.assert_repair(current_comparison())

    contradictory = current_comparison()
    contradictory["after"] = {
        **contradictory["after"],
        "policy_outcome": "violation",
    }
    with pytest.raises(verifier.ServiceError, match="replay policy outcome is not pass"):
        verifier.assert_repair(contradictory)

    wrong_replay_trace = current_comparison()
    wrong_replay_trace["after"] = {
        **wrong_replay_trace["after"],
        "trace_id": "d" * 32,
    }
    with pytest.raises(verifier.ServiceError, match="does not match replay_trace_id"):
        verifier.assert_repair(wrong_replay_trace)


def test_alert_history_requires_current_firing_transition() -> None:
    scope = current_scope()
    rules = [{"id": RULE_ID, "alert": scope_helpers.ALERT_RULE_NAME}]
    assert scope_helpers.find_rule_id(rules) == RULE_ID

    path = scope_helpers.alert_history_path(
        RULE_ID,
        start_ms=scope.detected_at_ms,
        end_ms=scope.detected_at_ms + 240_000,
    )
    query = parse_qs(urlparse(path).query)
    assert query == {
        "start": [str(scope.detected_at_ms)],
        "end": [str(scope.detected_at_ms + 240_000)],
        "state": ["firing"],
        "limit": ["100"],
        "order": ["asc"],
    }

    stale = {
        "status": "success",
        "data": {
            "items": [
                {
                    "state": "firing",
                    "stateChanged": True,
                    "unixMilli": scope.detected_at_ms - 1,
                }
            ]
        },
    }
    repeated = {
        "data": {
            "items": [
                {
                    "state": "firing",
                    "stateChanged": False,
                    "unixMilli": scope.detected_at_ms + 60_000,
                }
            ]
        }
    }
    current = {
        "data": {
            "items": [
                {
                    "state": "firing",
                    "stateChanged": True,
                    "unixMilli": scope.detected_at_ms + 180_000,
                }
            ]
        }
    }
    assert not scope_helpers.verify_firing_transition(
        stale,
        start_ms=scope.detected_at_ms,
    )[0]
    assert not scope_helpers.verify_firing_transition(
        repeated,
        start_ms=scope.detected_at_ms,
    )[0]
    assert scope_helpers.verify_firing_transition(
        current,
        start_ms=scope.detected_at_ms,
    )[0]


def test_strict_application_checks_reject_fallback_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident = current_incident()
    graph = {
        "source": "local_evidence",
        "nodes": [{"type": role} for role in ("source", "memory", "decision", "action", "outcome")],
        "edges": [{"source": "source", "target": "memory"}],
        "evidence": [
            {
                "trace_id": ACTION_TRACE,
                "url": f"http://localhost:3301/trace/{ACTION_TRACE}",
            }
        ],
    }

    def fake_request(method: str, path: str, **_: object):
        responses = {
            ("GET", "/health"): {"status": "ok"},
            ("GET", "/incidents/inc_current/graph"): graph,
            ("POST", "/incidents/inc_current/investigate"): {"source": "signoz"},
            ("GET", "/incidents/inc_current/comparison"): current_comparison(),
        }
        return responses[(method, path)]

    monkeypatch.setattr(verifier, "get_incident", lambda: incident)
    monkeypatch.setattr(verifier, "request_json", fake_request)

    checks, scope = verifier.check_application(require_signoz=True)
    by_name = {check.name: check for check in checks}
    assert scope.incident_id == "inc_current"
    assert by_name["graph source"].status == "FAIL"
    assert by_name["investigation source"].status == "FAIL"
