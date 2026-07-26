from __future__ import annotations

from datetime import UTC, datetime

from recallgraph.agent.policy_engine import decide_from_memory, evaluate_trusted_policy
from recallgraph.agent.prompts import TRUSTED_POLICY, UNSAFE_MEMORY
from recallgraph.graph.risk import calculate_risk
from recallgraph.memory.models import MemoryRecord


def memory(*, trust: str = "untrusted", source_type: str = "external_document") -> MemoryRecord:
    return MemoryRecord(
        id="mem_test",
        user_key="demo_user",
        content=UNSAFE_MEMORY,
        content_hash="a" * 64,
        sanitized_preview=UNSAFE_MEMORY,
        source_type=source_type,
        source_name="test.txt",
        source_trust=trust,
        status="active",
        created_at=datetime.now(UTC),
        expires_at=None,
        created_trace_id="a" * 32,
        created_span_id="b" * 16,
        created_trace_flags=1,
        retrieval_count=1,
    )


def test_untrusted_refund_policy_skips_approval() -> None:
    decision = decide_from_memory(UNSAFE_MEMORY, 35_000)
    assert decision.approval_required is False


def test_trusted_refund_policy_requires_approval() -> None:
    decision = decide_from_memory(TRUSTED_POLICY, 35_000)
    assert decision.approval_required is True


def test_independent_policy_detects_successful_but_unsafe_tool_call() -> None:
    evaluation = evaluate_trusted_policy(
        amount=35_000,
        selected_action="issue_refund",
        trusted_threshold=10_000,
    )
    assert evaluation.outcome == "violation"
    assert evaluation.approval_required is True
    assert evaluation.approval_present is False


def test_risk_score_is_transparent_and_critical() -> None:
    assessment = calculate_risk(
        memory(),
        sensitive_action_influenced=True,
        required_approval_missing=True,
    )
    assert assessment.score == 90
    assert assessment.level == "critical"
    assert [(factor.points, factor.label) for factor in assessment.factors] == [
        (35, "Untrusted source"),
        (20, "Stale policy"),
        (20, "Sensitive refund action"),
        (15, "Required approval missing"),
    ]


def test_repeated_retrieval_contribution_is_capped() -> None:
    record = memory(trust="trusted", source_type="system_policy")
    record.retrieval_count = 100
    assessment = calculate_risk(
        record,
        sensitive_action_influenced=False,
        required_approval_missing=False,
    )
    assert assessment.score == 10
    assert assessment.level == "low"
