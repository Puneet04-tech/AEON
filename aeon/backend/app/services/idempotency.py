"""Idempotency-Key support for every state-changing endpoint.

The first request with a key reserves it (unique index), runs the handler and
stores the response. A replay with the same key and body returns the stored
response; the same key with a different body is rejected with 409.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

TTL = timedelta(hours=24)


def request_hash(payload: Any) -> str:
    try:
        blob = json.dumps(payload, sort_keys=True, default=str)
    except TypeError:  # pragma: no cover - defensive
        blob = str(payload)
    return hashlib.sha256(blob.encode()).hexdigest()


async def cached_response(db, key: str, route: str, payload: Any) -> Optional[dict]:
    doc = await db.idempotency_keys.find_one({"key": key})
    if not doc:
        return None
    if doc.get("route") != route:
        raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency-Key reused for a different route")
    if doc.get("request_hash") != request_hash(payload):
        raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency-Key reused with a different body")
    return doc.get("response")


async def run_once(db, key: str, route: str, payload: Any,
                   handler: Callable[[], Awaitable[dict]]) -> tuple[dict, bool]:
    """Return (response, replayed)."""
    if not key:
        return await handler(), False
    if len(key) < 8 or len(key) > 128:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Idempotency-Key must be 8-128 characters")

    existing = await cached_response(db, key, route, payload)
    if existing is not None:
        return existing, True

    doc = {
        "key": key,
        "route": route,
        "request_hash": request_hash(payload),
        "response": None,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + TTL,
    }
    try:
        await db.idempotency_keys.insert_one(doc)
    except DuplicateKeyError:
        stored = await cached_response(db, key, route, payload)
        if stored is not None:
            return stored, True
        raise HTTPException(status.HTTP_409_CONFLICT, "Request with this Idempotency-Key is still in progress")

    try:
        response = await handler()
    except Exception:
        await db.idempotency_keys.delete_one({"key": key})
        raise
    await db.idempotency_keys.update_one({"key": key}, {"$set": {"response": response}})
    return response, False
