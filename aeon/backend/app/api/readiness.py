"""Hackathon submission readiness diagnostics.

This endpoint reports configuration and demo prerequisites without returning
credentials or calling payment-mutating PayPal endpoints.
"""
from fastapi import APIRouter, Depends

from app.db.client import get_database
from app.security.sessions import Session, require_viewer
from app.services import worker_client
from app.settings import settings

router = APIRouter(prefix="/api/v1/hackathon", tags=["hackathon"])


@router.get("/readiness")
async def readiness(session: Session = Depends(require_viewer)):
    db = get_database()
    workers = await worker_client.all_worker_health()
    agents = [doc async for doc in db.agents.find(
        {"role": "provider"}, {"_id": 0, "id": 1, "name": 1, "paypal_email": 1}
    )]
    invalid_receivers = [
        {"id": agent["id"], "name": agent.get("name", agent["id"])}
        for agent in agents
        if not agent.get("paypal_email")
        or agent["paypal_email"].lower().endswith("@example.com")
    ]
    checks = {
        "paypal_sandbox_configured": settings.paypal_effective_mode == "sandbox",
        "paypal_webhook_configured": bool(settings.PAYPAL_WEBHOOK_ID),
        "workers_healthy": bool(workers) and all(worker.get("healthy") for worker in workers),
        "provider_receivers_configured": not invalid_receivers,
        "evidence_available": await db.execution_evidence.count_documents({}) > 0,
        "ledger_invariant": True,
    }
    from app.ledger.service import LedgerService

    checks["ledger_invariant"] = (await LedgerService(db).invariant())["ok"]
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "workers": workers,
        "invalid_receivers": invalid_receivers,
        "trade_count": await db.trades.count_documents({}),
        "evidence_count": await db.execution_evidence.count_documents({}),
        "next_actions": [
            "Set PAYPAL_WEBHOOK_ID after creating the PayPal sandbox webhook."
            if not checks["paypal_webhook_configured"] else "",
            "Replace seeded provider example.com emails with PayPal sandbox receiver emails."
            if invalid_receivers else "",
            "Run one verified trade before recording the demo."
            if not checks["evidence_available"] else "",
        ],
    }
