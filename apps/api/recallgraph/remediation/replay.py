from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from recallgraph.agent.refund_agent import AgentExecution, RefundAgent, RefundCommand
from recallgraph.config import Settings
from recallgraph.ids import new_id
from recallgraph.memory.models import Incident, Replay, utc_now
from recallgraph.telemetry.attributes import SCENARIO
from recallgraph.telemetry.logging import emit_event
from recallgraph.telemetry.metrics import count_replay
from recallgraph.telemetry.tracing import current_span_ids, persisted_link, recorded_span


@dataclass(frozen=True, slots=True)
class ReplayExecution:
    replay: Replay
    agent_execution: AgentExecution


class ReplayPreconditionError(RuntimeError):
    """Raised when an incident has not yet been remediated for a safe replay."""


def _side(
    *,
    trace_id: str,
    run_id: str,
    action_id: str,
    memory_id: str,
    memory_status: str,
    source_trust: str,
    decision: str,
    tool: str,
    outcome: str,
    policy_outcome: str,
    risk_score: int,
    risk_level: str,
) -> dict[str, object]:
    return {
        "trace_id": trace_id,
        "run_id": run_id,
        "action_id": action_id,
        "memory_id": memory_id,
        "memory_status": memory_status,
        "source_trust": source_trust,
        "decision": decision,
        "tool": tool,
        "outcome": outcome,
        "policy_outcome": policy_outcome,
        "risk_score": risk_score,
        "risk_level": risk_level,
    }


def replay_incident(
    session: Session,
    settings: Settings,
    incident: Incident,
) -> ReplayExecution:
    original_action = incident.action
    original_run = incident.agent_run
    original_memory = incident.memory
    if original_memory.status != "quarantined":
        raise ReplayPreconditionError(
            f"Quarantine causal memory {original_memory.id} before replaying the incident."
        )
    original_link = persisted_link(
        original_action.trace_id,
        original_action.span_id,
        original_action.trace_flags,
    )
    replay_id = new_id("replay")
    attributes: dict[str, object] = {
        "recallgraph.scenario": SCENARIO,
        "recallgraph.replay.id": replay_id,
        "recallgraph.replay.original_trace_id": original_action.trace_id,
        "recallgraph.replay.original_action_id": original_action.id,
        "recallgraph.remediation.type": "quarantine_and_replay",
    }
    with recorded_span(
        session,
        "recallgraph.replay",
        attributes=attributes,
        links=[original_link],
    ) as replay_span:
        replay_trace_id, _, _ = current_span_ids()
        execution = RefundAgent(settings).run(
            session,
            RefundCommand(
                customer_id=original_run.customer_id,
                amount=original_run.amount,
                reason=original_run.reason,
            ),
            session_id=new_id("sess_replay"),
            is_replay=True,
            original_run_id=original_run.id,
            create_incident=False,
        )
        if execution.memory.source_trust != "trusted" or execution.memory.status != "active":
            raise ReplayPreconditionError(
                "Replay verification requires an active, trusted operative memory."
            )
        improved = (
            original_action.policy_outcome == "violation"
            and execution.action.policy_outcome == "pass"
        )
        result = "improved" if improved else "unchanged"
        memory_quarantined = original_memory.status == "quarantined"
        replay_span.set_attribute("recallgraph.replay.result", result)
        replay_span.set_attribute("recallgraph.replay.trace_id", replay_trace_id)

        before = _side(
            trace_id=original_action.trace_id,
            run_id=original_run.id,
            action_id=original_action.id,
            memory_id=original_memory.id,
            memory_status="active",
            source_trust=original_memory.source_trust,
            decision="auto_refund",
            tool=original_action.action_type,
            outcome=original_run.outcome,
            policy_outcome=original_action.policy_outcome,
            risk_score=incident.risk_score,
            risk_level=incident.risk_level,
        )
        after = _side(
            trace_id=execution.action.trace_id,
            run_id=execution.run.id,
            action_id=execution.action.id,
            memory_id=execution.memory.id,
            memory_status=execution.memory.status,
            source_trust=execution.memory.source_trust,
            decision=(
                "request_approval"
                if execution.action.action_type == "request_manager_approval"
                else "auto_refund"
            ),
            tool=execution.action.action_type,
            outcome=execution.run.outcome,
            policy_outcome=execution.action.policy_outcome,
            risk_score=execution.risk.score,
            risk_level=execution.risk.level,
        )
        verified_at = utc_now()
        causal_memory = {
            "id": original_memory.id,
            "source_trust": original_memory.source_trust,
            "before_status": "active",
            "after_status": original_memory.status,
            "remediation": "quarantine",
        }
        operative_replay_memory = {
            "id": execution.memory.id,
            "source_trust": execution.memory.source_trust,
            "status": execution.memory.status,
        }
        comparison = {
            "before": before,
            "after": after,
            "original": before,
            "replay": after,
            "causal_memory": causal_memory,
            "operative_replay_memory": operative_replay_memory,
            "changed_fields": [
                field
                for field in (
                    "memory_id",
                    "decision",
                    "tool",
                    "outcome",
                    "policy_outcome",
                    "risk_score",
                )
                if before[field] != after[field]
            ],
            "verified_at": verified_at.isoformat(),
        }
        replay = Replay(
            id=replay_id,
            incident_id=incident.id,
            original_action_id=original_action.id,
            original_trace_id=original_action.trace_id,
            replay_run_id=execution.run.id,
            replay_action_id=execution.action.id,
            replay_trace_id=replay_trace_id,
            memory_quarantined=memory_quarantined,
            original_outcome=original_run.outcome,
            replay_outcome=execution.run.outcome,
            result=result,
            comparison=comparison,
            created_at=verified_at,
        )
        session.add(replay)
        if improved:
            incident.status = "resolved"
            incident.resolved_at = utc_now()
        emit_event(
            session,
            "request_replayed",
            replay_id=replay_id,
            incident_id=incident.id,
            result=result,
            memory_quarantined=memory_quarantined,
        )
        if improved:
            emit_event(
                session,
                "replay_improved_outcome",
                replay_id=replay_id,
                original_policy_outcome=original_action.policy_outcome,
                replay_policy_outcome=execution.action.policy_outcome,
            )
        count_replay(result)
        session.flush()
    return ReplayExecution(replay=replay, agent_execution=execution)
