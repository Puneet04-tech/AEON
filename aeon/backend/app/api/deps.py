"""Shared API dependencies: database, idempotency, request context."""
from typing import Awaitable, Callable, Optional

from fastapi import HTTPException, Request, status

from app.db.client import get_database
from app.security.input_guard import InputRejected, reject_unsafe_keys
from app.services.audit import hash_ip
from app.services.idempotency import run_once


async def db_dependency():
    return get_database()


def request_context(request: Request) -> dict:
    ip = request.client.host if request.client else ""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    return {
        "request_id": request.headers.get("x-request-id", "")[:64],
        "ip_hash": hash_ip(ip),
        "user_agent": request.headers.get("user-agent", "")[:200],
    }


def idempotency_key(request: Request) -> str:
    return request.headers.get("Idempotency-Key", "")


async def mutate(request: Request, payload: dict,
                 handler: Callable[[], Awaitable[dict]]) -> dict:
    """Run a state-changing handler under the request's Idempotency-Key."""
    try:
        reject_unsafe_keys(payload)
    except InputRejected as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    key = idempotency_key(request)
    route = f"{request.method} {request.url.path}"
    response, replayed = await run_once(get_database(), key, route, payload, handler)
    if replayed:
        return {**response, "_replayed": True}
    return response


async def optional_session(request: Request) -> Optional[object]:
    from app.security.sessions import current_session

    try:
        return await current_session(request)
    except HTTPException:
        return None
