from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from recallgraph.memory.models import MemoryRecord, utc_now
from recallgraph.memory.repository import MemoryRepository


@dataclass(frozen=True, slots=True)
class RetrievedMemory:
    memory: MemoryRecord
    rank: int
    reason: str


def select_refund_policy(session: Session, user_key: str) -> MemoryRecord:
    candidates = MemoryRepository(session).active_for_user(user_key)
    refund_candidates = [
        memory
        for memory in candidates
        if "refund" in memory.content.casefold() or "refund" in memory.source_name.casefold()
    ]
    if not refund_candidates:
        raise LookupError("No active refund policy memory is available")
    return refund_candidates[0]


def mark_retrieved(session: Session, memory: MemoryRecord) -> RetrievedMemory:
    memory.retrieval_count += 1
    memory.last_retrieved_at = utc_now()
    session.flush()
    return RetrievedMemory(
        memory=memory,
        rank=1,
        reason="Most recent active memory matching the refund policy request",
    )


def retrieve_refund_policy(session: Session, user_key: str) -> RetrievedMemory:
    memory = select_refund_policy(session, user_key)

    return mark_retrieved(session, memory)
