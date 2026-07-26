from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from recallgraph.memory.models import (
    Action,
    AgentRun,
    Incident,
    MemoryInfluence,
    MemoryRecord,
    Replay,
    TelemetryLog,
    TelemetrySpan,
)


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, memory_id: str) -> MemoryRecord | None:
        return self.session.get(MemoryRecord, memory_id)

    def add(self, memory: MemoryRecord) -> MemoryRecord:
        self.session.add(memory)
        self.session.flush()
        return memory

    def active_for_user(self, user_key: str) -> list[MemoryRecord]:
        statement = (
            select(MemoryRecord)
            .where(MemoryRecord.user_key == user_key, MemoryRecord.status == "active")
            .order_by(MemoryRecord.created_at.desc(), MemoryRecord.id.desc())
        )
        return list(self.session.scalars(statement))

    def quarantine(self, memory_id: str) -> MemoryRecord | None:
        memory = self.get(memory_id)
        if memory is None:
            return None
        memory.status = "quarantined"
        self.session.flush()
        return memory


class IncidentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, incident_id: str) -> Incident | None:
        return self.session.get(Incident, incident_id)

    def list(self, status: str | None = None) -> list[Incident]:
        statement = select(Incident).order_by(Incident.created_at.desc())
        if status:
            statement = statement.where(Incident.status == status)
        return list(self.session.scalars(statement))

    def latest_replay(self, incident_id: str) -> Replay | None:
        statement = (
            select(Replay)
            .where(Replay.incident_id == incident_id)
            .order_by(Replay.created_at.desc())
            .limit(1)
        )
        return self.session.scalar(statement)


def reset_demo_data(session: Session) -> None:
    """Delete in dependency order while retaining the database schema."""

    for model in (
        Replay,
        Incident,
        MemoryInfluence,
        Action,
        AgentRun,
        TelemetryLog,
        TelemetrySpan,
        MemoryRecord,
    ):
        session.execute(delete(model))
    session.flush()


def normalize_datetime(value: datetime) -> datetime:
    """SQLite may return naive values even for timezone-aware columns."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
