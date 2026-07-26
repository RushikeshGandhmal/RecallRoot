from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from recallgraph.agent import refund_agent
from recallgraph.agent.decision_provider import DecisionMetadata, DecisionResult
from recallgraph.agent.policy_engine import AgentPolicyDecision
from recallgraph.memory.models import TelemetryLog, TelemetrySpan


def _post(client: TestClient, path: str, payload: dict[str, object] | None = None) -> dict:
    response = client.post(path, json=payload) if payload is not None else client.post(path)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _has_path(graph: dict, start_type: str, target_type: str) -> bool:
    node_types = {node["id"]: node["type"] for node in graph["nodes"]}
    starts = [node_id for node_id, node_type in node_types.items() if node_type == start_type]
    targets = {node_id for node_id, node_type in node_types.items() if node_type == target_type}
    adjacency: dict[str, list[str]] = {}
    for edge in graph["edges"]:
        adjacency.setdefault(edge["source"], []).append(edge["target"])
    pending = list(starts)
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current in targets:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(adjacency.get(current, []))
    return False


def test_complete_unsafe_quarantine_replay_workflow(client: TestClient, app: FastAPI) -> None:
    assert client.get("/health").json()["status"] == "ok"
    assert _post(client, "/demo/reset")["status"] == "reset"
    trusted = _post(client, "/demo/seed-trusted-policy")
    assert trusted["memory"]["source_trust"] == "trusted"
    unsafe = _post(client, "/demo/ingest-unsafe-memory")
    assert unsafe["memory"]["id"] == "mem_unsafe_refund_policy"

    run = _post(
        client,
        "/agent/refund",
        {
            "customer_id": "demo-customer",
            "amount": 35_000,
            "reason": "Duplicate charge",
        },
    )
    assert run["outcome"] == "refund_issued"
    assert run["action"]["result"]["status"] == "succeeded"
    assert run["action"]["result"]["decision"]["requested_provider"] == "deterministic"
    assert run["action"]["result"]["decision"]["provider"] == "deterministic"
    assert run["action"]["result"]["decision"]["fallback"] is False
    assert run["action"]["result"]["decision"]["model"] is None
    assert run["policy_outcome"] == "violation"
    assert run["risk_score"] == 90
    assert run["risk_level"] == "critical"
    incident_id = run["incident_id"]
    assert incident_id

    listing = client.get("/incidents")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["incident_id"] == incident_id

    graph_response = client.get(f"/incidents/{incident_id}/graph")
    assert graph_response.status_code == 200, graph_response.text
    graph = graph_response.json()
    assert graph["source"] == "local_evidence"
    assert any("SigNoz causal evidence rejected" in item for item in graph["warnings"])
    assert len(graph["nodes"]) == 7
    assert _has_path(graph, "source", "action")
    causal_edge = next(edge for edge in graph["edges"] if edge["type"] == "cross_trace_causal")
    assert causal_edge["label"] == "OTel Span Link"

    investigation = _post(client, f"/incidents/{incident_id}/investigate")
    assert "mem_unsafe_refund_policy" in investigation["explanation"]
    assert investigation["evidence"]
    assert investigation["source"] == "local_evidence"
    assert any("SigNoz MCP evidence rejected" in item for item in investigation["warnings"])

    premature_replay = client.post(f"/incidents/{incident_id}/replay")
    assert premature_replay.status_code == 409
    assert premature_replay.json()["detail"]["code"] == ("safe_replay_precondition_failed")

    quarantine = _post(client, "/memories/mem_unsafe_refund_policy/quarantine")
    assert quarantine["status"] == "quarantined"
    assert quarantine["memory"]["status"] == "quarantined"
    quarantine_again = _post(client, "/memories/mem_unsafe_refund_policy/quarantine")
    assert quarantine_again["already_quarantined"] is True

    replay = _post(client, f"/incidents/{incident_id}/replay")
    assert replay["result"] == "improved"
    assert replay["after"]["tool"] == "request_manager_approval"
    assert replay["after"]["policy_outcome"] == "pass"
    assert replay["after"]["risk_score"] == 10
    assert replay["before"]["risk_score"] == 90
    assert replay["run"]["outcome"] == "approval_requested"
    assert replay["causal_memory"] == {
        "id": "mem_unsafe_refund_policy",
        "source_trust": "untrusted",
        "before_status": "active",
        "after_status": "quarantined",
        "remediation": "quarantine",
    }
    assert replay["operative_replay_memory"] == {
        "id": "mem_trusted_refund_policy",
        "source_trust": "trusted",
        "status": "active",
    }
    assert replay["comparison"]["causal_memory"] == replay["causal_memory"]
    assert replay["comparison"]["operative_replay_memory"] == replay["operative_replay_memory"]
    assert replay["comparison"]["verified_at"] == replay["verified_at"]
    assert datetime.fromisoformat(replay["created_at"]).tzinfo is not None
    assert datetime.fromisoformat(replay["verified_at"]).tzinfo is not None

    comparison = client.get(f"/incidents/{incident_id}/comparison")
    assert comparison.status_code == 200
    comparison_payload = comparison.json()
    assert comparison_payload["comparison"]["after"]["policy_outcome"] == "pass"
    assert comparison_payload["causal_memory"] == replay["causal_memory"]
    assert comparison_payload["operative_replay_memory"] == replay["operative_replay_memory"]
    assert comparison_payload["created_at"] == replay["created_at"]
    assert comparison_payload["verified_at"] == replay["verified_at"]
    detail = client.get(f"/incidents/{incident_id}").json()
    assert detail["status"] == "resolved"

    database = app.state.database
    with database.session_factory() as session:
        use_span = session.scalar(
            select(TelemetrySpan)
            .where(TelemetrySpan.name == "recallgraph.memory.use")
            .order_by(TelemetrySpan.started_at.asc())
        )
        assert use_span is not None
        assert use_span.links
        assert use_span.links[0]["trace_id"] == unsafe["memory"]["created_trace_id"]
        assert use_span.links[0]["span_id"] == unsafe["memory"]["created_span_id"]

        decision_span = session.scalar(
            select(TelemetrySpan)
            .where(TelemetrySpan.name == "agent.decision")
            .order_by(TelemetrySpan.started_at.asc())
        )
        assert decision_span is not None
        assert decision_span.attributes["recallgraph.decision.provider"] == "deterministic"
        assert decision_span.attributes["recallgraph.decision.fallback"] is False
        assert unsafe["memory"]["content"] not in str(decision_span.attributes)

        replay_span = session.scalar(
            select(TelemetrySpan)
            .where(TelemetrySpan.name == "recallgraph.replay")
            .order_by(TelemetrySpan.started_at.desc())
        )
        assert replay_span is not None
        assert replay_span.links[0]["trace_id"] == run["action"]["trace_id"]
        assert replay_span.links[0]["span_id"] == run["action"]["span_id"]
        assert (
            replay_span.attributes["recallgraph.replay.original_trace_id"]
            == run["action"]["trace_id"]
        )

        violation_log = session.scalar(
            select(TelemetryLog).where(TelemetryLog.event == "policy_violation_detected")
        )
        assert violation_log is not None
        assert violation_log.trace_id
        assert violation_log.span_id


