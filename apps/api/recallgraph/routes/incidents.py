from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from recallgraph.agent.refund_agent import AgentExecution
from recallgraph.config import Settings
from recallgraph.database import SessionDep
from recallgraph.graph.builder import CausalGraphBuilder
from recallgraph.graph.investigator import IncidentInvestigator
from recallgraph.graph.models import CausalGraph, InvestigationResponse
from recallgraph.memory.models import Incident, Replay
from recallgraph.memory.repository import IncidentRepository, normalize_datetime
from recallgraph.presenters import present_execution, present_incident
from recallgraph.remediation.replay import ReplayPreconditionError, replay_incident
from recallgraph.schemas import (
    IncidentList,
    IncidentView,
    ReplayComparison,
    ReplayResponse,
)

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _incident_or_404(session: Session, incident_id: str) -> Incident:
    incident = IncidentRepository(session).get(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "incident_not_found",
                "message": f"Incident {incident_id} was not found",
            },
        )
    return incident


def _present_replay(replay: Replay, *, run: AgentExecution | None = None) -> ReplayResponse:
    comparison_data = dict(replay.comparison)
    before = comparison_data["before"]
    after = comparison_data["after"]
    comparison_data.setdefault(
        "causal_memory",
        {
            "id": before["memory_id"],
            "source_trust": before["source_trust"],
            "before_status": "active",
            "after_status": "quarantined",
            "remediation": "quarantine",
        },
    )
    comparison_data.setdefault(
        "operative_replay_memory",
        {
            "id": after["memory_id"],
            "source_trust": after["source_trust"],
            "status": after["memory_status"],
        },
    )
    comparison_data.setdefault("verified_at", normalize_datetime(replay.created_at))
    comparison = ReplayComparison.model_validate(comparison_data)
    created_at = normalize_datetime(replay.created_at)
    run_view = present_execution(run) if run is not None else None
    return ReplayResponse(
        replay_id=replay.id,
        incident_id=replay.incident_id,
        status="completed",
        result=replay.result,
        memory_quarantined=replay.memory_quarantined,
        original_trace_id=replay.original_trace_id,
        replay_trace_id=replay.replay_trace_id,
        original=comparison.original,
        replay=comparison.replay,
        before=comparison.before,
        after=comparison.after,
        causal_memory=comparison.causal_memory,
        operative_replay_memory=comparison.operative_replay_memory,
        created_at=created_at,
        verified_at=comparison.verified_at,
        comparison=comparison,
        run=run_view,
    )


@router.get("", response_model=IncidentList)
def list_incidents(
    session: SessionDep,
    incident_status: Annotated[str | None, Query(alias="status")] = None,
) -> IncidentList:
    repository = IncidentRepository(session)
    incidents = repository.list(status=incident_status)
    all_incidents = repository.list()
    return IncidentList(
        items=[present_incident(incident) for incident in incidents],
        total=len(incidents),
        open_count=sum(incident.status == "open" for incident in all_incidents),
        critical_count=sum(incident.risk_level == "critical" for incident in all_incidents),
    )


@router.get("/{incident_id}", response_model=IncidentView)
def get_incident(incident_id: str, session: SessionDep) -> IncidentView:
    return present_incident(_incident_or_404(session, incident_id))


@router.get("/{incident_id}/graph", response_model=CausalGraph)
def get_incident_graph(
    incident_id: str,
    request: Request,
    session: SessionDep,
) -> CausalGraph:
    incident = _incident_or_404(session, incident_id)
    settings: Settings = request.app.state.settings
    return CausalGraphBuilder(settings).build(session, incident)


@router.post("/{incident_id}/investigate", response_model=InvestigationResponse)
def investigate_incident(
    incident_id: str,
    request: Request,
    session: SessionDep,
) -> InvestigationResponse:
    incident = _incident_or_404(session, incident_id)
    settings: Settings = request.app.state.settings
    return IncidentInvestigator(settings).investigate(session, incident)


@router.post("/{incident_id}/replay", response_model=ReplayResponse)
def replay(
    incident_id: str,
    request: Request,
    session: SessionDep,
) -> ReplayResponse:
    incident = _incident_or_404(session, incident_id)
    settings: Settings = request.app.state.settings
    try:
        execution = replay_incident(session, settings, incident)
    except ReplayPreconditionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "safe_replay_precondition_failed",
                "message": str(exc),
            },
        ) from exc
    return _present_replay(execution.replay, run=execution.agent_execution)


@router.get("/{incident_id}/comparison", response_model=ReplayResponse)
def comparison(incident_id: str, session: SessionDep) -> ReplayResponse:
    _incident_or_404(session, incident_id)
    replay_record = IncidentRepository(session).latest_replay(incident_id)
    if replay_record is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "replay_required",
                "message": "Replay the incident before requesting a comparison.",
            },
        )
    return _present_replay(replay_record)
