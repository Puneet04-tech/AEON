"""Funding: PayPal Orders checkout -> capture -> ledger credit.

The amount is verified against the funding request before anything is credited,
and the ledger post is idempotent on the order id, so a duplicated webhook can
never double-credit an agent.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import structlog

from app.guardrails import policy
from app.ledger.service import LedgerService
from app.paypal import orders
from app.paypal.client import PayPalClient, PayPalError
from app.services import audit, events

logger = structlog.get_logger()


def new_funding_id() -> str:
    return f"fnd_{uuid.uuid4().hex[:20]}"


async def create_funding(db, agent_id: str, amount_micro: int, actor: str = "operator",
                         client: Optional[PayPalClient] = None) -> dict:
    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        raise ValueError("agent_not_found")

    decision = await policy.check_funding(db, amount_micro)
    if not decision.passed:
        raise ValueError(f"guardrail: {', '.join(decision.failed)}")

    client = client or PayPalClient(db)
    order = await orders.create_order(client, agent_id, agent.get("name", agent_id), amount_micro)

    funding_id = new_funding_id()
    doc = {
        "id": funding_id,
        "agent_id": agent_id,
        "amount_micro": amount_micro,
        "state": "CREATED",
        "paypal_order_id": order["id"],
        "approve_url": order.get("approve_url", ""),
        "capture_id": "",
        "mock": order.get("mock", False),
        "guardrail": decision.to_dict(),
        "created_by": actor,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=3),
    }
    await db.funding_requests.insert_one({**doc})
    await events.emit(db, "funding.created", {"funding_id": funding_id, "agent_id": agent_id,
                                              "amount_micro": amount_micro,
                                              "mock": doc["mock"]}, actor=actor)
    await audit.record(db, actor_type="operator", actor_id=actor, action="funding.created",
                       subject_type="funding_request", subject_id=funding_id,
                       after={"amount_micro": amount_micro, "agent_id": agent_id})
    return doc


async def capture_funding(db, funding_id: str, actor: str = "operator",
                          client: Optional[PayPalClient] = None) -> dict:
    doc = await db.funding_requests.find_one({"id": funding_id})
    if not doc:
        raise ValueError("funding_not_found")
    if doc["state"] == "CAPTURED":
        return doc
    if doc["state"] not in {"CREATED", "APPROVED"}:
        raise ValueError(f"funding is {doc['state']}")

    client = client or PayPalClient(db)
    capture = await orders.capture_order(client, doc["paypal_order_id"])

    if capture.get("status") not in {"COMPLETED", "SUCCESS"}:
        await db.funding_requests.update_one(
            {"id": funding_id},
            {"$set": {"state": "FAILED", "updated_at": datetime.now(timezone.utc),
                      "failure": {"code": "capture_not_completed", "message": str(capture.get("status"))}}},
        )
        raise PayPalError(f"capture did not complete: {capture.get('status')}")

    captured_micro = int(capture.get("amount_micro", 0))
    if captured_micro != int(doc["amount_micro"]):
        await db.funding_requests.update_one(
            {"id": funding_id},
            {"$set": {"state": "AMOUNT_MISMATCH", "updated_at": datetime.now(timezone.utc),
                      "capture_id": capture.get("capture_id", ""),
                      "failure": {"code": "amount_mismatch",
                                  "message": f"captured {captured_micro} vs requested {doc['amount_micro']}"}}},
        )
        await audit.record(db, actor_type="system", actor_id="funding", action="funding.amount_mismatch",
                           subject_type="funding_request", subject_id=funding_id, severity="warning",
                           detail={"captured_micro": captured_micro, "expected_micro": doc["amount_micro"]})
        raise PayPalError("captured amount does not match the funding request", code="amount_mismatch")

    await _credit(db, doc, capture.get("capture_id", ""), actor)
    return await db.funding_requests.find_one({"id": funding_id}, {"_id": 0})


async def _credit(db, funding: dict, capture_id: str, actor: str) -> None:
    ledger = LedgerService(db)
    await ledger.fund_agent(funding["agent_id"], int(funding["amount_micro"]), funding["id"])
    await db.funding_requests.update_one(
        {"id": funding["id"]},
        {"$set": {"state": "CAPTURED", "capture_id": capture_id,
                  "captured_at": datetime.now(timezone.utc),
                  "updated_at": datetime.now(timezone.utc)}},
    )
    await events.emit(db, "funding.captured", {"funding_id": funding["id"],
                                               "agent_id": funding["agent_id"],
                                               "amount_micro": funding["amount_micro"]}, actor=actor)
    await audit.record(db, actor_type="operator", actor_id=actor, action="funding.captured",
                       subject_type="funding_request", subject_id=funding["id"],
                       after={"amount_micro": funding["amount_micro"]})


async def on_capture_webhook(db, resource: dict) -> dict:
    """Credit the funding request referenced by a capture event."""
    order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id") \
        if isinstance(resource.get("supplementary_data"), dict) else None
    custom_id = resource.get("custom_id") or ""
    amount_micro = 0
    if isinstance(resource.get("amount"), dict):
        from app.paypal.client import to_micro

        amount_micro = to_micro(resource["amount"].get("value", "0"))

    query = {"paypal_order_id": order_id} if order_id else {"id": custom_id}
    funding = await db.funding_requests.find_one(query)
    if not funding:
        # capture arrived for an order we never issued
        await audit.record(db, actor_type="system", actor_id="paypal_webhook",
                           action="funding.unmatched_capture", subject_type="order",
                           subject_id=str(order_id or custom_id), severity="warning",
                           detail={"amount_micro": amount_micro})
        return {"handled": False, "action": "unmatched_capture"}

    if funding["state"] == "CAPTURED":
        return {"handled": True, "action": "already_credited", "funding_id": funding["id"]}
    if amount_micro and amount_micro != int(funding["amount_micro"]):
        await db.funding_requests.update_one(
            {"id": funding["id"]},
            {"$set": {"state": "AMOUNT_MISMATCH",
                      "failure": {"code": "amount_mismatch",
                                  "message": f"webhook amount {amount_micro}"}}},
        )
        return {"handled": False, "action": "amount_mismatch", "funding_id": funding["id"]}

    await _credit(db, funding, resource.get("id", ""), "paypal_webhook")
    return {"handled": True, "action": "credited", "funding_id": funding["id"]}


async def list_funding(db, limit: int = 50) -> List[dict]:
    cursor = db.funding_requests.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return [doc async for doc in cursor]
