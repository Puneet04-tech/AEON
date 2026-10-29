"""Treasurer agent: reads PayPal-side state and proposes payout batches.

Two jobs:
  * mirror PayPal resources into a read model the console and MCP tools can show
  * propose a settlement batch, with an LLM-written rationale that guardrails
    validate before a human or the settlement engine can act on it

Nothing here moves money. Execution lives in `services.settlement`.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List

import structlog

from app.ledger.service import LedgerService
from app.paypal import orders as orders_api
from app.paypal import payouts as payouts_api
from app.paypal.client import PayPalClient, PayPalError
from app.services import settlement

logger = structlog.get_logger()

TREASURER_SYSTEM = (
    "You are the treasurer agent of a compute clearing house. Reply with JSON only: "
    "{\"recommend\": boolean, \"note\": string}. recommend is true only when the batch is "
    "within the treasury float, above the payout floor and justified by net credits. "
    "note is one short sentence for the operator."
)


async def list_orders(db, limit: int = 20) -> List[dict]:
    """Funding orders with their PayPal-side status when available."""
    rows = []
    cursor = db.funding_requests.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    client = PayPalClient(db)
    async for funding in cursor:
        row = {
            "funding_id": funding["id"],
            "agent_id": funding["agent_id"],
            "amount_micro": funding["amount_micro"],
            "state": funding["state"],
            "paypal_order_id": funding.get("paypal_order_id", ""),
            "mock": bool(funding.get("mock")),
        }
        if not funding.get("mock") and funding.get("paypal_order_id"):
            try:
                live = await orders_api.get_order(client, funding["paypal_order_id"])
                row["paypal_status"] = live.get("status", "")
            except PayPalError as exc:
                row["paypal_status_error"] = exc.code
        rows.append(row)
    return rows


async def list_transactions(db, limit: int = 40) -> List[dict]:
    """Captured funding and settled payouts: the money that actually moved."""
    captures = []
    cursor = db.funding_requests.find({"state": "CAPTURED"}, {"_id": 0}).sort("captured_at", -1).limit(limit)
    async for funding in cursor:
        captures.append({
            "kind": "capture",
            "ref": funding.get("capture_id") or funding["id"],
            "agent_id": funding["agent_id"],
            "amount_micro": funding["amount_micro"],
            "at": (funding.get("captured_at") or funding.get("created_at")).isoformat()
            if hasattr(funding.get("captured_at") or funding.get("created_at"), "isoformat") else "",
        })
    payouts = []
    cursor = db.payout_items.find({"state": "SUCCESS"}, {"_id": 0}).sort("settled_at", -1).limit(limit)
    async for item in cursor:
        payouts.append({
            "kind": "payout",
            "ref": item.get("paypal_item_id") or item["id"],
            "agent_id": item["agent_id"],
            "amount_micro": int(item["amount_micro"]),
            "at": item["settled_at"].isoformat() if hasattr(item.get("settled_at"), "isoformat") else "",
        })
    return sorted(captures + payouts, key=lambda row: row["at"], reverse=True)[:limit]


async def payout_batches(db, limit: int = 10) -> List[dict]:
    batches = []
    async for settlement_doc in db.settlements.find({}, {"_id": 0}).sort("created_at", -1).limit(limit):
        batches.append({
            "settlement_id": settlement_doc["id"],
            "state": settlement_doc["state"],
            "paypal_batch_id": settlement_doc.get("paypal_batch_id", ""),
            "totals": settlement_doc.get("totals", {}),
            "simulated": bool(settlement_doc.get("simulated")),
        })
    return batches


async def propose_batch_plan(db) -> Dict[str, Any]:
    """Build the batch the treasurer would submit, plus a validated rationale."""
    from app.llm.llm_client import LLMUnavailable, get_llm

    plan = await settlement.build_plan(db)
    ledger = LedgerService(db)
    amount = int(plan["totals"]["amount_micro"])

    llm_note = {"source": "fallback", "provider": "none", "model": "none", "latency_ms": 0}
    recommend = amount > 0
    note = "deterministic fallback: recommend when net credits exist inside the float"
    try:
        result = await get_llm(db).complete_json(
            "treasurer_plan", TREASURER_SYSTEM,
            f"net_amount_micro={amount}; items={plan['totals']['items']}; "
            f"treasury_float_micro={plan['treasury_float_micro']}; "
            f"paid_today_micro={plan['paid_today_micro']}",
        )
        data = result["data"]
        if isinstance(data.get("recommend"), bool):
            recommend = data["recommend"]
        if isinstance(data.get("note"), str):
            note = data["note"][:300]
        llm_note = {k: result[k] for k in ("source", "provider", "model", "latency_ms")}
    except LLMUnavailable:
        pass

    from app.guardrails import policy

    decision = await policy.check_settlement(db, amount, has_approval=False) if amount else None
    return {
        "positions": plan["positions"],
        "totals": plan["totals"],
        "treasury_float_micro": plan["treasury_float_micro"],
        "paid_today_micro": plan["paid_today_micro"],
        "treasurer": {
            "recommend": recommend,
            "note": note,
            "llm": llm_note,
            "guardrail": decision.to_dict() if decision else None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "simulated_pricing": False,
    }


async def payments_overview(db) -> Dict[str, Any]:
    return {
        "paypal_mode": PayPalClient(db).mode,
        "orders": await list_orders(db),
        "transactions": await list_transactions(db),
        "batches": await payout_batches(db),
    }
