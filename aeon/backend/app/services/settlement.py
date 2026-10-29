"""Settlement: net internal balances, then pay net-positive agents with one
PayPal Payouts batch from the treasury.

Flow: DRAFT -> (AWAITING_APPROVAL) -> OPEN -> SUBMITTED -> SUCCEEDED | PARTIAL | FAILED
Every item moves funds to `payout_in_flight` before the API call and either
completes or reverses it afterwards, so a crash mid-batch leaves an auditable
in-flight position instead of silent money loss.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import structlog

from app.guardrails import policy
from app.ledger.netting import apply_caps, net_positions, totals
from app.ledger.service import LedgerService
from app.paypal import payouts as payouts_api
from app.paypal.client import PayPalClient, PayPalError
from app.services import audit, events

logger = structlog.get_logger()

FINAL_GOOD = {"SUCCESS"}
FAILED_STATES = {"FAILED", "DENIED", "RETURNED", "BLOCKED", "CANCELLED", "REVERSED"}


def new_settlement_id() -> str:
    return f"stl_{uuid.uuid4().hex[:20]}"


def sender_batch_id(settlement_id: str) -> str:
    return f"AEON-{settlement_id}"[:64]


async def _cash_out_agents(db) -> dict:
    """Agents that opted into cash-out, with the PayPal email to pay."""
    emails = {}
    async for agent in db.agents.find({"paypal_email": {"$ne": ""},
                                       "policy.cash_out": True,
                                       "status": {"$in": ["ACTIVE", "PAUSED"]}},
                                      {"id": 1, "paypal_email": 1}):
        emails[agent["id"]] = agent["paypal_email"]
    return emails


async def build_plan(db) -> dict:
    ledger = LedgerService(db)
    wallets = await ledger.all_balances()
    emails = await _cash_out_agents(db)
    positions = net_positions(wallets, emails, eligible=set(emails))
    float_micro = await ledger.treasury_funds_micro()
    paid_today = await policy.paid_today_micro(db)
    from app.settings import settings

    remaining = max(0, settings.PAYOUT_DAILY_CAP_MICRO - paid_today)
    capped = apply_caps(positions, float_micro, remaining)
    return {
        "positions": capped,
        "totals": totals(capped),
        "treasury_float_micro": float_micro,
        "paid_today_micro": paid_today,
        "excluded_below_floor": len(positions) - len(capped),
    }


async def propose_settlement(db, actor: str = "operator", has_approval: bool = False,
                             client: Optional[PayPalClient] = None) -> dict:
    if await policy.kill_switch_active(db):
        raise ValueError("kill_switch_active")

    plan = await build_plan(db)
    if not plan["positions"]:
        raise ValueError("nothing_to_settle")

    amount = plan["totals"]["amount_micro"]
    decision = await policy.check_settlement(db, amount, has_approval)
    if not decision.passed:
        raise ValueError(f"guardrail: {', '.join(decision.failed)}")

    settlement_id = new_settlement_id()
    needs_approval = amount >= _approval_threshold()
    state = "AWAITING_APPROVAL" if (needs_approval and not has_approval) else "DRAFT"
    now = datetime.now(timezone.utc)
    doc = {
        "id": settlement_id,
        "state": state,
        "sender_batch_id": sender_batch_id(settlement_id),
        "paypal_batch_id": "",
        "window": {"from": now.isoformat(), "to": now.isoformat()},
        "totals": plan["totals"],
        "treasury_float_micro": plan["treasury_float_micro"],
        "lock_owner": None,
        "created_by": actor,
        "created_at": now,
        "updated_at": now,
        "guardrail": decision.to_dict(),
        "approval_id": None,
        "simulated": False,
    }
    await db.settlements.insert_one({**doc})
    await db.payout_items.delete_many({"settlement_id": settlement_id})
    for position in plan["positions"]:
        await db.payout_items.insert_one({
            "id": f"pi_{uuid.uuid4().hex[:16]}",
            "settlement_id": settlement_id,
            "agent_id": position["agent_id"],
            "amount_micro": position["amount_micro"],
            "state": "PENDING",
            "paypal_item_id": "",
            "sender_item_id": f"{settlement_id}:{position['agent_id']}"[:64],
            "receiver": position["paypal_email"],
            "approval_id": None,
            "created_at": now,
        })
    await events.emit(db, "settlement.proposed", {"settlement_id": settlement_id,
                                                  "amount_micro": amount,
                                                  "items": plan["totals"]["items"],
                                                  "state": state}, actor=actor)
    await audit.record(db, actor_type="operator", actor_id=actor, action="settlement.proposed",
                       subject_type="settlement", subject_id=settlement_id,
                       after={"amount_micro": amount, "state": state})

    if state == "AWAITING_APPROVAL":
        from app.services import approvals

        approval = await approvals.create(db, kind="settlement", subject_id=settlement_id,
                                          amount_micro=amount,
                                          facts={"items": plan["totals"]["items"],
                                                 "treasury_float_micro": plan["treasury_float_micro"]},
                                          requested_by=actor)
        await db.settlements.update_one({"id": settlement_id}, {"$set": {"approval_id": approval["id"]}})
        doc["approval_id"] = approval["id"]
        return doc

    return await execute_settlement(db, settlement_id, actor=actor, has_approval=has_approval,
                                    client=client)


def _approval_threshold() -> int:
    from app.settings import settings

    return settings.APPROVAL_THRESHOLD_MICRO


async def execute_settlement(db, settlement_id: str, actor: str = "operator",
                             has_approval: bool = False,
                             client: Optional[PayPalClient] = None) -> dict:
    settlement = await db.settlements.find_one({"id": settlement_id})
    if not settlement:
        raise ValueError("settlement_not_found")
    if settlement["state"] in {"SUBMITTED", "SUCCEEDED", "PARTIAL", "FAILED"}:
        return settlement
    if settlement["state"] == "AWAITING_APPROVAL" and not has_approval:
        raise ValueError("settlement_awaiting_approval")

    items = [item async for item in db.payout_items.find({"settlement_id": settlement_id})]
    if not items:
        raise ValueError("empty_settlement")

    amount = sum(int(i["amount_micro"]) for i in items)
    decision = await policy.check_settlement(db, amount, has_approval)
    if not decision.passed:
        await db.settlements.update_one(
            {"id": settlement_id},
            {"$set": {"state": "DRAFT", "guardrail": decision.to_dict(),
                      "updated_at": datetime.now(timezone.utc)}},
        )
        raise ValueError(f"guardrail: {', '.join(decision.failed)}")

    # Single active batch: optimistic lock on state.
    lock_owner = f"{actor}:{uuid.uuid4().hex[:8]}"
    claimed = await db.settlements.find_one_and_update(
        {"id": settlement_id, "state": {"$in": ["DRAFT", "AWAITING_APPROVAL"]}},
        {"$set": {"state": "OPEN", "lock_owner": lock_owner,
                  "updated_at": datetime.now(timezone.utc)}},
    )
    if not claimed:
        current = await db.settlements.find_one({"id": settlement_id})
        if current and current["state"] in {"OPEN", "SUBMITTED"}:
            return current
        raise ValueError("settlement_not_claimable")

    from app.settings import settings

    client = client or PayPalClient(db)
    ledger = LedgerService(db)

    for item in items:
        await ledger.start_payout(settlement_id, item["agent_id"], int(item["amount_micro"]))

    payload_items = [{
        "sender_item_id": item["sender_item_id"],
        "receiver_email": item["receiver"],
        "amount_micro": int(item["amount_micro"]),
        "note": f"AEON settlement {settlement_id}",
    } for item in items]

    try:
        batch = await payouts_api.create_payout(client, settlement["sender_batch_id"], payload_items,
                                                email_subject="AEON settlement (sandbox)")
    except PayPalError as exc:
        for item in items:
            await ledger.reverse_payout(settlement_id, item["agent_id"], int(item["amount_micro"]),
                                        reason="payout submission failed")
            await db.payout_items.update_one({"id": item["id"]},
                                             {"$set": {"state": "FAILED",
                                                       "failure": {"code": exc.code,
                                                                   "message": str(exc)[:300]}}})
        await db.settlements.update_one(
            {"id": settlement_id},
            {"$set": {"state": "FAILED", "lock_owner": None,
                      "failure": {"code": exc.code, "message": str(exc)[:300]},
                      "updated_at": datetime.now(timezone.utc)}},
        )
        await events.emit(db, "settlement.failed", {"settlement_id": settlement_id,
                                                    "error": exc.code}, actor=actor)
        raise

    batch_header = batch.get("batch_header") or {}
    payout_batch_id = batch_header.get("payout_batch_id", "")
    await db.settlements.update_one(
        {"id": settlement_id},
        {"$set": {"state": "SUBMITTED", "paypal_batch_id": payout_batch_id,
                  "lock_owner": None, "simulated": bool(batch.get("mock")),
                  "submitted_at": datetime.now(timezone.utc),
                  "updated_at": datetime.now(timezone.utc)}},
    )
    by_sender = {entry.get("sender_item_id"): entry for entry in payouts_api.normalize_items(batch)}
    for item in items:
        normalized = by_sender.get(item["sender_item_id"], {})
        await db.payout_items.update_one(
            {"id": item["id"]},
            {"$set": {"state": normalized.get("status") or "SUBMITTED",
                      "paypal_item_id": normalized.get("payout_item_id", ""),
                      "submitted_at": datetime.now(timezone.utc)}},
        )
    await events.emit(db, "settlement.submitted", {"settlement_id": settlement_id,
                                                   "paypal_batch_id": payout_batch_id,
                                                   "amount_micro": amount,
                                                   "items": len(items)}, actor=actor)
    await audit.record(db, actor_type="operator", actor_id=actor, action="settlement.submitted",
                       subject_type="settlement", subject_id=settlement_id,
                       after={"paypal_batch_id": payout_batch_id, "amount_micro": amount})

    # Mock payouts report terminal state immediately; reconcile inline.
    if batch.get("mock") or payout_batch_id:
        try:
            return await reconcile(db, settlement_id, client=client)
        except PayPalError as exc:  # reconciliation failure is not a submission failure
            logger.warning("inline_reconcile_failed", settlement=settlement_id, error=str(exc))
    return await db.settlements.find_one({"id": settlement_id}, {"_id": 0})


async def reconcile(db, settlement_id: str, client: Optional[PayPalClient] = None) -> dict:
    settlement = await db.settlements.find_one({"id": settlement_id})
    if not settlement:
        raise ValueError("settlement_not_found")
    if not settlement.get("paypal_batch_id"):
        raise ValueError("settlement_not_submitted")

    client = client or PayPalClient(db)
    batch = await payouts_api.get_payout(client, settlement["paypal_batch_id"])
    normalized = payouts_api.normalize_items(batch)
    ledger = LedgerService(db)
    items = [item async for item in db.payout_items.find({"settlement_id": settlement_id})]
    by_paypal = {n["payout_item_id"]: n for n in normalized if n["payout_item_id"]}
    by_sender = {n["sender_item_id"]: n for n in normalized}

    for item in items:
        entry = by_paypal.get(item.get("paypal_item_id")) or by_sender.get(item["sender_item_id"]) or {}
        status = (entry.get("status") or "").upper()
        if not status:
            continue
        if status in FINAL_GOOD and item["state"] != "SUCCESS":
            await ledger.complete_payout(settlement_id, item["agent_id"], int(item["amount_micro"]))
            await db.payout_items.update_one({"id": item["id"]},
                                             {"$set": {"state": "SUCCESS",
                                                       "paypal_item_id": entry.get("payout_item_id", item.get("paypal_item_id", "")),
                                                       "settled_at": datetime.now(timezone.utc)}})
        elif status in FAILED_STATES and item["state"] != "FAILED":
            await ledger.reverse_payout(settlement_id, item["agent_id"], int(item["amount_micro"]),
                                        reason=f"paypal item {status}")
            await db.payout_items.update_one({"id": item["id"]},
                                             {"$set": {"state": "FAILED",
                                                       "failure": {"code": status, "message": str(entry.get("error") or "")[:300]}}})
        else:
            await db.payout_items.update_one({"id": item["id"]}, {"$set": {"state": status}})

    items = [item async for item in db.payout_items.find({"settlement_id": settlement_id})]
    successes = sum(1 for i in items if i["state"] == "SUCCESS")
    failures = sum(1 for i in items if i["state"] == "FAILED")
    if successes == len(items):
        state = "SUCCEEDED"
    elif failures == len(items):
        state = "FAILED"
    elif successes + failures == len(items):
        state = "PARTIAL"
    else:
        state = "SUBMITTED"

    await db.settlements.update_one(
        {"id": settlement_id},
        {"$set": {"state": state, "reconciled_at": datetime.now(timezone.utc),
                  "updated_at": datetime.now(timezone.utc)}},
    )
    await events.emit(db, f"settlement.{state.lower()}",
                      {"settlement_id": settlement_id, "succeeded": successes, "failed": failures},
                      actor="reconciler")
    if state in {"SUCCEEDED", "PARTIAL", "FAILED"}:
        await audit.record(db, actor_type="system", actor_id="reconciler",
                           action=f"settlement.{state.lower()}", subject_type="settlement",
                           subject_id=settlement_id, severity="info" if state == "SUCCEEDED" else "warning",
                           detail={"succeeded": successes, "failed": failures})
        from app.services import loans

        await loans.repay_from_settlement(db, settlement_id)
    return await db.settlements.find_one({"id": settlement_id}, {"_id": 0})


async def on_payout_webhook(db, event_type: str, resource: dict) -> dict:
    item_id = resource.get("payout_item_id") or ""
    sender_item_id = (resource.get("payout_item") or {}).get("sender_item_id") or resource.get("sender_item_id")
    item = None
    if item_id:
        item = await db.payout_items.find_one({"paypal_item_id": item_id})
    if item is None and sender_item_id:
        item = await db.payout_items.find_one({"sender_item_id": sender_item_id})
    if not item:
        return {"handled": False, "action": "unmatched_payout_item"}
    settlement_id = item["settlement_id"]
    return {"handled": True, "action": "reconciled", "settlement": await reconcile(db, settlement_id)}


async def list_settlements(db, limit: int = 50) -> List[dict]:
    cursor = db.settlements.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return [doc async for doc in cursor]


async def list_payouts(db, limit: int = 100, settlement_id: Optional[str] = None) -> List[dict]:
    query = {"settlement_id": settlement_id} if settlement_id else {}
    cursor = db.payout_items.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    return [doc async for doc in cursor]
