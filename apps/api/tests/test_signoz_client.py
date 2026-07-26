from __future__ import annotations

import pytest

from recallgraph.config import Settings
from recallgraph.graph.models import SpanEvidence
from recallgraph.graph.signoz_client import SigNozClient, SigNozUnavailable


def _causal_spans(
    *,
    action_trace: str = "a" * 32,
    origin_trace: str = "b" * 32,
    origin_span: str = "6" * 16,
) -> tuple[list[SpanEvidence], list[SpanEvidence]]:
    action_spans = [
        SpanEvidence(
            trace_id=action_trace,
            span_id="3" * 16,
            name="recallgraph.memory.use",
            attributes={
                "recallgraph.memory.id": "mem_test",
                "recallgraph.memory.source.name": "unverified-playbook.txt",
                "recallgraph.memory.source.trust": "untrusted",
                "recallgraph.memory.sanitized_preview": "Unsafe refund guidance.",
                "recallgraph.memory.origin.trace_id": origin_trace,
                "recallgraph.memory.origin.span_id": origin_span,
            },
        ),
        SpanEvidence(
            trace_id=action_trace,
            span_id="4" * 16,
            name="execute_tool issue_refund",
            attributes={
                "recallgraph.action.id": "act_test",
                "recallgraph.action.type": "issue_refund",
                "recallgraph.memory.id": "mem_test",
            },
        ),
        SpanEvidence(
            trace_id=action_trace,
            span_id="5" * 16,
            name="recallgraph.outcome.evaluate",
            attributes={
                "recallgraph.action.id": "act_test",
                "recallgraph.action.type": "issue_refund",
                "recallgraph.memory.id": "mem_test",
                "recallgraph.approval.required": True,
                "recallgraph.policy.outcome": "violation",
            },
        ),
    ]
    origin_spans = [
        SpanEvidence(
            trace_id=origin_trace,
            span_id=origin_span,
            name="recallgraph.memory.write",
            attributes={
                "recallgraph.memory.id": "mem_test",
                "recallgraph.memory.operation": "write",
                "recallgraph.memory.source.name": "unverified-playbook.txt",
                "recallgraph.memory.source.trust": "untrusted",
                "recallgraph.memory.sanitized_preview": "Unsafe refund guidance.",
            },
        )
    ]
    return action_spans, origin_spans


def test_query_body_uses_current_signoz_v5_builder_contract() -> None:
    client = SigNozClient(Settings(signoz_api_url="http://signoz:8080"))
    body = client._query_body("recallgraph.action.id = 'act_123'")
    assert body["requestType"] == "raw"
    query = body["compositeQuery"]["queries"][0]
    assert query["type"] == "builder_query"
    assert query["spec"]["signal"] == "traces"
    assert query["spec"]["filter"]["expression"] == "recallgraph.action.id = 'act_123'"
    assert {field["name"] for field in query["spec"]["selectFields"]} >= {
        "trace_id",
        "span_id",
        "recallgraph.memory.origin.trace_id",
        "recallgraph.memory.origin.span_id",
        "recallgraph.action.id",
    }


def test_normalizes_common_trace_row_shape() -> None:
    spans = SigNozClient._normalize_spans(
        {
            "data": {
                "rows": [
                    {
                        "trace_id": "a" * 32,
                        "span_id": "b" * 16,
                        "parent_span_id": "c" * 16,
                        "name": "recallgraph.memory.use",
                        "attributes": {"recallgraph.memory.id": "mem_1"},
                        "links": [{"trace_id": "d" * 32, "span_id": "e" * 16}],
                    }
                ]
            }
        }
    )
    assert len(spans) == 1
    assert spans[0].name == "recallgraph.memory.use"
    assert spans[0].attributes["recallgraph.memory.id"] == "mem_1"
    assert spans[0].links[0]["trace_id"] == "d" * 32


def test_fetch_causal_evidence_queries_only_exact_linked_traces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action_trace = "a" * 32
    origin_trace = "b" * 32
    action_spans, origin_spans = _causal_spans()
    expressions: list[str] = []
    client = SigNozClient(Settings(signoz_api_url="http://signoz:8080"))

    def query_spans(expression: str, *, limit: int = 100) -> list[SpanEvidence]:
        expressions.append(expression)
        assert limit == 100
        return action_spans if action_trace in expression else origin_spans

    monkeypatch.setattr(client, "query_spans", query_spans)
    evidence = client.fetch_causal_evidence(
        action_id="act_test",
        action_type="issue_refund",
        memory_id="mem_test",
        action_trace_id=action_trace,
        origin_trace_id=origin_trace,
        origin_span_id="6" * 16,
    )

    assert evidence.source == "signoz"
    assert expressions == [
        f"trace_id = '{action_trace}'",
        f"trace_id = '{origin_trace}'",
    ]


def test_fetch_causal_evidence_rejects_a_stale_origin_without_labeling_signoz(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action_spans, _ = _causal_spans(
        origin_trace="c" * 32,
        origin_span="9" * 16,
    )
    expressions: list[str] = []
    client = SigNozClient(Settings(signoz_api_url="http://signoz:8080"))

    def query_spans(expression: str, *, limit: int = 100) -> list[SpanEvidence]:
        expressions.append(expression)
        assert limit == 100
        return action_spans

    monkeypatch.setattr(client, "query_spans", query_spans)
    with pytest.raises(SigNozUnavailable, match="origin mismatch"):
        client.fetch_causal_evidence(
            action_id="act_test",
            action_type="issue_refund",
            memory_id="mem_test",
            action_trace_id="a" * 32,
            origin_trace_id="b" * 32,
            origin_span_id="6" * 16,
        )

    assert expressions == [f"trace_id = '{'a' * 32}'"]
