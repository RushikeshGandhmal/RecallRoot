from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from recallgraph.memory.models import MemoryRecord
from recallgraph.memory.repository import normalize_datetime


@dataclass(frozen=True, slots=True)
class RiskFactor:
    points: int
    label: str
    reason: str


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    score: int
    level: str
    factors: tuple[RiskFactor, ...]


def risk_level(score: int) -> str:
    if score < 30:
        return "low"
    if score < 60:
        return "medium"
    if score < 80:
        return "high"
    return "critical"


def _is_stale_or_unverifiable(memory: MemoryRecord, now: datetime) -> bool:
    if memory.expires_at is not None and normalize_datetime(memory.expires_at) <= now:
        return True
    # External policy instructions without a trusted freshness guarantee are
    # conservatively classified as stale/unverifiable.
    return memory.source_type == "external_document" and memory.source_trust == "untrusted"


def calculate_risk(
    memory: MemoryRecord,
    *,
    sensitive_action_influenced: bool,
    required_approval_missing: bool,
    now: datetime | None = None,
) -> RiskAssessment:
    current_time = now or datetime.now(UTC)
    factors: list[RiskFactor] = []
    if memory.source_trust == "untrusted":
        factors.append(RiskFactor(35, "Untrusted source", "Memory came from an untrusted source"))
    if _is_stale_or_unverifiable(memory, current_time):
        factors.append(
            RiskFactor(
                20,
                "Stale policy",
                "External policy had no verified freshness guarantee",
            )
        )
    if sensitive_action_influenced:
        factors.append(
            RiskFactor(20, "Sensitive refund action", "Memory influenced a refund execution")
        )
    if required_approval_missing:
        factors.append(
            RiskFactor(15, "Required approval missing", "Trusted policy required approval")
        )

    repeated_retrievals = max(0, memory.retrieval_count - 1)
    repeated_points = min(10, repeated_retrievals * 5)
    if repeated_points:
        factors.append(
            RiskFactor(
                repeated_points,
                "Repeated retrieval",
                f"Memory was retrieved {memory.retrieval_count} times",
            )
        )

    score = min(100, sum(factor.points for factor in factors))
    return RiskAssessment(score=score, level=risk_level(score), factors=tuple(factors))
