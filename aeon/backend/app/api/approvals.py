"""Human approval endpoints."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.deps import mutate
from app.db.client import get_database
from app.paypal.client import PayPalError
from app.security.sessions import Session, require_operator, require_viewer
from app.services import approvals as approvals_service

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


class Decision(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(default="", max_length=500)


@router.get("")
async def list_approvals(state: Optional[str] = None, session: Session = Depends(require_viewer)):
    return {"approvals": await approvals_service.list_approvals(get_database(), state=state)}


@router.post("/{approval_id}/decision")
async def decide(approval_id: str, body: Decision, request: Request,
                 session: Session = Depends(require_operator)):
    async def handler() -> dict:
        try:
            return await approvals_service.decide(get_database(), approval_id, body.decision,
                                                  actor="operator", reason=body.reason)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        except PayPalError as exc:
            # The approval is already recorded; report why the payout could not run
            # instead of turning a provider refusal into an opaque 500.
            raise HTTPException(exc.status, {"code": exc.code, "message": str(exc)})

    return await mutate(request, {"approval_id": approval_id, **body.model_dump()}, handler)
