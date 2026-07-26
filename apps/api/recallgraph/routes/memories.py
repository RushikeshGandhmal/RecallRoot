from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from recallgraph.database import SessionDep
from recallgraph.presenters import present_memory
from recallgraph.remediation.quarantine import MemoryNotFoundError, quarantine_memory
from recallgraph.schemas import QuarantineResponse

router = APIRouter(prefix="/memories", tags=["memories"])


@router.post("/{memory_id}/quarantine", response_model=QuarantineResponse)
def quarantine(memory_id: str, session: SessionDep) -> QuarantineResponse:
    try:
        memory, already_quarantined = quarantine_memory(session, memory_id)
    except MemoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "memory_not_found", "message": str(exc)},
        ) from exc
    return QuarantineResponse(
        status="quarantined",
        already_quarantined=already_quarantined,
        memory=present_memory(memory),
    )
