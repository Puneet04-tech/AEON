"""Human-in-the-loop approvals for movements above the threshold."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import structlog

from app.services import audit, events

logger = structlog.get_logger()

TTL_MINUTES = 30


def new_approval_id() -> str:
    return f"apr_{uuid.uuid4().hex[:20]}"


async def create(db, kind: str, subject_id: str, amount_micro: int, facts: dict,
                 requested_by: str = "treasurer") -> dict:
    approval_id = new_approval_id()
    now = datetime.now(timezone.utc)
    doc = {
        "id": approval_id,
        "kind": kind,
        "subject": {"type": kind, "id": subject_id},
        "amount_micro": amount_micro,
        "facts": facts,
        "state": "PENDING",
        "requested_by": requested_by,
        "decided_by": None,
        "decided_at": None,
        "reason": "",
        "created_at": now,
        "expires_at": now + timedelta(minutes=TTL_MINUTES),
    }
    await db.approvals.insert_one({**doc})
    await events.emit(db, "approval.requested", {"approval_id": approval_id, "kind": kind,
                                                 "subject_id": subject_id,
                                                 "amount_micro": amount_micro}, actor=requested_by)
    await audit.record(db, actor_type="agent", actor_id=requested_by, action="approval.requested",
                       subject_type="approval", subject_id=approval_id,
                       detail={"kind": kind, "amount_micro": amount_micro})
    return doc


async def list_approvals(db, state: Optional[str] = None, limit: int = 50) -> List[dict]:
    query = {"state": state} if state else {}
    cursor = db.approvals.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    return [doc async for doc in cursor]


async def pending_for(db, subject_id: str) -> Optional[dict]:
    return await db.approvals.find_one({"subject.id": subject_id, "state": "PENDING"})


async def decide(db, approval_id: str, decision: str, actor: str = "operator",
                 reason: str = "", client=None) -> dict:
    if decision not in {"APPROVED", "REJECTED"}:
        raise ValueError("invalid_decision")
    approval = await db.approvals.find_one({"id": approval_id})
    if not approval:
        raise ValueError("approval_not_found")
    if approval["state"] != "PENDING":
        raise ValueError(f"approval_already_{approval['state'].lower()}")
    expires_at = approval["expires_at"]
    if hasattr(expires_at, "tzinfo") and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        await db.approvals.update_one({"id": approval_id}, {"$set": {"state": "EXPIRED"}})
        raise ValueError("approval_expired")

    updated = await db.approvals.find_one_and_update(
        {"id": approval_id, "state": "PENDING"},
        {"$set": {"state": decision, "decided_by": actor,
                  "decided_at": datetime.now(timezone.utc), "reason": reason[:500]}},
        return_document=True,
    )
    if not updated:
        raise ValueError("approval_already_decided")

    await events.emit(db, "approval.decided", {"approval_id": approval_id, "decision": decision,
                                               "kind": approval["kind"],
                                               "subject_id": approval["subject"]["id"]}, actor=actor)
    await audit.record(db, actor_type="operator", actor_id=actor, action="approval.decided",
                       subject_type="approval", subject_id=approval_id,
                       before={"state": "PENDING"}, after={"state": decision},
                       detail={"reason": reason[:300]})

    result = {"approval": await db.approvals.find_one({"id": approval_id}, {"_id": 0})}
    if decision == "APPROVED":
        result["execution"] = await _execute(db, approval, actor, client)
    return result


async def _execute(db, approval: dict, actor: str, client=None) -> dict:
    kind = approval["kind"]
    subject_id = approval["subject"]["id"]
    if kind == "settlement":
        from app.services import settlement

        try:
            return await settlement.execute_settlement(db, subject_id, actor=actor,
                                                       has_approval=True, client=client)
        except ValueError as exc:
            return {"error": str(exc)}
    if kind == "loan":
        from app.services import loans

        try:
            return await loans.disburse_approved(db, subject_id, actor)
        except ValueError as exc:
            return {"error": str(exc)}
    if kind == "funding":
        return {"error": "funding approvals are not wired"}
    return {"error": f"unknown approval kind {kind}"}


async def expire_pending(db) -> int:
    now = datetime.now(timezone.utc)
    result = await db.approvals.update_many(
        {"state": "PENDING", "expires_at": {"$lt": now}},
        {"$set": {"state": "EXPIRED"}},
    )
    return result.modified_count
