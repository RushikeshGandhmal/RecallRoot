from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.orm import Session

from recallgraph.agent.prompts import TRUSTED_POLICY, UNSAFE_MEMORY
from recallgraph.database import SessionDep
from recallgraph.ids import new_id
from recallgraph.memory.models import MemoryRecord, utc_now
from recallgraph.memory.provenance import content_hash, sanitized_preview
from recallgraph.memory.repository import MemoryRepository, reset_demo_data
from recallgraph.presenters import present_memory
from recallgraph.schemas import DemoMutationResponse
from recallgraph.telemetry.attributes import SCENARIO
from recallgraph.telemetry.logging import emit_event
from recallgraph.telemetry.tracing import current_span_ids, recorded_span

router = APIRouter(prefix="/demo", tags=["demo"])


def _write_memory(
    session: Session,
    *,
    memory_id: str,
    content: str,
    source_type: str,
    source_name: str,
    source_trust: str,
    session_id: str,
) -> tuple[MemoryRecord, bool]:
    repository = MemoryRepository(session)
    existing = repository.get(memory_id)
    if existing is not None:
        return existing, False

    digest = content_hash(content)
    preview = sanitized_preview(content)
    with (
        recorded_span(
            session,
            "ingest_source",
            attributes={
                "recallgraph.session.id": session_id,
                "recallgraph.scenario": SCENARIO,
                "recallgraph.memory.source.type": source_type,
                "recallgraph.memory.source.trust": source_trust,
                "recallgraph.memory.source.name": source_name,
            },
        ),
        recorded_span(
            session,
            "recallgraph.memory.write",
            attributes={
                "recallgraph.session.id": session_id,
                "recallgraph.scenario": SCENARIO,
                "recallgraph.memory.id": memory_id,
                "recallgraph.memory.operation": "write",
                "recallgraph.memory.status": "active",
                "recallgraph.memory.source.type": source_type,
                "recallgraph.memory.source.trust": source_trust,
                "recallgraph.memory.source.name": source_name,
                "recallgraph.memory.content_hash": digest,
                "recallgraph.memory.sanitized_preview": preview,
            },
        ),
    ):
        trace_id, span_id, trace_flags = current_span_ids()
        memory = MemoryRecord(
            id=memory_id,
            user_key="demo_user",
            content=content,
            content_hash=digest,
            sanitized_preview=preview,
            source_type=source_type,
            source_name=source_name,
            source_trust=source_trust,
            status="active",
            created_at=utc_now(),
            expires_at=None,
            created_trace_id=trace_id,
            created_span_id=span_id,
            created_trace_flags=trace_flags,
            retrieval_count=0,
        )
        repository.add(memory)
        emit_event(
            session,
            "memory_written",
            memory_id=memory.id,
            content_hash=digest,
            sanitized_preview=preview,
            source_name=source_name,
            source_type=source_type,
            source_trust=source_trust,
        )
    return memory, True


@router.post("/reset", response_model=DemoMutationResponse)
def reset_demo(session: SessionDep) -> DemoMutationResponse:
    with recorded_span(
        session,
        "recallgraph.demo.reset",
        attributes={"recallgraph.scenario": SCENARIO},
    ):
        reset_demo_data(session)
    return DemoMutationResponse(
        status="reset",
        message="All operational data and local telemetry evidence were cleared.",
    )


@router.post("/seed-trusted-policy", response_model=DemoMutationResponse)
def seed_trusted_policy(session: SessionDep) -> DemoMutationResponse:
    memory, created = _write_memory(
        session,
        memory_id="mem_trusted_refund_policy",
        content=TRUSTED_POLICY,
        source_type="system_policy",
        source_name="trusted-refund-policy",
        source_trust="trusted",
        session_id=new_id("sess_seed"),
    )
    return DemoMutationResponse(
        status="seeded",
        created=created,
        memory=present_memory(memory),
        message="Trusted refund policy is active.",
    )


@router.post("/ingest-unsafe-memory", response_model=DemoMutationResponse)
def ingest_unsafe_memory(session: SessionDep) -> DemoMutationResponse:
    memory, created = _write_memory(
        session,
        memory_id="mem_unsafe_refund_policy",
        content=UNSAFE_MEMORY,
        source_type="external_document",
        source_name="unverified-refund-playbook.txt",
        source_trust="untrusted",
        session_id=new_id("sess_ingest"),
    )
    return DemoMutationResponse(
        status="ingested",
        created=created,
        memory=present_memory(memory),
        message="Untrusted external note was stored in durable memory.",
    )
