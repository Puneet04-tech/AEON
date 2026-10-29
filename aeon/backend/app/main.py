"""
AEON FastAPI Application Main Entry Point

Core application setup, middleware, and route registration.
Follows the AEON 7-day blueprint architecture.
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.settings import settings
from app.security import (
    generate_session_token,
    verify_session_token,
    validate_role,
    validate_actor_for_resource,
    default_limiter,
)
from app.db.client import connect_to_mongo, close_mongo_connection, get_database
from app.db.indexes import create_indexes

from app.api.agents import router as api_agents
from app.api.trades import router as api_trades
from app.api.approvals import router as api_approvals
from app.api.funding import router as api_funding

import structlog
import time

logger = structlog.get_logger()

# Configure rate limiter
limiter = default_limiter

app = FastAPI(
    title="AEON API",
    description="Agent-to-Agent Settlement Network for Shared Compute",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS - allow frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.ALLOWED_ORIGIN, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(api_agents)
app.include_router(api_trades)
app.include_router(api_approvals)
app.include_router(api_funding)


# Rate limiting middleware
@app.middleware("http")
async def add_rate_limit_headers(request: Request, call_next):
    """Add rate limit information to response headers."""
    try:
        limit_info = limiter.check(request)
    except Exception:
        limit_info = {"limit": "100", "remaining": "100", "reset": ""}

    response = await call_next(request)
    if hasattr(limit_info, 'remaining'):
        response.headers["X-Rate-Limit-Limit"] = str(limit_info.limit)
        response.headers["X-Rate-Limit-Remaining"] = str(limit_info.remaining)
    return response


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add process time header to responses."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.on_event("startup")
async def startup_db_client():
    """Database connection startup."""
    await connect_to_mongo()
    # Create indexes after connection
    db = get_database()
    await create_indexes(db)
    logger.info("AEON API started", version="0.1.0")


@app.on_event("shutdown")
async def shutdown_db_client():
    """Database connection shutdown."""
    await close_mongo_connection()
    logger.info("AEON API shutting down")


@app.get("/healthz")
async def healthz(request: Request):
    """Health check endpoint."""
    db = get_database()
    return {"status": "ok", "service": "aeon-api", "version": "0.1.0"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "AEON API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/healthz"
    }