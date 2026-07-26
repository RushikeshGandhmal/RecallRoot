from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from recallgraph.config import Settings
from recallgraph.graph.evidence import (
    CausalEvidenceMismatch,
    derive_memory_origin,
    validate_causal_evidence,
)
from recallgraph.graph.models import SpanEvidence
from recallgraph.graph.signoz_client import SigNozClient


class SigNozMCPUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MCPTraceEvidence:
    action_trace_id: str
    origin_trace_id: str
    action_url: str
    origin_url: str
    spans: tuple[SpanEvidence, ...]


class SigNozMCPClient:
    """Minimal MCP Streamable HTTP client for SigNoz's investigation tools."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self._request_id = 0

    @property
    def enabled(self) -> bool:
        return bool(self.settings.signoz_mcp_url)

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
        if not self.enabled:
            raise SigNozMCPUnavailable("SigNoz MCP URL is not configured")
        try:
            safe_action_id = SigNozClient._literal(action_id)
            safe_action_type = SigNozClient._literal(action_type)
            safe_memory_id = SigNozClient._literal(memory_id)
            safe_action_trace_id = SigNozClient._literal(action_trace_id)
            safe_origin_trace_id = SigNozClient._literal(origin_trace_id)
            safe_origin_span_id = SigNozClient._literal(origin_span_id)
        except ValueError as exc:
            raise SigNozMCPUnavailable(str(exc)) from exc
        headers = {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
        }
        if self.settings.signoz_mcp_api_key:
            headers["SIGNOZ-API-KEY"] = self.settings.signoz_mcp_api_key
            headers["authorization"] = f"Bearer {self.settings.signoz_mcp_api_key}"

        try:
            with httpx.Client(
                headers=headers,
                timeout=self.settings.signoz_timeout_seconds,
                transport=self.transport,
            ) as client:
                session_id = self._initialize(client)
                action_search = self._call_tool(
                    client,
                    session_id,
                    "signoz_search_traces",
                    {
                        "filter": f"recallgraph.action.id = '{safe_action_id}'",
                        "timeRange": "24h",
                        "limit": 100,
                    },
                )
                resolved_action_trace_id = self._trace_id(action_search)
                if resolved_action_trace_id != safe_action_trace_id:
                    raise SigNozMCPUnavailable(
                        "SigNoz MCP action trace mismatch: "
                        f"expected {safe_action_trace_id}, observed {resolved_action_trace_id}"
                    )
                action_details = self._call_tool(
                    client,
                    session_id,
                    "signoz_get_trace_details",
                    {
                        "traceId": resolved_action_trace_id,
                        "timeRange": "24h",
                        "includeSpans": True,
                    },
                )
                action_builder = self._call_tool(
                    client,
                    session_id,
                    "signoz_execute_builder_query",
                    {"query": self._trace_builder_query(resolved_action_trace_id)},
                )
                action_spans = SigNozClient._deduplicate(
                    [
                        *SigNozClient._normalize_spans(action_details),
                        *SigNozClient._normalize_spans(action_builder),
                    ]
                )
                observed_origin = derive_memory_origin(
                    action_spans,
                    action_trace_id=safe_action_trace_id,
                    memory_id=safe_memory_id,
                )
                expected_origin = (safe_origin_trace_id, safe_origin_span_id)
                if observed_origin != expected_origin:
                    raise CausalEvidenceMismatch(
                        "memory-use origin mismatch: "
                        f"expected {expected_origin[0]}/{expected_origin[1]}, "
                        f"observed {observed_origin[0]}/{observed_origin[1]}"
                    )
                origin_details = self._call_tool(
                    client,
                    session_id,
                    "signoz_get_trace_details",
                    {
                        "traceId": observed_origin[0],
                        "timeRange": "24h",
                        "includeSpans": True,
                    },
                )
                origin_builder = self._call_tool(
                    client,
                    session_id,
                    "signoz_execute_builder_query",
                    {"query": self._trace_builder_query(observed_origin[0])},
                )
        except (
            CausalEvidenceMismatch,
            httpx.HTTPError,
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            raise SigNozMCPUnavailable(f"SigNoz MCP investigation failed: {exc}") from exc

        spans = SigNozClient._deduplicate(
            [
                *action_spans,
                *SigNozClient._normalize_spans(origin_details),
                *SigNozClient._normalize_spans(origin_builder),
            ]
        )
        try:
            validate_causal_evidence(
                spans,
                action_id=safe_action_id,
                action_type=safe_action_type,
                memory_id=safe_memory_id,
                action_trace_id=safe_action_trace_id,
                origin_trace_id=safe_origin_trace_id,
                origin_span_id=safe_origin_span_id,
            )
        except CausalEvidenceMismatch as exc:
            raise SigNozMCPUnavailable(f"SigNoz MCP causal evidence rejected: {exc}") from exc

        signoz = SigNozClient(self.settings)
        return MCPTraceEvidence(
            action_trace_id=resolved_action_trace_id,
            origin_trace_id=observed_origin[0],
            # MCP runs inside Foundry's Docker network and may return an
            # internal service URL. Always build operator links from the
            # configured browser-facing SigNoz URL.
            action_url=signoz.trace_url(resolved_action_trace_id),
            origin_url=signoz.trace_url(observed_origin[0]),
            spans=tuple(spans),
        )

    def _trace_builder_query(self, trace_id: str) -> dict[str, Any]:
        end = datetime.now(UTC)
        start = end - timedelta(hours=self.settings.signoz_query_lookback_hours)
        return {
            "schemaVersion": "v1",
            "start": int(start.timestamp() * 1000),
            "end": int(end.timestamp() * 1000),
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
                            "filter": {"expression": f"trace_id = '{trace_id}'"},
                            "selectFields": SigNozClient.trace_select_fields(),
                        },
                    }
                ]
            },
            "formatOptions": {"formatTableResultForUI": False, "fillGaps": False},
            "variables": {},
        }

    def _initialize(self, client: httpx.Client) -> str | None:
        response, payload = self._post(
            client,
            None,
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "recallroot-api", "version": "0.1.0"},
                },
            },
        )
        if "error" in payload:
            raise SigNozMCPUnavailable(str(payload["error"]))
        session_id = response.headers.get("Mcp-Session-Id")
        self._post(
            client,
            session_id,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            allow_empty=True,
        )
        return session_id

    def _call_tool(
        self,
        client: httpx.Client,
        session_id: str | None,
        name: str,
        arguments: dict[str, Any],
    ) -> Any:
        _, payload = self._post(
            client,
            session_id,
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
        )
        if "error" in payload:
            raise SigNozMCPUnavailable(str(payload["error"]))
        result = payload.get("result", {})
        if result.get("isError"):
            raise SigNozMCPUnavailable(f"SigNoz MCP tool {name} returned an error")
        if "structuredContent" in result:
            return result["structuredContent"]
        content = result.get("content", [])
        decoded: list[Any] = []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            text = block.get("text", "")
            try:
                decoded.append(json.loads(text))
            except (json.JSONDecodeError, TypeError):
                decoded.append({"text": str(text)})
        if len(decoded) == 1:
            return decoded[0]
        return decoded

    def _post(
        self,
        client: httpx.Client,
        session_id: str | None,
        payload: dict[str, Any],
        *,
        allow_empty: bool = False,
    ) -> tuple[httpx.Response, dict[str, Any]]:
        headers = {"Mcp-Session-Id": session_id} if session_id else None
        response = client.post(self.settings.signoz_mcp_url or "", headers=headers, json=payload)
        response.raise_for_status()
        if not response.content and allow_empty:
            return response, {}
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            messages = []
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    try:
                        messages.append(json.loads(line.removeprefix("data:").strip()))
                    except json.JSONDecodeError:
                        continue
            if not messages:
                raise SigNozMCPUnavailable("MCP stream did not contain a JSON-RPC message")
            return response, messages[-1]
        parsed = response.json()
        if not isinstance(parsed, dict):
            raise SigNozMCPUnavailable("MCP response was not a JSON-RPC object")
        return response, parsed

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    @classmethod
    def _trace_id(cls, payload: Any) -> str:
        for item in cls._walk(payload):
            if isinstance(item, dict):
                for key in ("trace_id", "traceId", "traceID"):
                    value = item.get(key)
                    if isinstance(value, str) and len(value) == 32:
                        return value
        raise SigNozMCPUnavailable("SigNoz MCP search returned no trace ID")

    @classmethod
    def _walk(cls, value: Any):
        yield value
        if isinstance(value, dict):
            for child in value.values():
                yield from cls._walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from cls._walk(child)
