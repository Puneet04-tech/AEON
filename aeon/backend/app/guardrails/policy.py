"""Policy engine: assembles live facts (balances, spend, velocity, kill switch)
and runs the deterministic rules. Every state-changing service calls this.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.guardrails.rules import GuardrailDecision, evaluate_funding, evaluate_settlement, evaluate_trade
from app.ledger.service import AGENT_AVAILABLE, LedgerService


def _since(minutes: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


async def kill_switch_active(db) -> bool:
    doc = await db.kv.find_one({"key": "kill_switch"})
    return bool(doc and doc.get("value", {}).get("active"))


async def set_kill_switch(db, active: bool, actor: str, reason: str = "") -> dict:
    value = {
        "active": active,
        "reason": reason[:500],
        "updated_by": actor,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.kv.update_one({"key": "kill_switch"}, {"$set": {"value": value}}, upsert=True)
    return value


async def spent_today(db, agent_id: str) -> int:
    """Sum of escrowed trade value created by this buyer since UTC midnight."""
    midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total = 0
    cursor = db.trades.find({
        "buyer_id": agent_id,
        "created_at": {"$gte": midnight},
        "state": {"$in": ["ESCROWED", "DISPATCHED", "DELIVERED", "VERIFIED", "SETTLED"]},
    }, {"agreed.price_micro": 1})
    async for trade in cursor:
        total += int((trade.get("agreed") or {}).get("price_micro", 0))
    return total


async def recent_trades(db, buyer_id: str, minutes: int = 1) -> int:
    return await db.trades.count_documents({"buyer_id": buyer_id, "created_at": {"$gte": _since(minutes)}})


async def check_trade(db, buyer: dict, seller: dict, price_micro: int, quantity: int,
                      reference_micro: int, has_approval: bool = False) -> GuardrailDecision:
    ledger = LedgerService(db)
    available = await ledger.balance(buyer["id"], AGENT_AVAILABLE)
    decision = evaluate_trade(
        buyer_policy={**buyer.get("policy", {}), "agent_id": buyer["id"]},
        seller_policy={**seller.get("policy", {}), "agent_id": seller["id"]},
        price_micro=price_micro,
        reference_micro=reference_micro,
        buyer_available_micro=available,
        spent_today_micro=await spent_today(db, buyer["id"]),
        recent_trades=await recent_trades(db, buyer["id"]),
        has_approval=has_approval,
        kill_active=await kill_switch_active(db),
    )
    return decision


async def check_funding(db, amount_micro: int) -> GuardrailDecision:
    return evaluate_funding(amount_micro, await kill_switch_active(db))


async def paid_today_micro(db) -> int:
    midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total = 0
    cursor = db.payout_items.find({
        "state": {"$in": ["SUBMITTED", "SUCCESS"]},
        "submitted_at": {"$gte": midnight},
    }, {"amount_micro": 1})
    async for item in cursor:
        total += int(item.get("amount_micro", 0))
    return total


async def check_settlement(db, batch_micro: int, has_approval: bool) -> GuardrailDecision:
    ledger = LedgerService(db)
    return evaluate_settlement(
        batch_micro=batch_micro,
        paid_today_micro=await paid_today_micro(db),
        treasury_float_micro=await ledger.treasury_funds_micro(),
        has_approval=has_approval,
        kill_active=await kill_switch_active(db),
    )


async def agent_or_none(db, agent_id: str) -> Optional[dict]:
    return await db.agents.find_one({"id": agent_id})
