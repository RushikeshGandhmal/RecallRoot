from __future__ import annotations

from dataclasses import dataclass

from opentelemetry.trace import Link
from sqlalchemy.orm import Session

from recallgraph.agent.decision_provider import (
    DecisionProvider,
    build_decision_provider,
    decision_request_attributes,
    decision_span_name,
)
from recallgraph.agent.policy_engine import evaluate_trusted_policy
from recallgraph.agent.prompts import approval_requested_response, refund_issued_response
from recallgraph.agent.tools import issue_refund, request_manager_approval
from recallgraph.config import Settings
from recallgraph.graph.risk import RiskAssessment, calculate_risk
from recallgraph.ids import new_id
from recallgraph.memory.models import (
    Action,
    AgentRun,
    Incident,
    MemoryInfluence,
    MemoryRecord,
    utc_now,
)
from recallgraph.memory.retrieval import mark_retrieved, select_refund_policy
from recallgraph.telemetry.attributes import SCENARIO, amount_bucket, memory_age_seconds
from recallgraph.telemetry.logging import emit_event
from recallgraph.telemetry.metrics import (
    count_memory_use,
    count_policy_violation,
    count_sensitive_action,
    record_risk_score,
)
from recallgraph.telemetry.tracing import current_span_ids, persisted_link, recorded_span


@dataclass(frozen=True, slots=True)
class RefundCommand:
    customer_id: str
    amount: float
    reason: str
    user_key: str = "demo_user"


@dataclass(frozen=True, slots=True)
class AgentExecution:
    run: AgentRun
    action: Action
    memory: MemoryRecord
    incident: Incident | None
    risk: RiskAssessment
    decision_rationale: str
    policy_explanation: str


