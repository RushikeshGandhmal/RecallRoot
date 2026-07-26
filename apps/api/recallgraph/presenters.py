from __future__ import annotations

from recallgraph.agent.refund_agent import AgentExecution
from recallgraph.graph.risk import RiskAssessment
from recallgraph.memory.models import Action, Incident, MemoryRecord
from recallgraph.memory.repository import normalize_datetime
from recallgraph.schemas import (
    ActionView,
    AgentRunView,
    IncidentView,
    MemoryView,
    RiskFactorView,
    RiskView,
)


def present_memory(memory: MemoryRecord) -> MemoryView:
    return MemoryView(
        id=memory.id,
        content=memory.content,
        sanitized_preview=memory.sanitized_preview,
        content_hash=memory.content_hash,
        source_type=memory.source_type,
        source_name=memory.source_name,
        source_trust=memory.source_trust,
        status=memory.status,
        retrieval_count=memory.retrieval_count,
        created_at=normalize_datetime(memory.created_at),
        created_trace_id=memory.created_trace_id,
        created_span_id=memory.created_span_id,
    )


def present_action(action: Action) -> ActionView:
    return ActionView(
        id=action.id,
        type=action.action_type,
        amount=action.amount,
        customer_id=action.customer_id,
        sensitivity=action.sensitivity,
        approval_required=action.approval_required,
        approval_present=action.approval_present,
        policy_outcome=action.policy_outcome,
        trace_id=action.trace_id,
        span_id=action.span_id,
        result=action.result,
    )


def present_risk(risk: RiskAssessment) -> RiskView:
    return RiskView(
        score=risk.score,
        level=risk.level,
        factors=[
            RiskFactorView(points=factor.points, label=factor.label, reason=factor.reason)
            for factor in risk.factors
        ],
    )


def present_incident(incident: Incident) -> IncidentView:
    factors = [RiskFactorView.model_validate(item) for item in incident.risk_factors]
    risk = RiskView(score=incident.risk_score, level=incident.risk_level, factors=factors)
    return IncidentView(
        id=incident.id,
        incident_id=incident.id,
        status=incident.status,
        risk_score=incident.risk_score,
        risk_level=incident.risk_level,
        risk=risk,
        policy_outcome=incident.policy_outcome,
        detected_at=normalize_datetime(incident.created_at),
        created_at=normalize_datetime(incident.created_at),
        resolved_at=(
            normalize_datetime(incident.resolved_at) if incident.resolved_at is not None else None
        ),
        run_id=incident.agent_run.id,
        session_id=incident.agent_run.session_id,
        trace_id=incident.agent_run.trace_id,
        action=present_action(incident.action),
        memory=present_memory(incident.memory),
    )


def present_execution(execution: AgentExecution) -> AgentRunView:
    incident = present_incident(execution.incident) if execution.incident else None
    return AgentRunView(
        run_id=execution.run.id,
        session_id=execution.run.session_id,
        trace_id=execution.run.trace_id,
        outcome=execution.run.outcome,
        response=execution.run.response_text,
        action=present_action(execution.action),
        memory=present_memory(execution.memory),
        policy_outcome=execution.action.policy_outcome,
        policy_explanation=execution.policy_explanation,
        decision_rationale=execution.decision_rationale,
        risk_score=execution.risk.score,
        risk_level=execution.risk.level,
        risk=present_risk(execution.risk),
        incident_id=execution.incident.id if execution.incident else None,
        incident=incident,
    )
