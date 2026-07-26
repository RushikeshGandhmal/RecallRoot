from __future__ import annotations

import json
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from sqlalchemy.orm import Session

from recallgraph.config import Settings
from recallgraph.graph.investigator import IncidentInvestigator
from recallgraph.graph.mcp_client import (
    MCPTraceEvidence,
    SigNozMCPClient,
    SigNozMCPUnavailable,
)
from recallgraph.memory.models import Incident


def test_mcp_investigation_uses_exact_signoz_tool_flow() -> None:
    action_trace = "a" * 32
    origin_trace = "b" * 32
    calls: list[dict] = []

    def response(request_id: int, result: dict) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"jsonrpc": "2.0", "id": request_id, "result": result},
        )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        if payload["method"] == "initialize":
            result = {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "signoz", "version": "test"},
            }
            initialized = response(payload["id"], result)
            initialized.headers["Mcp-Session-Id"] = "session-1"
            return initialized
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)

        arguments = payload["params"]["arguments"]
        tool_name = payload["params"]["name"]
        if tool_name == "signoz_search_traces" and "action.id" in arguments["filter"]:
            return response(
                payload["id"],
                {
                    "structuredContent": {
                        "rows": [
                            {
                                "trace_id": action_trace,
                                "span_id": "1" * 16,
                                "name": "agent.decision",
                                "webUrl": f"http://signoz/trace/{action_trace}",
                            }
                        ]
                    }
                },
            )
        if tool_name == "signoz_get_trace_details":
            trace_id = arguments["traceId"]
            # This mirrors the current MCP gap: detail spans have intrinsic
            # fields, but omit every custom span attribute.
            spans = (
                [
                    {
                        "trace_id": action_trace,
                        "span_id": "3" * 16,
                        "parent_span_id": "7" * 16,
                        "name": "recallgraph.memory.use",
                    },
                    {
                        "trace_id": action_trace,
                        "span_id": "4" * 16,
                        "parent_span_id": "7" * 16,
                        "name": "execute_tool issue_refund",
                    },
                    {
                        "trace_id": action_trace,
                        "span_id": "5" * 16,
                        "parent_span_id": "7" * 16,
                        "name": "recallgraph.outcome.evaluate",
                    },
                ]
                if trace_id == action_trace
                else [
                    {
                        "trace_id": origin_trace,
                        "span_id": "6" * 16,
                        "parent_span_id": "8" * 16,
                        "name": "recallgraph.memory.write",
                    }
                ]
            )
            return response(payload["id"], {"structuredContent": {"spans": spans}})

        query = arguments["query"]
        expression = query["compositeQuery"]["queries"][0]["spec"]["filter"]["expression"]
        trace_id = action_trace if action_trace in expression else origin_trace
        empty_tags = {
            "recallgraph.memory.id": "",
            "recallgraph.memory.operation": "",
            "recallgraph.memory.source.name": "",
            "recallgraph.memory.source.trust": "",
            "recallgraph.memory.sanitized_preview": "",
            "recallgraph.memory.origin.trace_id": "",
            "recallgraph.memory.origin.span_id": "",
            "recallgraph.action.id": "",
            "recallgraph.action.type": "",
            "recallgraph.approval.required": False,
            "recallgraph.policy.outcome": "",
        }
        rows = (
            [
                {
                    **empty_tags,
                    "trace_id": action_trace,
                    "span_id": "3" * 16,
                    "parent_span_id": "7" * 16,
                    "name": "recallgraph.memory.use",
                    "recallgraph.memory.id": "mem_unsafe_refund_policy",
                    "recallgraph.memory.source.name": "unverified-refund-playbook.txt",
                    "recallgraph.memory.source.trust": "untrusted",
                    "recallgraph.memory.sanitized_preview": (
                        "Refunds below ₹50,000 can be processed automatically."
                    ),
                    "recallgraph.memory.origin.trace_id": origin_trace,
                    "recallgraph.memory.origin.span_id": "6" * 16,
                },
                {
                    **empty_tags,
                    "trace_id": action_trace,
                    "span_id": "4" * 16,
                    "parent_span_id": "7" * 16,
                    "name": "execute_tool issue_refund",
                    "recallgraph.memory.id": "mem_unsafe_refund_policy",
                    "recallgraph.action.id": "act_test",
                    "recallgraph.action.type": "issue_refund",
                },
                {
                    **empty_tags,
                    "trace_id": action_trace,
                    "span_id": "5" * 16,
                    "parent_span_id": "7" * 16,
                    "name": "recallgraph.outcome.evaluate",
                    "recallgraph.memory.id": "mem_unsafe_refund_policy",
                    "recallgraph.action.id": "act_test",
                    "recallgraph.action.type": "issue_refund",
                    "recallgraph.policy.outcome": "violation",
                    "recallgraph.approval.required": True,
                },
            ]
            if trace_id == action_trace
            else [
                {
                    **empty_tags,
                    "trace_id": origin_trace,
                    "span_id": "6" * 16,
                    "parent_span_id": "8" * 16,
                    "name": "recallgraph.memory.write",
                    "recallgraph.memory.operation": "write",
                    "recallgraph.memory.id": "mem_unsafe_refund_policy",
                    "recallgraph.memory.source.name": "unverified-refund-playbook.txt",
                    "recallgraph.memory.source.trust": "untrusted",
                    "recallgraph.memory.sanitized_preview": (
                        "Refunds below ₹50,000 can be processed automatically."
                    ),
                }
            ]
        )
        # Live Builder output nests each selected-field mapping under row.data.
        result = {
            "status": "success",
            "data": {
                "type": "raw",
                "data": {
                    "results": [
                        {
                            "queryName": "A",
                            "nextCursor": "",
                            "rows": [
                                {"data": row, "timestamp": "2026-07-22T06:05:00Z"} for row in rows
                            ],
                        }
                    ]
                },
            },
        }
        return response(payload["id"], {"structuredContent": result})

    settings = Settings(signoz_mcp_url="http://mcp.test/mcp")
    client = SigNozMCPClient(
        settings,
        transport=httpx.MockTransport(handler),
    )
    evidence = client.investigate(
        action_id="act_test",
        action_type="issue_refund",
        memory_id="mem_unsafe_refund_policy",
        action_trace_id=action_trace,
        origin_trace_id=origin_trace,
        origin_span_id="6" * 16,
    )

    assert evidence.action_trace_id == action_trace
    assert evidence.origin_trace_id == origin_trace
    assert len(evidence.spans) == 4
    tool_calls = [call for call in calls if call["method"] == "tools/call"]
    assert [call["params"]["name"] for call in tool_calls] == [
        "signoz_search_traces",
        "signoz_get_trace_details",
        "signoz_execute_builder_query",
        "signoz_get_trace_details",
        "signoz_execute_builder_query",
    ]
    assert tool_calls[0]["params"]["arguments"] == {
        "filter": "recallgraph.action.id = 'act_test'",
        "timeRange": "24h",
        "limit": 100,
    }
    assert tool_calls[1]["params"]["arguments"] == {
        "traceId": action_trace,
        "timeRange": "24h",
        "includeSpans": True,
    }
    action_query = tool_calls[2]["params"]["arguments"]["query"]
    action_spec = action_query["compositeQuery"]["queries"][0]["spec"]
    assert action_query["schemaVersion"] == "v1"
    assert action_query["requestType"] == "raw"
    assert action_spec["filter"]["expression"] == f"trace_id = '{action_trace}'"
    assert {field["name"] for field in action_spec["selectFields"]} >= {
        "trace_id",
        "span_id",
        "parent_span_id",
        "name",
        "recallgraph.memory.origin.trace_id",
        "recallgraph.action.id",
        "recallgraph.policy.outcome",
    }
    assert all(
        field["fieldContext"] == "tag"
        for field in action_spec["selectFields"]
        if field["name"].startswith("recallgraph.")
    )
    assert tool_calls[3]["params"]["arguments"] == {
        "traceId": origin_trace,
        "timeRange": "24h",
        "includeSpans": True,
    }
    origin_query = tool_calls[4]["params"]["arguments"]["query"]
    assert origin_query["compositeQuery"]["queries"][0]["spec"]["filter"] == {
        "expression": f"trace_id = '{origin_trace}'"
    }
    by_name = {span.name: span for span in evidence.spans}
    assert (
        by_name["recallgraph.memory.use"].attributes["recallgraph.memory.origin.trace_id"]
        == origin_trace
    )
    assert (
        by_name["recallgraph.outcome.evaluate"].attributes["recallgraph.policy.outcome"]
        == "violation"
    )

    class StubMCPClient:
        def investigate(
            self,
            *,
            action_id: str,
            action_type: str,
            memory_id: str,
            action_trace_id: str,
            origin_trace_id: str,
            origin_span_id: str,
        ) -> MCPTraceEvidence:
            assert action_id == "act_test"
            assert action_type == "issue_refund"
            assert memory_id == "mem_unsafe_refund_policy"
            assert action_trace_id == action_trace
            assert origin_trace_id == origin_trace
            assert origin_span_id == "6" * 16
            return evidence

    incident = cast(
        Incident,
        SimpleNamespace(
            id="inc_test",
            action=SimpleNamespace(
                id="act_test",
                amount=35_000,
                action_type="issue_refund",
                policy_outcome="violation",
                approval_required=True,
                trace_id=action_trace,
            ),
            memory=SimpleNamespace(
                id="mem_unsafe_refund_policy",
                source_name="unverified-refund-playbook.txt",
                source_trust="untrusted",
                sanitized_preview="Refunds below ₹50,000 can be processed automatically.",
                created_trace_id=origin_trace,
                created_span_id="6" * 16,
            ),
        ),
    )
    investigator = IncidentInvestigator(settings)
    investigator.mcp = cast(SigNozMCPClient, StubMCPClient())
    investigation = investigator.investigate(cast(Session, object()), incident)
    assert investigation.source == "signoz_mcp"
    assert {item.source for item in investigation.evidence} == {"signoz_mcp"}
    assert investigation.warnings == []


