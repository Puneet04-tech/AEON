"""AEON API application.

FastAPI app with security middleware, all routers and static dashboard serving.
"""
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import agents, approvals, audit, control, demo, events, forecasts, funding, ledger, loans, mcp
from app.api import scenarios as scenarios_api
from app.api import session as session_api
from app.api import settlement as settlement_api
from app.api import system, trades as trades_api, webhooks
from app.api import trust as trust_api
from app.api import readiness as readiness_api
from app.db.client import close_mongo_connection, connect_to_mongo, get_database
from app.db.indexes import create_indexes
from app.db.validators import apply_validators
from app.security.input_guard import InputRejected, reject_unsafe_keys
from app.security.rate_limit import SlidingWindowLimiter, client_key
from app.settings import settings
from app.api.system import count_request

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
)
logger = structlog.get_logger()

rate_limiter = SlidingWindowLimiter(settings.RATE_LIMIT_WINDOW, settings.RATE_LIMIT_MAX)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.assert_production_safe()
    await connect_to_mongo()
    db = get_database()
    await create_indexes(db)
    await apply_validators(db)
    if settings.AUTO_SEED and await db.agents.count_documents({}) == 0:
        from app.db.seed import seed

        await seed(db)
        logger.info("demo_seed_applied")
    from app.db.seed import repair_worker_urls

    repaired = await repair_worker_urls(db)
    if repaired:
        logger.info("startup_worker_url_repair", fixed=repaired)
    logger.info("aeon_api_started", version=settings.APP_VERSION,
                paypal_mode=settings.paypal_effective_mode, llm_mode=settings.LLM_MODE)
    yield
    await close_mongo_connection()
    logger.info("aeon_api_stopped")


app = FastAPI(
    title="AEON - Agent-to-Agent Settlement Network",
    description="Clearing house for AI agents that trade compute and settle through PayPal sandbox.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-Id"],
    expose_headers=["X-Request-Id", "X-RateLimit-Remaining"],
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


@app.middleware("http")
async def security_and_limits(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    started = time.perf_counter()

    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 1024 * 1024:
            return JSONResponse({"detail": "payload too large"}, status_code=413)
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            raw = await request.body()
            try:
                import json

                reject_unsafe_keys(json.loads(raw or b"{}"))
            except InputRejected as exc:
                return JSONResponse({"detail": str(exc)}, status_code=400)
            except ValueError:
                if request.url.path == "/mcp":
                    return JSONResponse({"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32700, "message": "parse error"}},
                                        status_code=400)
                return JSONResponse({"detail": "invalid JSON"}, status_code=400)
            request._body = raw  # type: ignore[attr-defined]
            body_sent = False

            async def receive_body():
                nonlocal body_sent
                if body_sent:
                    return {"type": "http.request", "body": b"", "more_body": False}
                body_sent = True
                return {"type": "http.request", "body": raw, "more_body": False}

            request._receive = receive_body  # type: ignore[attr-defined]

    # Only API traffic is limited. Static assets and the SSE stream are not:
    # a 429 on the stream makes EventSource retry every few seconds, which would
    # feed the limiter and lock a browser out of the console after a refresh.
    path = request.url.path
    limited = path.startswith("/api/") and path != "/api/v1/events/stream"
    if limited:
        allowed, remaining, _ = rate_limiter.hit(client_key(request))
        if not allowed:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429,
                                headers={"Retry-After": str(settings.RATE_LIMIT_WINDOW)})
    else:
        remaining = settings.RATE_LIMIT_MAX

    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Request-Id"] = request_id
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-Process-Time"] = f"{time.perf_counter() - started:.4f}"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    count_request(error=response.status_code >= 500)
    return response


app.include_router(system.router)
app.include_router(session_api.router)
app.include_router(agents.router)
app.include_router(trades_api.router)
app.include_router(trust_api.router)
app.include_router(readiness_api.router)
app.include_router(ledger.router)
app.include_router(funding.router)
app.include_router(settlement_api.router)
app.include_router(approvals.router)
app.include_router(audit.router)
app.include_router(mcp.router)
app.include_router(demo.router)
app.include_router(control.router)
app.include_router(scenarios_api.router)
app.include_router(forecasts.router)
app.include_router(loans.router)
app.include_router(events.router)
app.include_router(webhooks.router)


@app.exception_handler(InputRejected)
async def input_rejected_handler(request: Request, exc: InputRejected):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


DASHBOARD_DIR = Path(__file__).resolve().parents[2] / settings.DASHBOARD_DIR
if DASHBOARD_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")


@app.get("/")
async def root():
    return {
        "service": "AEON",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/healthz",
        "dashboard": "/" if DASHBOARD_DIR.exists() else "run the dashboard dev server on :5173",
    }
