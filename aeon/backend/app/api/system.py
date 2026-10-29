"""Health, metrics and public config for judges."""
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.db.client import get_database
from app.ledger.service import LedgerService
from app.security.sessions import operator_login_configured
from app.services.events import bus
from app.settings import settings

router = APIRouter(tags=["system"])

STARTED_AT = datetime.now(timezone.utc)
_counters = {"requests": 0, "errors": 0}


def count_request(error: bool = False) -> None:
    _counters["requests"] += 1
    if error:
        _counters["errors"] += 1


@router.get("/healthz")
async def healthz():
    db = get_database()
    mongo_ok = True
    try:
        await db.command("ping")
    except Exception:
        mongo_ok = False
    return {
        "status": "ok" if mongo_ok else "degraded",
        "service": settings.SERVICE_NAME,
        "version": settings.APP_VERSION,
        "mongo": mongo_ok,
        "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
    }


@router.get("/metrics")
async def metrics():
    db = get_database()
    ledger = LedgerService(db)
    return {
        "requests": _counters["requests"],
        "errors": _counters["errors"],
        "sse_subscribers": bus.subscriber_count(),
        "agents": await db.agents.count_documents({}),
        "trades": await db.trades.count_documents({}),
        "ledger_entries": await db.ledger_entries.count_documents({}),
        "treasury_float_micro": await ledger.treasury_float_micro(),
        "invariant_ok": (await ledger.invariant())["ok"],
        "llm_mode": settings.LLM_MODE,
        "paypal_mode": settings.paypal_effective_mode,
    }


@router.get("/api/v1/config")
async def public_config():
    """Everything the dashboard needs to render honest labels."""
    return {
        "environment": settings.APP_ENV,
        "paypal_mode": settings.paypal_effective_mode,
        "paypal_env": "sandbox",
        "llm_mode": settings.LLM_MODE,
        "judge_session_minutes": settings.JUDGE_SESSION_MINUTES,
        "judge_scenario_quota": settings.JUDGE_SCENARIO_QUOTA,
        "operator_login": operator_login_configured(),
        "currency": "USD",
        "money_unit": "micro-USD (1 USD = 1,000,000)",
        "disclosures": [
            "PayPal sandbox only: no real money moves.",
            "Weather is real (Open-Meteo); energy price and regions are simulated.",
            "Agent decisions use Cloudflare Workers AI, validated by deterministic guardrails.",
        ],
    }
