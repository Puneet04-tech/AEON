"""Ledger read endpoints, including the invariant status chip."""
from typing import Optional

from fastapi import APIRouter, Depends

from app.db.client import get_database
from app.ledger.netting import net_positions, totals
from app.ledger.service import LedgerService
from app.security.sessions import Session, require_viewer
from app.services import settlement

router = APIRouter(prefix="/api/v1/ledger", tags=["ledger"])


@router.get("/entries")
async def entries(limit: int = 200, agent_id: Optional[str] = None,
                  session: Session = Depends(require_viewer)):
    return {"entries": await LedgerService(get_database()).entries(limit=min(limit, 1000),
                                                                   agent_id=agent_id)}


@router.get("/balances")
async def balances(session: Session = Depends(require_viewer)):
    db = get_database()
    ledger = LedgerService(db)
    wallets = await ledger.all_balances()
    system = {}
    async for doc in db.account_totals.find({}, {"_id": 1, "amount_micro": 1}):
        system[doc["_id"]] = int(doc["amount_micro"])
    return {"agents": wallets, "system_accounts": system,
            "treasury_float_micro": await ledger.treasury_float_micro()}


@router.get("/invariant")
async def invariant(session: Session = Depends(require_viewer)):
    return await LedgerService(get_database()).invariant()


@router.get("/netting")
async def netting(session: Session = Depends(require_viewer)):
    plan = await settlement.build_plan(get_database())
    return plan


@router.post("/rebuild-wallets")
async def rebuild(session: Session = Depends(require_viewer)):
    """Repair the balance caches from the append-only ledger."""
    count = await LedgerService(get_database()).rebuild_wallets()
    return {"ok": True, "wallets": count}


@router.get("/transactions/{txn_id}")
async def transaction(txn_id: str, session: Session = Depends(require_viewer)):
    return {"txn_id": txn_id, "entries": await LedgerService(get_database()).transaction(txn_id)}
