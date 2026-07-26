from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from recallgraph.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class MemoryRecord(Base):
    __tablename__ = "memory_records"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_key: Mapped[str] = mapped_column(String(120), index=True)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    sanitized_preview: Mapped[str] = mapped_column(String(240))
    source_type: Mapped[str] = mapped_column(String(60), index=True)
    source_name: Mapped[str] = mapped_column(String(200))
    source_trust: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_trace_id: Mapped[str] = mapped_column(String(32))
    created_span_id: Mapped[str] = mapped_column(String(16))
    created_trace_flags: Mapped[int] = mapped_column(Integer, default=1)
    retrieval_count: Mapped[int] = mapped_column(Integer, default=0)
    last_retrieved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(80), index=True)
    request_text: Mapped[str] = mapped_column(Text)
    request_type: Mapped[str] = mapped_column(String(40), default="refund")
    customer_id: Mapped[str] = mapped_column(String(120))
    amount: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trace_id: Mapped[str] = mapped_column(String(32), index=True)
    outcome: Mapped[str] = mapped_column(String(40))
    response_text: Mapped[str] = mapped_column(Text)
    is_replay: Mapped[bool] = mapped_column(Boolean, default=False)
    original_run_id: Mapped[str | None] = mapped_column(String(80), nullable=True)

    actions: Mapped[list[Action]] = relationship(
        back_populates="agent_run", cascade="all, delete-orphan"
    )
    influences: Mapped[list[MemoryInfluence]] = relationship(
        back_populates="agent_run", cascade="all, delete-orphan"
    )


class Action(Base):
    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    action_type: Mapped[str] = mapped_column(String(60), index=True)
    amount: Mapped[float] = mapped_column(Float)
    customer_id: Mapped[str] = mapped_column(String(120))
    sensitivity: Mapped[str] = mapped_column(String(24))
    approval_required: Mapped[bool] = mapped_column(Boolean)
    approval_present: Mapped[bool] = mapped_column(Boolean)
    policy_outcome: Mapped[str] = mapped_column(String(24), index=True)
    trace_id: Mapped[str] = mapped_column(String(32), index=True)
    span_id: Mapped[str] = mapped_column(String(16))
    trace_flags: Mapped[int] = mapped_column(Integer, default=1)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    agent_run: Mapped[AgentRun] = relationship(back_populates="actions")
    influences: Mapped[list[MemoryInfluence]] = relationship(
        back_populates="action", cascade="all, delete-orphan"
    )


class MemoryInfluence(Base):
    __tablename__ = "memory_influences"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id", ondelete="CASCADE"), index=True)
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memory_records.id", ondelete="RESTRICT"), index=True
    )
    retrieval_rank: Mapped[int] = mapped_column(Integer)
    retrieval_reason: Mapped[str] = mapped_column(String(300))
    risk_score: Mapped[int] = mapped_column(Integer)

    agent_run: Mapped[AgentRun] = relationship(back_populates="influences")
    action: Mapped[Action] = relationship(back_populates="influences")
    memory: Mapped[MemoryRecord] = relationship()


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    action_id: Mapped[str] = mapped_column(
        ForeignKey("actions.id", ondelete="CASCADE"), unique=True, index=True
    )
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memory_records.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    risk_score: Mapped[int] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(20))
    risk_factors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    policy_outcome: Mapped[str] = mapped_column(String(24), default="violation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    action: Mapped[Action] = relationship()
    agent_run: Mapped[AgentRun] = relationship()
    memory: Mapped[MemoryRecord] = relationship()


class Replay(Base):
    __tablename__ = "replays"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    original_action_id: Mapped[str] = mapped_column(ForeignKey("actions.id", ondelete="CASCADE"))
    original_trace_id: Mapped[str] = mapped_column(String(32))
    replay_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    replay_action_id: Mapped[str] = mapped_column(ForeignKey("actions.id", ondelete="CASCADE"))
    replay_trace_id: Mapped[str] = mapped_column(String(32))
    memory_quarantined: Mapped[bool] = mapped_column(Boolean)
    original_outcome: Mapped[str] = mapped_column(String(40))
    replay_outcome: Mapped[str] = mapped_column(String(40))
    result: Mapped[str] = mapped_column(String(24))
    comparison: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    incident: Mapped[Incident] = relationship()
    replay_run: Mapped[AgentRun] = relationship()


class TelemetrySpan(Base):
    """A durable local copy of semantic evidence, used only if SigNoz is unavailable."""

    __tablename__ = "telemetry_spans"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(32), index=True)
    span_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    parent_span_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="ok")
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON)
    links: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class TelemetryLog(Base):
    __tablename__ = "telemetry_logs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    event: Mapped[str] = mapped_column(String(100), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    span_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