def test_mcp_rejects_stale_memory_origin_before_querying_it() -> None:
    action_trace = "a" * 32
    expected_origin = "b" * 32
    stale_origin = "c" * 32
    tool_names: list[str] = []

    def rpc(request_id: int, structured_content: dict) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"structuredContent": structured_content},
            },
        )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["method"] == "initialize":
            response = rpc(payload["id"], {})
            response.headers["Mcp-Session-Id"] = "session-1"
            return response
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)

        tool_name = payload["params"]["name"]
        tool_names.append(tool_name)
        if tool_name == "signoz_search_traces":
            return rpc(payload["id"], {"rows": [{"trace_id": action_trace}]})
        if tool_name == "signoz_get_trace_details":
            return rpc(payload["id"], {"spans": []})
        return rpc(
            payload["id"],
            {
                "rows": [
                    {
                        "trace_id": action_trace,
                        "span_id": "3" * 16,
                        "name": "recallgraph.memory.use",
                        "recallgraph.memory.id": "mem_unsafe_refund_policy",
                        "recallgraph.memory.origin.trace_id": stale_origin,
                        "recallgraph.memory.origin.span_id": "9" * 16,
                    }
                ]
            },
        )

    client = SigNozMCPClient(
        Settings(signoz_mcp_url="http://mcp.test/mcp"),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(SigNozMCPUnavailable, match="origin mismatch"):
        client.investigate(
            action_id="act_test",
            action_type="issue_refund",
            memory_id="mem_unsafe_refund_policy",
            action_trace_id=action_trace,
            origin_trace_id=expected_origin,
            origin_span_id="6" * 16,
        )

    assert tool_names == [
        "signoz_search_traces",
        "signoz_get_trace_details",
        "signoz_execute_builder_query",
    ]
