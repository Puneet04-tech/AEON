from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.deps import mutate
from app.db.client import get_database
from app.ledger.service import LedgerError, LedgerService
from app.security.sessions import Session, require_judge_or_operator, require_viewer
from app.services import audit, events
from app.services.trust import provider_reputation

router = APIRouter(prefix="/api/v1", tags=["trust"])


class DisputeRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)


class DisputeResolution(BaseModel):
    outcome: Literal["refund", "release"]
    note: str = Field(min_length=3, max_length=1000)


@router.get("/trades/{trade_id}/evidence")
async def evidence(trade_id: str, session: Session = Depends(require_viewer)):
    db = get_database()
    doc = await db.execution_evidence.find_one({"trade_id": trade_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "execution evidence not found")
    verification = await db.verifications.find_one(
        {"trade_id": trade_id}, {"_id": 0}, sort=[("created_at", -1)]
    )
    return {"evidence": doc, "verification": verification}


@router.post("/trades/{trade_id}/dispute", status_code=status.HTTP_201_CREATED)
async def create_dispute(trade_id: str, body: DisputeRequest,
                         request: Request,
                         session: Session = Depends(require_judge_or_operator)):
    db = get_database()
    trade = await db.trades.find_one({"id": trade_id})
    if not trade:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trade not found")
    if trade.get("state") != "SETTLED":
        raise HTTPException(status.HTTP_409_CONFLICT, "only settled trades can be disputed")
    evidence = await db.execution_evidence.find_one({"trade_id": trade_id})
    if not evidence:
        raise HTTPException(status.HTTP_409_CONFLICT, "trade has no execution evidence")

    async def handler():
        existing = await db.disputes.find_one({"trade_id": trade_id}, {"_id": 0})
        if existing:
            return existing
        amount = int((trade.get("settlement") or {}).get("price_micro", 0))
        if amount <= 0:
            raise HTTPException(status.HTTP_409_CONFLICT, "trade has no settled value")
        try:
            txn = await LedgerService(db).hold_dispute(trade_id, trade["seller_id"], amount)
        except LedgerError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
        now = datetime.now(timezone.utc)
        dispute = {
            "id": f"dsp_{trade_id}",
            "trade_id": trade_id,
            "buyer_id": trade["buyer_id"],
            "seller_id": trade["seller_id"],
            "amount_micro": amount,
            "reason": body.reason,
            "state": "OPEN",
            "hold_txn_id": txn["txn_id"],
            "created_by": session.role,
            "created_at": now,
            "updated_at": now,
        }
        await db.disputes.insert_one(dispute)
        await db.trades.update_one({"id": trade_id}, {"$set": {"state": "DISPUTED",
                                                                 "dispute_id": dispute["id"],
                                                                 "updated_at": now}})
        await audit.record(db, actor_type="operator", actor_id=session.role,
                           action="trade.disputed", subject_type="trade", subject_id=trade_id,
                           detail={"reason": body.reason, "amount_micro": amount})
        await events.emit(db, "trade.disputed", {"trade_id": trade_id, "reason": body.reason},
                          trade_id=trade_id)
        dispute.pop("_id", None)
        return dispute

    return await mutate(request, {"trade_id": trade_id, "reason": body.reason}, handler)


@router.get("/trades/{trade_id}/dispute")
async def get_dispute(trade_id: str, session: Session = Depends(require_viewer)):
    dispute = await get_database().disputes.find_one({"trade_id": trade_id}, {"_id": 0})
    return dispute


@router.post("/trades/{trade_id}/dispute/resolve")
async def resolve_dispute(trade_id: str, body: DisputeResolution,
                          request: Request,
                          session: Session = Depends(require_judge_or_operator)):
    db = get_database()
    dispute = await db.disputes.find_one({"trade_id": trade_id})
    if not dispute or dispute.get("state") != "OPEN":
        raise HTTPException(status.HTTP_409_CONFLICT, "open dispute not found")
    async def handler():
        txn = await LedgerService(db).resolve_dispute(
            trade_id, dispute["seller_id"], dispute["buyer_id"],
            int(dispute["amount_micro"]), body.outcome == "refund",
        )
        now = datetime.now(timezone.utc)
        state = "REFUNDED" if body.outcome == "refund" else "RELEASED"
        await db.disputes.update_one({"trade_id": trade_id}, {"$set": {
            "state": state, "outcome": body.outcome, "note": body.note,
            "resolution_txn_id": txn["txn_id"], "resolved_by": session.role, "updated_at": now,
        }})
        await db.trades.update_one({"id": trade_id}, {"$set": {"state": state, "updated_at": now}})
        await audit.record(db, actor_type="operator", actor_id=session.role,
                           action=f"trade.dispute_{body.outcome}", subject_type="trade",
                           subject_id=trade_id, detail={"note": body.note})
        return await db.disputes.find_one({"trade_id": trade_id}, {"_id": 0})
    return await mutate(request, {"trade_id": trade_id, **body.model_dump()}, handler)


@router.get("/agents/{agent_id}/reputation")
async def reputation(agent_id: str, session: Session = Depends(require_viewer)):
    return await provider_reputation(get_database(), agent_id)
