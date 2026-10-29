"""Operator controls: kill switch, agent pause, worker chaos and health."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.deps import mutate, request_context
from app.db.client import get_database
from app.guardrails import policy
from app.security.sessions import Session, require_operator, require_viewer
from app.services import audit, events, worker_client
from app.settings import settings

router = APIRouter(prefix="/api/v1", tags=["control"])


class KillSwitchRequest(BaseModel):
    active: bool
    reason: str = Field(default="", max_length=300)


class ChaosRequest(BaseModel):
    fail: bool
    worker_url: Optional[str] = Field(default=None, max_length=500)


@router.get("/control/status")
async def status_view(session: Session = Depends(require_viewer)):
    db = get_database()
    doc = await db.kv.find_one({"key": "kill_switch"})
    return {
        "kill_switch": (doc or {}).get("value", {"active": False}),
        "paypal_mode": settings.paypal_effective_mode,
        "llm_mode": settings.LLM_MODE,
        "environment": settings.APP_ENV,
        "workers": settings.worker_urls,
        "treasury_reserve_micro": settings.TREASURY_RESERVE_MICRO,
        "approval_threshold_micro": settings.APPROVAL_THRESHOLD_MICRO,
        "payout_min_micro": settings.PAYOUT_MIN_MICRO,
        "disclosures": [
            "PayPal sandbox only - no real money moves",
            "Energy price and region multipliers are simulated",
            "LLM proposals are validated by deterministic guardrails",
        ],
    }


@router.post("/control/kill-switch")
async def kill_switch(body: KillSwitchRequest, request: Request,
                      session: Session = Depends(require_operator)):
    db = get_database()

    async def handler() -> dict:
        value = await policy.set_kill_switch(db, body.active, "operator", body.reason)
        await events.emit(db, "control.kill_switch", value, actor="operator")
        await audit.record(db, actor_type="operator", actor_id="operator",
                           action="control.kill_switch", subject_type="system",
                           subject_id="kill_switch", after=value, severity="warning",
                           ip_hash=request_context(request)["ip_hash"])
        return value

    return await mutate(request, body.model_dump(), handler)


@router.get("/workers/health")
async def workers_health(session: Session = Depends(require_viewer)):
    return {"workers": await worker_client.all_worker_health()}


@router.post("/workers/{worker_id}/chaos")
async def chaos(worker_id: str, body: ChaosRequest, request: Request,
                session: Session = Depends(require_operator)):
    db = get_database()
    target = body.worker_url
    if not target:
        agent = await db.agents.find_one({"id": worker_id})
        target = ((agent or {}).get("profile") or {}).get("worker_url")
    if not target:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no worker url for this id")

    async def handler() -> dict:
        result = await worker_client.set_chaos(target, body.fail, db=db)
        await events.emit(db, "worker.chaos", {"worker_id": worker_id, "fail": body.fail,
                                               "ok": result.get("ok")}, actor="operator",
                          )
        await audit.record(db, actor_type="operator", actor_id="operator", action="worker.chaos",
                           subject_type="worker", subject_id=worker_id,
                           detail={"fail": body.fail, "ok": result.get("ok")},
                           severity="warning")
        return result

    return await mutate(request, {"worker_id": worker_id, **body.model_dump()}, handler)
