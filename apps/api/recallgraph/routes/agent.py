from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from recallgraph.agent.refund_agent import RefundAgent, RefundCommand
from recallgraph.config import Settings
from recallgraph.database import SessionDep
from recallgraph.presenters import present_execution
from recallgraph.schemas import AgentRunView, RefundRequest

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/refund", response_model=AgentRunView, status_code=status.HTTP_201_CREATED)
def execute_refund(
    payload: RefundRequest,
    request: Request,
    session: SessionDep,
) -> AgentRunView:
    settings: Settings = request.app.state.settings
    try:
        execution = RefundAgent(settings).run(
            session,
            RefundCommand(
                customer_id=payload.customer_id,
                amount=payload.amount,
                reason=payload.reason,
            ),
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "refund_policy_missing",
                "message": str(exc),
                "hint": "Call POST /demo/seed-trusted-policy first.",
            },
        ) from exc
    return present_execution(execution)
