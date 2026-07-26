from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GraphModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceLink(GraphModel):
    id: str
    label: str
    trace_id: str
    span_id: str | None = None
    span_name: str | None = None
    url: str
    source: Literal["signoz_mcp", "signoz", "local_evidence"]


class GraphNode(GraphModel):
    id: str
    type: str
    label: str
    data: dict[str, Any]
    evidence: list[EvidenceLink] = Field(default_factory=list)


class GraphEdge(GraphModel):
    id: str
    source: str
    target: str
    type: str
    label: str
    animated: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class CausalGraph(GraphModel):
    incident_id: str
    source: Literal["signoz", "local_evidence"]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    evidence: list[EvidenceLink]
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime


class InvestigationResponse(GraphModel):
    incident_id: str
    summary: str
    explanation: str
    source: Literal["signoz_mcp", "signoz", "local_evidence"]
    evidence: list[EvidenceLink]
    facts: list[str]
    duration_ms: float
    warnings: list[str] = Field(default_factory=list)


class SpanEvidence(BaseModel):
    model_config = ConfigDict(extra="allow")

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    timestamp: datetime | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    links: list[dict[str, Any]] = Field(default_factory=list)


class EvidenceBundle(BaseModel):
    spans: list[SpanEvidence]
    source: Literal["signoz", "local_evidence"]
    warnings: list[str] = Field(default_factory=list)
