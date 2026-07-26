from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemoryView(ApiModel):
    id: str
    content: str
    sanitized_preview: str
    content_hash: str
    source_type: str
    source_name: str
    source_trust: str
    status: str
    retrieval_count: int
    created_at: datetime
    created_trace_id: str
    created_span_id: str


class ActionView(ApiModel):
    id: str
    type: str
    amount: float
    customer_id: str
    sensitivity: str
    approval_required: bool
    approval_present: bool
    policy_outcome: str
    trace_id: str
    span_id: str
    result: dict[str, Any]


class RiskFactorView(ApiModel):
    points: int
    label: str
    reason: str


class RiskView(ApiModel):
    score: int
    level: str
    factors: list[RiskFactorView]


class IncidentView(ApiModel):
    id: str
    incident_id: str
    status: str
    risk_score: int
    risk_level: str
    risk: RiskView
    policy_outcome: str
    detected_at: datetime
    created_at: datetime
    resolved_at: datetime | None
    run_id: str
    session_id: str
    trace_id: str
    action: ActionView
    memory: MemoryView


class IncidentList(ApiModel):
    items: list[IncidentView]
    total: int
    open_count: int
    critical_count: int


class RefundRequest(ApiModel):
    customer_id: str = Field(min_length=1, max_length=120)
    amount: float = Field(gt=0, le=10_000_000)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("customer_id", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class AgentRunView(ApiModel):
    run_id: str
    session_id: str
    trace_id: str
    outcome: str
    response: str
    action: ActionView
    memory: MemoryView
    policy_outcome: str
    policy_explanation: str
    decision_rationale: str
    risk_score: int
    risk_level: str
    risk: RiskView
    incident_id: str | None
    incident: IncidentView | None


class DemoMutationResponse(ApiModel):
    status: Literal["reset", "seeded", "ingested"]
    created: bool | None = None
    memory: MemoryView | None = None
    message: str


class QuarantineResponse(ApiModel):
    status: Literal["quarantined"]
    remediation: Literal["memory_quarantine"] = "memory_quarantine"
    already_quarantined: bool
    memory: MemoryView


class HealthResponse(ApiModel):
    status: Literal["ok"]
    service: str
    version: str
    database: Literal["ok"]
    telemetry_export: Literal["configured", "local-only"]


class ReadinessCheck(ApiModel):
    status: Literal["ready", "degraded", "unconfigured", "unavailable"]
    detail: str


class LLMReadiness(ApiModel):
    provider: Literal["deterministic", "ollama"]
    model: str | None
    fallback_provider: Literal["deterministic"]
    local_only: bool


class ReadinessResponse(ApiModel):
    status: Literal["ready", "degraded"]
    checks: dict[str, ReadinessCheck]
    llm: LLMReadiness


class AlertWebhookResponse(ApiModel):
    status: Literal["accepted"]
    message: str


class ReplaySide(ApiModel):
    trace_id: str
    run_id: str
    action_id: str
    memory_id: str
    memory_status: str
    source_trust: str
    decision: str
    tool: str
    outcome: str
    policy_outcome: str
    risk_score: int
    risk_level: str


class CausalMemoryRemediation(ApiModel):
    id: str
    source_trust: str
    before_status: Literal["active"]
    after_status: Literal["quarantined"]
    remediation: Literal["quarantine"]


class OperativeReplayMemory(ApiModel):
    id: str
    source_trust: Literal["trusted"]
    status: Literal["active"]


class ReplayComparison(ApiModel):
    before: ReplaySide
    after: ReplaySide
    original: ReplaySide
    replay: ReplaySide
    causal_memory: CausalMemoryRemediation
    operative_replay_memory: OperativeReplayMemory
    changed_fields: list[str]
    verified_at: datetime


class ReplayResponse(ApiModel):
    replay_id: str
    incident_id: str
    status: str
    result: Literal["improved", "unchanged"]
    memory_quarantined: bool
    original_trace_id: str
    replay_trace_id: str
    original: ReplaySide
    replay: ReplaySide
    before: ReplaySide
    after: ReplaySide
    causal_memory: CausalMemoryRemediation
    operative_replay_memory: OperativeReplayMemory
    created_at: datetime
    verified_at: datetime
    comparison: ReplayComparison
    run: AgentRunView | None = None
