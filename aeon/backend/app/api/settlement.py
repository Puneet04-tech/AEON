"""Settlement and payout endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import mutate
from app.db.client import get_database
from app.paypal.client import PayPalError
from app.security.sessions import Session, require_operator, require_viewer
from app.services import settlement as settlement_service

router = APIRouter(prefix="/api/v1", tags=["settlement"])


class SettlementRun(BaseModel):
    has_approval: bool = False


@router.post("/settlement/run", status_code=status.HTTP_201_CREATED)
async def run_settlement(body: SettlementRun, request: Request,
                         session: Session = Depends(require_operator)):
    async def handler() -> dict:
        try:
            return await settlement_service.propose_settlement(
                get_database(), actor="operator", has_approval=body.has_approval)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        except PayPalError as exc:
            raise HTTPException(exc.status, {"code": exc.code, "message": str(exc)})

    return await mutate(request, body.model_dump(), handler)


@router.get("/settlement/batches")
async def batches(limit: int = 50, session: Session = Depends(require_viewer)):
    return {"settlements": await settlement_service.list_settlements(get_database(), limit=min(limit, 200))}


@router.post("/settlement/batches/{settlement_id}/reconcile")
async def reconcile(settlement_id: str, request: Request,
                    session: Session = Depends(require_operator)):
    async def handler() -> dict:
        try:
            return await settlement_service.reconcile(get_database(), settlement_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        except PayPalError as exc:
            raise HTTPException(exc.status, {"code": exc.code, "message": str(exc)})

    return await mutate(request, {"settlement_id": settlement_id}, handler)


@router.get("/payouts")
async def payouts(limit: int = 100, settlement_id: Optional[str] = None,
                  session: Session = Depends(require_viewer)):
    return {"payouts": await settlement_service.list_payouts(get_database(), limit=min(limit, 500),
                                                             settlement_id=settlement_id)}