def test_refund_requires_seeded_policy(client: TestClient) -> None:
    _post(client, "/demo/reset")
    response = client.post(
        "/agent/refund",
        json={"customer_id": "demo", "amount": 35_000, "reason": "Duplicate"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "refund_policy_missing"


def test_ollama_decision_metadata_reaches_action_result_and_safe_spans(
    client: TestClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StaticOllamaProvider:
        requested_provider = "ollama"
        requested_model = "local-test-model"

        def decide(self, memory_content: str, amount: float) -> DecisionResult:
            assert "processed automatically" in memory_content
            assert amount == 35_000
            return DecisionResult(
                decision=AgentPolicyDecision(
                    approval_required=False,
                    rationale="Operative memory permits this refund without manager approval",
                ),
                metadata=DecisionMetadata(
                    requested_provider="ollama",
                    provider="ollama",
                    model="local-test-model",
                    response_model="local-test-model-q4",
                    fallback=False,
                    fallback_reason=None,
                    latency_ms=18.75,
                    input_tokens=29,
                    output_tokens=5,
                ),
            )

    provider = StaticOllamaProvider()
    monkeypatch.setattr(refund_agent, "build_decision_provider", lambda _: provider)
    _post(client, "/demo/reset")
    _post(client, "/demo/seed-trusted-policy")
    unsafe = _post(client, "/demo/ingest-unsafe-memory")

    run = _post(
        client,
        "/agent/refund",
        {
            "customer_id": "demo-customer",
            "amount": 35_000,
            "reason": "Duplicate charge",
        },
    )

    metadata = run["action"]["result"]["decision"]
    assert metadata == {
        "requested_provider": "ollama",
        "provider": "ollama",
        "model": "local-test-model",
        "response_model": "local-test-model-q4",
        "fallback": False,
        "fallback_reason": None,
        "latency_ms": 18.75,
        "input_tokens": 29,
        "output_tokens": 5,
    }
    with app.state.database.session_factory() as session:
        decision_span = session.scalar(
            select(TelemetrySpan).where(TelemetrySpan.name == "agent.decision")
        )
        provider_span = session.scalar(
            select(TelemetrySpan).where(TelemetrySpan.name == "chat local-test-model")
        )
        assert decision_span is not None
        assert provider_span is not None
        assert decision_span.attributes["gen_ai.usage.input_tokens"] == 29
        assert decision_span.attributes["gen_ai.usage.output_tokens"] == 5
        assert provider_span.attributes["gen_ai.provider.name"] == "ollama"
        assert unsafe["memory"]["content"] not in str(decision_span.attributes)
        assert unsafe["memory"]["content"] not in str(provider_span.attributes)
