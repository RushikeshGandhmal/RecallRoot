from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from recallgraph.config import Settings
from recallgraph.graph.evidence import CausalEvidenceMismatch, validate_causal_evidence
from recallgraph.graph.models import (
    CausalGraph,
    EvidenceBundle,
    EvidenceLink,
    GraphEdge,
    GraphNode,
    SpanEvidence,
)
from recallgraph.graph.signoz_client import SigNozClient, SigNozUnavailable
from recallgraph.memory.models import Incident, TelemetrySpan
from recallgraph.telemetry.attributes import SCENARIO
from recallgraph.telemetry.metrics import record_causal_depth


def deduplicate_nodes(nodes: Iterable[GraphNode]) -> list[GraphNode]:
    unique: dict[str, GraphNode] = {}
    for node in nodes:
        unique[node.id] = node
    return list(unique.values())


class CausalGraphBuilder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.signoz = SigNozClient(settings)

    def build(self, session: Session, incident: Incident) -> CausalGraph:
        warning: str | None = None
        try:
            bundle = self.signoz.fetch_causal_evidence(
                action_id=incident.action.id,
                action_type=incident.action.action_type,
                memory_id=incident.memory.id,
                action_trace_id=incident.action.trace_id,
                origin_trace_id=incident.memory.created_trace_id,
                origin_span_id=incident.memory.created_span_id,
            )
        except (SigNozUnavailable, ValueError) as exc:
            warning = f"Live SigNoz causal evidence rejected; using validated local evidence: {exc}"
            bundle = self._local_bundle(session, incident)

        graph = self._assemble(incident, bundle)
        if warning:
            graph.warnings.append(warning)
        record_causal_depth(7, SCENARIO)
        return graph

    def _local_bundle(self, session: Session, incident: Incident) -> EvidenceBundle:
        trace_ids = [incident.action.trace_id, incident.memory.created_trace_id]
        statement = (
            select(TelemetrySpan)
            .where(TelemetrySpan.trace_id.in_(trace_ids))
            .order_by(TelemetrySpan.started_at.asc())
        )
        local_spans = session.scalars(statement)
        spans = [
            SpanEvidence(
                trace_id=span.trace_id,
                span_id=span.span_id,
                parent_span_id=span.parent_span_id,
                name=span.name,
                timestamp=span.started_at,
                attributes=span.attributes,
                links=span.links,
            )
            for span in local_spans
        ]
        try:
            validate_causal_evidence(
                spans,
                action_id=incident.action.id,
                action_type=incident.action.action_type,
                memory_id=incident.memory.id,
                action_trace_id=incident.action.trace_id,
                origin_trace_id=incident.memory.created_trace_id,
                origin_span_id=incident.memory.created_span_id,
            )
        except CausalEvidenceMismatch as exc:
            raise RuntimeError(f"Local causal evidence integrity failure: {exc}") from exc
        return EvidenceBundle(
            spans=spans,
            source="local_evidence",
            warnings=[
                "SigNoz was unavailable or incomplete; graph reconstructed from durable "
                "OpenTelemetry-shaped evidence."
            ],
        )

    @staticmethod
    def _span(
        bundle: EvidenceBundle,
        name: str,
        *,
        trace_id: str,
        span_id: str | None = None,
        attributes: dict[str, object] | None = None,
        prefix: bool = False,
    ) -> SpanEvidence | None:
        expected_attributes = attributes or {}
        return next(
            (
                span
                for span in bundle.spans
                if span.trace_id == trace_id
                and (span.name.startswith(name) if prefix else span.name == name)
                and (span_id is None or span.span_id == span_id)
                and all(
                    span.attributes.get(key) == value for key, value in expected_attributes.items()
                )
            ),
            None,
        )

    def _link(
        self,
        bundle: EvidenceBundle,
        span: SpanEvidence | None,
        label: str,
    ) -> list[EvidenceLink]:
        if span is None:
            return []
        return [
            EvidenceLink(
                id=f"evidence:{span.trace_id}:{span.span_id}",
                label=label,
                trace_id=span.trace_id,
                span_id=span.span_id,
                span_name=span.name,
                url=self.signoz.trace_url(span.trace_id),
                source=bundle.source,
            )
        ]

    @staticmethod
    def _timestamp(span: SpanEvidence | None) -> str | None:
        return span.timestamp.isoformat() if span and span.timestamp else None

    def _assemble(self, incident: Incident, bundle: EvidenceBundle) -> CausalGraph:
        memory = incident.memory
        action = incident.action
        memory_identity = {"recallgraph.memory.id": memory.id}
        action_identity = {
            **memory_identity,
            "recallgraph.action.id": action.id,
            "recallgraph.action.type": action.action_type,
        }
        ingest = self._span(
            bundle,
            "ingest_source",
            trace_id=memory.created_trace_id,
            attributes={
                "recallgraph.memory.source.name": memory.source_name,
                "recallgraph.memory.source.trust": memory.source_trust,
            },
        )
        write = self._span(
            bundle,
            "recallgraph.memory.write",
            trace_id=memory.created_trace_id,
            span_id=memory.created_span_id,
            attributes=memory_identity,
        )
        use = self._span(
            bundle,
            "recallgraph.memory.use",
            trace_id=action.trace_id,
            attributes={
                **memory_identity,
                "recallgraph.memory.origin.trace_id": memory.created_trace_id,
                "recallgraph.memory.origin.span_id": memory.created_span_id,
            },
        )
        decision = self._span(
            bundle,
            "agent.decision",
            trace_id=action.trace_id,
            attributes=action_identity,
        )
        tool = self._span(
            bundle,
            "execute_tool ",
            trace_id=action.trace_id,
            attributes=action_identity,
            prefix=True,
        )
        outcome = self._span(
            bundle,
            "recallgraph.outcome.evaluate",
            trace_id=action.trace_id,
            attributes=action_identity,
        )

        source_node = GraphNode(
            id=f"source:{memory.id}",
            type="source",
            label=memory.source_name,
            data={
                "title": "Untrusted external note",
                "source_name": memory.source_name,
                "source_type": memory.source_type,
                "source_trust": memory.source_trust,
                "content_hash": memory.content_hash,
                "sanitized_preview": memory.sanitized_preview,
                "timestamp": self._timestamp(ingest or write),
            },
            evidence=self._link(bundle, ingest or write, "Source ingestion trace"),
        )
        write_node = GraphNode(
            id=f"write:{memory.created_span_id}",
            type="memory_write",
            label="Memory written in Session A",
            data={
                "title": "Durable memory write",
                "memory_id": memory.id,
                "operation": "write",
                "trace_id": memory.created_trace_id,
                "span_id": memory.created_span_id,
                "timestamp": self._timestamp(write),
            },
            evidence=self._link(bundle, write, "Memory-write span"),
        )
        memory_node = GraphNode(
            id=f"memory:{memory.id}",
            type="memory",
            label=memory.id,
            data={
                "title": "Durable memory record",
                "memory_id": memory.id,
                "status": memory.status,
                "source_trust": memory.source_trust,
                "retrieval_count": memory.retrieval_count,
                "timestamp": self._timestamp(write),
            },
            evidence=self._link(bundle, write, "Memory origin trace"),
        )
        use_node = GraphNode(
            id=f"use:{use.span_id if use else action.id}",
            type="memory_use",
            label="Memory retrieved in Session B",
            data={
                "title": "Cross-session memory use",
                "memory_id": memory.id,
                "origin_trace_id": memory.created_trace_id,
                "origin_span_id": memory.created_span_id,
                "has_otel_span_link": bool(use and use.links),
                "timestamp": self._timestamp(use),
            },
            evidence=self._link(bundle, use, "Memory-use span"),
        )
        decision_label = (
            "Approval skipped" if action.action_type == "issue_refund" else "Approval requested"
        )
        decision_node = GraphNode(
            id=f"decision:{decision.span_id if decision else action.id}",
            type="decision",
            label=decision_label,
            data={
                "title": "Agent policy decision",
                "action_type": action.action_type,
                "approval_required": action.approval_required,
                "approval_present": action.approval_present,
                "timestamp": self._timestamp(decision),
            },
            evidence=self._link(bundle, decision, "Decision span"),
        )
        action_node = GraphNode(
            id=f"action:{action.id}",
            type="action",
            label=f"{action.action_type} · ₹{action.amount:,.0f}",
            data={
                "title": "Sensitive tool execution",
                "action_id": action.id,
                "action_type": action.action_type,
                "amount": action.amount,
                "sensitivity": action.sensitivity,
                "tool_status": action.result.get("status"),
                "timestamp": self._timestamp(tool),
            },
            evidence=self._link(bundle, tool, "Tool execution span"),
        )
        outcome_node = GraphNode(
            id=f"outcome:{outcome.span_id if outcome else action.id}",
            type="outcome",
            label=(
                "Policy violation detected"
                if action.policy_outcome == "violation"
                else "Trusted policy passed"
            ),
            data={
                "title": "Independent policy evaluation",
                "policy_outcome": action.policy_outcome,
                "risk_score": incident.risk_score,
                "risk_level": incident.risk_level,
                "timestamp": self._timestamp(outcome),
            },
            evidence=self._link(bundle, outcome, "Policy-evaluation span"),
        )

        nodes = deduplicate_nodes(
            [
                source_node,
                write_node,
                memory_node,
                use_node,
                decision_node,
                action_node,
                outcome_node,
            ]
        )
        edges = [
            GraphEdge(
                id="edge:source-write",
                source=source_node.id,
                target=write_node.id,
                type="parent_child",
                label="ingested",
            ),
            GraphEdge(
                id="edge:write-memory",
                source=write_node.id,
                target=memory_node.id,
                type="parent_child",
                label="created",
            ),
            GraphEdge(
                id="edge:memory-use",
                source=memory_node.id,
                target=use_node.id,
                type="cross_trace_causal",
                label="OTel Span Link",
                animated=True,
                data={
                    "origin_trace_id": memory.created_trace_id,
                    "origin_span_id": memory.created_span_id,
                },
            ),
            GraphEdge(
                id="edge:use-decision",
                source=use_node.id,
                target=decision_node.id,
                type="parent_child",
                label="influenced",
            ),
            GraphEdge(
                id="edge:decision-action",
                source=decision_node.id,
                target=action_node.id,
                type="parent_child",
                label="selected",
            ),
            GraphEdge(
                id="edge:action-outcome",
                source=action_node.id,
                target=outcome_node.id,
                type="parent_child",
                label="evaluated",
            ),
        ]
        evidence_by_id: dict[str, EvidenceLink] = {}
        for node in nodes:
            for item in node.evidence:
                evidence_by_id[item.id] = item
        return CausalGraph(
            incident_id=incident.id,
            source=bundle.source,
            nodes=nodes,
            edges=edges,
            evidence=list(evidence_by_id.values()),
            warnings=list(bundle.warnings),
            generated_at=datetime.now(UTC),
        )
