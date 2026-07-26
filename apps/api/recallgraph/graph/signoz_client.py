from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from recallgraph.config import Settings
from recallgraph.graph.evidence import (
    CausalEvidenceMismatch,
    derive_memory_origin,
    validate_causal_evidence,
)
from recallgraph.graph.models import EvidenceBundle, SpanEvidence

_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_-]+$")


class SigNozUnavailable(RuntimeError):
    pass


class SigNozClient:
    """Small client for the current SigNoz v5 Query Range trace API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.signoz_api_url)

    def trace_url(self, trace_id: str) -> str:
        return f"{self.settings.signoz_ui_url.rstrip('/')}/trace/{trace_id}"

    @staticmethod
    def _literal(value: str) -> str:
        if not _SAFE_VALUE.fullmatch(value):
            raise ValueError("Telemetry lookup value contains unsupported characters")
        return value

    def _query_body(self, expression: str, *, limit: int = 100) -> dict[str, Any]:
        end = datetime.now(UTC)
        start = end - timedelta(hours=self.settings.signoz_query_lookback_hours)
        return {
            "schemaVersion": "v1",
            "start": int(start.timestamp() * 1000),
            "end": int(end.timestamp() * 1000),
            "requestType": "raw",
            "variables": {},
            "compositeQuery": {
                "queries": [
                    {
                        "type": "builder_query",
                        "spec": {
                            "name": "A",
                            "signal": "traces",
                            "filter": {"expression": expression},
                            "selectFields": self.trace_select_fields(),
                            "order": [
                                {
                                    "key": {"name": "timestamp"},
                                    "direction": "desc",
                                }
                            ],
                            "limit": limit,
                            "offset": 0,
                            "disabled": False,
                            "having": {"expression": ""},
                        },
                    }
                ]
            },
            "formatOptions": {"formatTableResultForUI": False, "fillGaps": False},
        }

    @staticmethod
    def trace_select_fields() -> list[dict[str, str]]:
        span_fields = ("trace_id", "span_id", "parent_span_id", "name", "timestamp")
        tag_fields = {
            "recallgraph.memory.id": "string",
            "recallgraph.memory.operation": "string",
            "recallgraph.memory.source.name": "string",
            "recallgraph.memory.source.trust": "string",
            "recallgraph.memory.sanitized_preview": "string",
            "recallgraph.memory.origin.trace_id": "string",
            "recallgraph.memory.origin.span_id": "string",
            "recallgraph.action.id": "string",
            "recallgraph.action.type": "string",
            "recallgraph.approval.required": "bool",
            "recallgraph.policy.outcome": "string",
        }
        fields = [
            {
                "name": name,
                "fieldDataType": "string",
                "signal": "traces",
                "fieldContext": "span",
            }
            for name in span_fields
        ]
        fields.extend(
            {
                "name": name,
                "fieldDataType": data_type,
                "signal": "traces",
                "fieldContext": "tag",
            }
            for name, data_type in tag_fields.items()
        )
        return fields

    def query_spans(self, expression: str, *, limit: int = 100) -> list[SpanEvidence]:
        if not self.enabled:
            raise SigNozUnavailable("SigNoz API URL is not configured")
        headers = {"content-type": "application/json"}
        if self.settings.signoz_api_key:
            headers["SIGNOZ-API-KEY"] = self.settings.signoz_api_key
        endpoint = (
            f"{self.settings.signoz_api_url.rstrip('/')}"
            f"/{self.settings.signoz_query_path.lstrip('/')}"
        )
        try:
            response = httpx.post(
                endpoint,
                headers=headers,
                json=self._query_body(expression, limit=limit),
                timeout=self.settings.signoz_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SigNozUnavailable(f"SigNoz trace query failed: {exc}") from exc
        return self._normalize_spans(payload)

    def fetch_causal_evidence(
        self,
        *,
        action_id: str,
        action_type: str,
        memory_id: str,
        action_trace_id: str,
        origin_trace_id: str,
        origin_span_id: str,
    ) -> EvidenceBundle:
        safe_action = self._literal(action_id)
        safe_action_type = self._literal(action_type)
        safe_memory = self._literal(memory_id)
        safe_action_trace = self._literal(action_trace_id)
        safe_origin_trace = self._literal(origin_trace_id)
        safe_origin_span = self._literal(origin_span_id)

        action_spans = self.query_spans(f"trace_id = '{safe_action_trace}'")
        try:
            observed_origin = derive_memory_origin(
                action_spans,
                action_trace_id=safe_action_trace,
                memory_id=safe_memory,
            )
            if observed_origin != (safe_origin_trace, safe_origin_span):
                raise CausalEvidenceMismatch(
                    "memory-use origin mismatch: "
                    f"expected {safe_origin_trace}/{safe_origin_span}, "
                    f"observed {observed_origin[0]}/{observed_origin[1]}"
                )
            origin_spans = self.query_spans(f"trace_id = '{observed_origin[0]}'")
            spans = self._deduplicate([*action_spans, *origin_spans])
            validate_causal_evidence(
                spans,
                action_id=safe_action,
                action_type=safe_action_type,
                memory_id=safe_memory,
                action_trace_id=safe_action_trace,
                origin_trace_id=safe_origin_trace,
                origin_span_id=safe_origin_span,
            )
        except CausalEvidenceMismatch as exc:
            raise SigNozUnavailable(f"SigNoz causal evidence rejected: {exc}") from exc
        return EvidenceBundle(spans=spans, source="signoz")

    @staticmethod
    def _deduplicate(spans: list[SpanEvidence]) -> list[SpanEvidence]:
        unique: dict[tuple[str, str], SpanEvidence] = {}
        for span in spans:
            key = (span.trace_id, span.span_id)
            existing = unique.get(key)
            if existing is None:
                unique[key] = span
                continue
            unique[key] = SpanEvidence(
                trace_id=span.trace_id,
                span_id=span.span_id,
                parent_span_id=span.parent_span_id or existing.parent_span_id,
                name=span.name if span.name != "unknown" else existing.name,
                timestamp=span.timestamp or existing.timestamp,
                attributes={**existing.attributes, **span.attributes},
                links=span.links or existing.links,
            )
        return list(unique.values())

    @classmethod
    def _normalize_spans(cls, payload: Any) -> list[SpanEvidence]:
        spans: dict[tuple[str, str], SpanEvidence] = {}
        for row in cls._walk_dicts(payload):
            normalized = cls._normalize_row(row)
            if normalized:
                spans[(normalized.trace_id, normalized.span_id)] = normalized
        return list(spans.values())

    @classmethod
    def _walk_dicts(cls, value: Any) -> Iterator[dict[str, Any]]:
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from cls._walk_dicts(child)
        elif isinstance(value, list):
            for child in value:
                yield from cls._walk_dicts(child)

    @staticmethod
    def _pick(row: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in row and row[key] not in (None, ""):
                return row[key]
        return None

    @classmethod
    def _normalize_row(cls, row: dict[str, Any]) -> SpanEvidence | None:
        trace_id = cls._pick(row, "trace_id", "traceID", "traceId")
        span_id = cls._pick(row, "span_id", "spanID", "spanId")
        if not isinstance(trace_id, str) or not isinstance(span_id, str):
            return None
        if len(trace_id) != 32 or len(span_id) != 16:
            return None
        name = cls._pick(row, "name", "span_name", "spanName", "operationName")
        if name is None and not any(
            key in row for key in ("attributes", "spanAttributes", "tags", "parent_span_id")
        ):
            # Link contexts also contain trace_id/span_id; they are evidence
            # references, not standalone trace rows.
            return None
        attributes: dict[str, Any] = {}
        raw_attributes = cls._pick(row, "attributes", "spanAttributes", "tags")
        if isinstance(raw_attributes, dict):
            attributes.update(raw_attributes)
        elif isinstance(raw_attributes, list):
            for item in raw_attributes:
                if isinstance(item, dict) and "key" in item:
                    attributes[str(item["key"])] = item.get("value")
        for key, value in row.items():
            if key.startswith("recallgraph."):
                attributes[key] = value
        links = row.get("links") if isinstance(row.get("links"), list) else []
        return SpanEvidence(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=cls._pick(row, "parent_span_id", "parentSpanId", "parentSpanID"),
            name=str(name or "unknown"),
            timestamp=cls._pick(row, "timestamp", "start_time", "startTime"),
            attributes=attributes,
            links=links,
        )