class RefundAgent:
    def __init__(
        self,
        settings: Settings,
        *,
        decision_provider: DecisionProvider | None = None,
    ) -> None:
        self.settings = settings
        self.decision_provider = decision_provider or build_decision_provider(settings)

    def run(
        self,
        session: Session,
        command: RefundCommand,
        *,
        session_id: str | None = None,
        is_replay: bool = False,
        original_run_id: str | None = None,
        links: list[Link] | None = None,
        create_incident: bool = True,
    ) -> AgentExecution:
        run_id = new_id("run")
        action_id = new_id("act")
        actual_session_id = session_id or new_id("sess")
        started_at = utc_now()

        root_attributes: dict[str, object] = {
            "recallgraph.session.id": actual_session_id,
            "recallgraph.agent.run_id": run_id,
            "recallgraph.scenario": SCENARIO,
            "gen_ai.agent.name": "support-refund-agent",
            "recallgraph.replay": is_replay,
        }
        with recorded_span(
            session,
            "invoke_agent support-refund-agent",
            attributes=root_attributes,
            links=links,
        ):
            run_trace_id, _, _ = current_span_ids()

            with recorded_span(
                session,
                "parse_request",
                attributes={
                    **root_attributes,
                    "recallgraph.action.amount_bucket": amount_bucket(command.amount),
                    "recallgraph.request.type": "refund",
                },
            ):
                if command.amount <= 0:
                    raise ValueError("Refund amount must be positive")

            memory = select_refund_policy(session, command.user_key)
            origin_link = persisted_link(
                memory.created_trace_id,
                memory.created_span_id,
                memory.created_trace_flags,
            )
            memory_attributes: dict[str, object] = {
                **root_attributes,
                "recallgraph.memory.id": memory.id,
                "recallgraph.memory.operation": "use",
                "recallgraph.memory.status": memory.status,
                "recallgraph.memory.source.type": memory.source_type,
                "recallgraph.memory.source.trust": memory.source_trust,
                "recallgraph.memory.age_seconds": memory_age_seconds(memory.created_at),
                "recallgraph.memory.origin.trace_id": memory.created_trace_id,
                "recallgraph.memory.origin.span_id": memory.created_span_id,
                "recallgraph.memory.retrieval_rank": 1,
                "recallgraph.memory.content_hash": memory.content_hash,
                "recallgraph.memory.sanitized_preview": memory.sanitized_preview,
                "recallgraph.memory.source.name": memory.source_name,
            }
            with recorded_span(
                session,
                "recallgraph.memory.use",
                attributes=memory_attributes,
                links=[origin_link],
            ):
                retrieved = mark_retrieved(session, memory)
                count_memory_use(memory.source_trust, memory.status)
                emit_event(
                    session,
                    "memory_retrieved",
                    memory_id=memory.id,
                    source_name=memory.source_name,
                    source_trust=memory.source_trust,
                    status=memory.status,
                    retrieval_rank=retrieved.rank,
                )

            with recorded_span(
                session,
                decision_span_name(self.decision_provider),
                attributes={
                    **root_attributes,
                    **decision_request_attributes(self.decision_provider),
                    "recallgraph.memory.id": memory.id,
                    "recallgraph.action.amount_bucket": amount_bucket(command.amount),
                },
            ) as provider_span:
                decision_result = self.decision_provider.decide(memory.content, command.amount)
                decision_result.metadata.apply_to_span(provider_span)

            decision = decision_result.decision
            selected_action = (
                "request_manager_approval" if decision.approval_required else "issue_refund"
            )
            with recorded_span(
                session,
                "agent.decision",
                attributes={
                    **root_attributes,
                    "recallgraph.action.id": action_id,
                    "recallgraph.action.type": selected_action,
                    "recallgraph.action.sensitivity": (
                        "high" if selected_action == "issue_refund" else "guardrail"
                    ),
                    "recallgraph.action.amount_bucket": amount_bucket(command.amount),
                    "recallgraph.approval.required_by_memory": decision.approval_required,
                    "recallgraph.memory.id": memory.id,
                    **decision_result.metadata.span_attributes(),
                },
            ):
                emit_event(
                    session,
                    "memory_influenced_decision",
                    memory_id=memory.id,
                    action_id=action_id,
                    action_type=selected_action,
                    source_trust=memory.source_trust,
                )
                emit_event(
                    session,
                    "sensitive_action_selected",
                    action_id=action_id,
                    action_type=selected_action,
                    amount_bucket=amount_bucket(command.amount),
                )

            tool_attributes: dict[str, object] = {
                **root_attributes,
                "recallgraph.action.id": action_id,
                "recallgraph.action.type": selected_action,
                "recallgraph.action.sensitivity": (
                    "high" if selected_action == "issue_refund" else "guardrail"
                ),
                "recallgraph.action.amount_bucket": amount_bucket(command.amount),
                "recallgraph.memory.id": memory.id,
                "tool.name": selected_action,
            }
            with recorded_span(
                session,
                f"execute_tool {selected_action}",
                attributes=tool_attributes,
            ):
                action_trace_id, action_span_id, action_trace_flags = current_span_ids()
                if selected_action == "issue_refund":
                    tool_result = issue_refund(command.amount, command.customer_id)
                    response_text = refund_issued_response(command.amount)
                    outcome = "refund_issued"
                else:
                    tool_result = request_manager_approval(command.amount, command.customer_id)
                    response_text = approval_requested_response(command.amount)
                    outcome = "approval_requested"
                tool_result["decision"] = decision_result.metadata.tool_result()

            evaluation = evaluate_trusted_policy(
                amount=command.amount,
                selected_action=selected_action,
                trusted_threshold=self.settings.trusted_refund_threshold,
            )
            # The independent evaluator reads the trusted policy record as a
            # separate guardrail. This access is intentionally distinct from
            # the agent's operative-memory retrieval.
            trusted_policy = session.get(MemoryRecord, "mem_trusted_refund_policy")
            if trusted_policy is not None:
                trusted_policy.retrieval_count += 1
                trusted_policy.last_retrieved_at = utc_now()
                session.flush()
            risk = calculate_risk(
                memory,
                sensitive_action_influenced=selected_action == "issue_refund",
                required_approval_missing=(
                    evaluation.approval_required
                    and not evaluation.approval_present
                    and selected_action == "issue_refund"
                ),
            )
            outcome_attributes: dict[str, object] = {
                **root_attributes,
                "recallgraph.action.id": action_id,
                "recallgraph.action.type": selected_action,
                "recallgraph.action.sensitivity": (
                    "high" if selected_action == "issue_refund" else "guardrail"
                ),
                "recallgraph.action.amount_bucket": amount_bucket(command.amount),
                "recallgraph.approval.required": evaluation.approval_required,
                "recallgraph.approval.present": evaluation.approval_present,
                "recallgraph.policy.outcome": evaluation.outcome,
                "recallgraph.memory.id": memory.id,
                "recallgraph.risk.score": risk.score,
                "recallgraph.risk.level": risk.level,
            }
            with recorded_span(
                session,
                "recallgraph.outcome.evaluate",
                attributes=outcome_attributes,
            ):
                if evaluation.outcome == "violation":
                    count_policy_violation(selected_action, memory.source_trust)
                    emit_event(
                        session,
                        "policy_violation_detected",
                        action_id=action_id,
                        action_type=selected_action,
                        amount_bucket=amount_bucket(command.amount),
                        memory_source_trust=memory.source_trust,
                        approval_required=evaluation.approval_required,
                        approval_present=evaluation.approval_present,
                    )
                count_sensitive_action(evaluation.outcome)
                record_risk_score(risk.score, memory.source_trust)

            run = AgentRun(
                id=run_id,
                session_id=actual_session_id,
                request_text=(
                    f"Refund request for {command.customer_id}: ₹{command.amount:,.2f}; "
                    f"reason: {command.reason}"
                ),
                request_type="refund",
                customer_id=command.customer_id,
                amount=command.amount,
                reason=command.reason,
                started_at=started_at,
                completed_at=utc_now(),
                trace_id=run_trace_id,
                outcome=outcome,
                response_text=response_text,
                is_replay=is_replay,
                original_run_id=original_run_id,
            )
            action = Action(
                id=action_id,
                agent_run_id=run_id,
                action_type=selected_action,
                amount=command.amount,
                customer_id=command.customer_id,
                sensitivity="high" if selected_action == "issue_refund" else "guardrail",
                approval_required=evaluation.approval_required,
                approval_present=evaluation.approval_present,
                policy_outcome=evaluation.outcome,
                trace_id=action_trace_id,
                span_id=action_span_id,
                trace_flags=action_trace_flags,
                result=tool_result,
            )
            influence = MemoryInfluence(
                id=new_id("inf"),
                agent_run_id=run_id,
                action_id=action_id,
                memory_id=memory.id,
                retrieval_rank=1,
                retrieval_reason=retrieved.reason,
                risk_score=risk.score,
            )
            session.add_all([run, action, influence])
            session.flush()

            incident: Incident | None = None
            if evaluation.outcome == "violation" and create_incident:
                incident = Incident(
                    id=new_id("inc"),
                    action_id=action_id,
                    agent_run_id=run_id,
                    memory_id=memory.id,
                    status="open",
                    risk_score=risk.score,
                    risk_level=risk.level,
                    risk_factors=[
                        {
                            "points": factor.points,
                            "label": factor.label,
                            "reason": factor.reason,
                        }
                        for factor in risk.factors
                    ],
                    policy_outcome=evaluation.outcome,
                )
                session.add(incident)
                session.flush()

        return AgentExecution(
            run=run,
            action=action,
            memory=memory,
            incident=incident,
            risk=risk,
            decision_rationale=decision.rationale,
            policy_explanation=evaluation.explanation,
        )
