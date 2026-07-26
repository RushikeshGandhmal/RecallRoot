from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from sqlalchemy.orm import Session

from recallgraph.config import Settings
from recallgraph.graph.builder import CausalGraphBuilder
from recallgraph.graph.mcp_client import SigNozMCPClient, SigNozMCPUnavailable
from recallgraph.graph.models import (
    CausalGraph,
    EvidenceLink,
    InvestigationResponse,
    SpanEvidence,
)
from recallgraph.memory.models import Incident
from recallgraph.telemetry.metrics import record_investigation_duration


@dataclass(frozen=True, slots=True)
class InvestigationFacts:
    memory_id: str
    source_name: str
    source_trust: str
    sanitized_preview: str
    action_type: str
    policy_outcome: str
    approval_required: bool


class IncidentInvestigator:
    """Produce a constrained explanation from retrieved telemetry facts only."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.builder = CausalGraphBuilder(settings)
        self.mcp = SigNozMCPClient(settings)

    def _mcp_evidence(self, incident: Incident) -> tuple[list[EvidenceLink], InvestigationFacts]:
        result = self.mcp.investigate(
            action_id=incident.action.id,
            action_type=incident.action.action_type,
            memory_id=incident.memory.id,
            action_trace_id=incident.action.trace_id,
            origin_trace_id=incident.memory.created_trace_id,
            origin_span_id=incident.memory.created_span_id,
        )

        def find(
            name: str,
            *,
            trace_id: str,
            attributes: dict[str, object],
            span_id: str | None = None,
            prefix: bool = False,
        ) -> SpanEvidence:
            span = next(
                (
                    item
                    for item in result.spans
                    if (item.name.startswith(name) if prefix else item.name == name)
                    and item.trace_id == trace_id
                    and (span_id is None or item.span_id == span_id)
                    and all(item.attributes.get(key) == value for key, value in attributes.items())
                ),
                None,
            )
            if span is None:
                raise SigNozMCPUnavailable(f"MCP evidence did not include {name}")
            return span

        memory_identity = {"recallgraph.memory.id": incident.memory.id}
        action_identity = {
            **memory_identity,
            "recallgraph.action.id": incident.action.id,
            "recallgraph.action.type": incident.action.action_type,
        }
        write_span = find(
            "recallgraph.memory.write",
            trace_id=incident.memory.created_trace_id,
            span_id=incident.memory.created_span_id,
            attributes=memory_identity,
        )
        use_span = find(
            "recallgraph.memory.use",
            trace_id=incident.action.trace_id,
            attributes={
                **memory_identity,
                "recallgraph.memory.origin.trace_id": incident.memory.created_trace_id,
                "recallgraph.memory.origin.span_id": incident.memory.created_span_id,
            },
        )
        tool_span = find(
            "execute_tool ",
            trace_id=incident.action.trace_id,
            attributes=action_identity,
            prefix=True,
        )
        outcome_span = find(
            "recallgraph.outcome.evaluate",
            trace_id=incident.action.trace_id,
            attributes=action_identity,
        )
        items = [
            (write_span, "Memory-write trace", result.origin_url),
            (use_span, "Linked memory-use trace", result.action_url),
            (tool_span, "Refund tool span", result.action_url),
            (outcome_span, "Policy-evaluation span", result.action_url),
        ]
        evidence = [
            EvidenceLink(
                id=f"mcp:{span.trace_id}:{span.span_id}",
                label=label,
                trace_id=span.trace_id,
                span_id=span.span_id,
                span_name=span.name,
                url=url,
                source="signoz_mcp",
            )
            for span, label, url in items
        ]
        memory_attributes = use_span.attributes
        tool_attributes = tool_span.attributes
        outcome_attributes = outcome_span.attributes
        facts = InvestigationFacts(
            memory_id=str(memory_attributes.get("recallgraph.memory.id") or incident.memory.id),
            source_name=str(
                memory_attributes.get("recallgraph.memory.source.name")
                or incident.memory.source_name
            ),
            source_trust=str(
                memory_attributes.get("recallgraph.memory.source.trust")
                or incident.memory.source_trust
            ),
            sanitized_preview=str(
                memory_attributes.get("recallgraph.memory.sanitized_preview")
                or incident.memory.sanitized_preview
            ),
            action_type=str(
                outcome_attributes.get("recallgraph.action.type")
                or tool_attributes.get("recallgraph.action.type")
                or incident.action.action_type
            ),
            policy_outcome=str(
                outcome_attributes.get("recallgraph.policy.outcome")
                or incident.action.policy_outcome
            ),
            approval_required=bool(
                outcome_attributes.get(
                    "recallgraph.approval.required",
                    incident.action.approval_required,
                )
            ),
        )
        return evidence, facts

    @staticmethod
    def _graph_facts(graph: CausalGraph, incident: Incident) -> InvestigationFacts:
        nodes = {node.type: node for node in graph.nodes}
        source_data = nodes["source"].data
        action_data = nodes["action"].data
        outcome_data = nodes["outcome"].data
        return InvestigationFacts(
            memory_id=incident.memory.id,
            source_name=str(source_data["source_name"]),
            source_trust=str(source_data["source_trust"]),
            sanitized_preview=str(source_data["sanitized_preview"]),
            action_type=str(action_data["action_type"]),
            policy_outcome=str(outcome_data["policy_outcome"]),
            approval_required=incident.action.approval_required,
        )

    def investigate(self, session: Session, incident: Incident) -> InvestigationResponse:
        started = perf_counter()
        try:
            evidence, retrieved = self._mcp_evidence(incident)
            source = "signoz_mcp"
            warnings: list[str] = []
        except SigNozMCPUnavailable as exc:
            graph = self.builder.build(session, incident)
            evidence = graph.evidence
            source = graph.source
            retrieved = self._graph_facts(graph, incident)
            warnings = [f"SigNoz MCP evidence rejected: {exc}", *graph.warnings]
        action = incident.action
        facts = [
            f"Action {action.id} issued a ₹{action.amount:,.0f} refund.",
            f"Memory {retrieved.memory_id} was retrieved before the decision.",
            (
                f"The memory originated in {retrieved.source_name} and was classified "
                f"{retrieved.source_trust}."
            ),
            f"Telemetry preview: {retrieved.sanitized_preview}",
            (
                f"The trusted policy requires approval above "
                f"₹{self.settings.trusted_refund_threshold:,.0f}."
            ),
            f"Independent policy evaluation returned {retrieved.policy_outcome}.",
        ]
        summary = (
            f"The ₹{action.amount:,.0f} refund was automatically issued because the agent "
            f"retrieved {retrieved.memory_id} from an earlier session."
        )
        explanation = (
            f"{summary} Telemetry records that it was written from {retrieved.source_name}, "
            f"an {retrieved.source_trust} source, with the evidence-safe preview: "
            f"“{retrieved.sanitized_preview}” This conflicted with the trusted policy "
            f"requiring manager approval above "
            f"₹{self.settings.trusted_refund_threshold:,.0f}. The conclusion is limited to "
            "the memory-write, linked memory-use, decision, tool, and policy-evaluation "
            "evidence shown below."
        )
        duration_ms = round((perf_counter() - started) * 1000, 2)
        record_investigation_duration(duration_ms, "success")
        return InvestigationResponse(
            incident_id=incident.id,
            summary=summary,
            explanation=explanation,
            source=source,
            evidence=evidence,
            facts=facts,
            duration_ms=duration_ms,
            warnings=warnings,
        )
