from __future__ import annotations

from sqlalchemy.orm import Session

from recallgraph.memory.models import MemoryRecord
from recallgraph.memory.repository import MemoryRepository
from recallgraph.telemetry.attributes import SCENARIO
from recallgraph.telemetry.logging import emit_event
from recallgraph.telemetry.tracing import recorded_span


class MemoryNotFoundError(LookupError):
    pass


def quarantine_memory(session: Session, memory_id: str) -> tuple[MemoryRecord, bool]:
    repository = MemoryRepository(session)
    memory = repository.get(memory_id)
    if memory is None:
        raise MemoryNotFoundError(f"Memory {memory_id} was not found")
    already_quarantined = memory.status == "quarantined"
    with recorded_span(
        session,
        "recallgraph.memory.quarantine",
        attributes={
            "recallgraph.scenario": SCENARIO,
            "recallgraph.memory.id": memory.id,
            "recallgraph.memory.operation": "quarantine",
            "recallgraph.memory.status": "quarantined",
            "recallgraph.memory.source.trust": memory.source_trust,
            "recallgraph.remediation.type": "memory_quarantine",
            "recallgraph.remediation.idempotent": already_quarantined,
        },
    ):
        memory = repository.quarantine(memory_id)
        assert memory is not None
        emit_event(
            session,
            "memory_quarantined",
            memory_id=memory.id,
            source_name=memory.source_name,
            source_trust=memory.source_trust,
            already_quarantined=already_quarantined,
        )
    return memory, already_quarantined
