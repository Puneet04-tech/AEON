"""Signed dispatch to provider worker services.

Every request carries a timestamp, a single-use nonce and an HMAC signature over
method, path, timestamp, nonce and body. Nonces are stored by the API so a
captured request cannot be replayed against a worker.
"""
import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import httpx
import structlog

from app.security.hmac_signing import sign
from app.settings import settings

logger = structlog.get_logger()


class WorkerError(Exception):
    def __init__(self, message: str, code: str = "worker_error"):
        super().__init__(message)
        self.code = code


def canonical_digest(result: dict) -> str:
    return hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def _store_nonce(db, nonce: str) -> None:
    await db.nonces.update_one(
        {"nonce": nonce},
        {"$set": {"nonce": nonce, "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)}},
        upsert=True,
    )


async def dispatch_job(db, worker_url: str, job: dict) -> dict:
    """POST a job to a worker and return its verified result envelope."""
    path = "/jobs"
    body = json.dumps(job, sort_keys=True, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    signature = sign("POST", path, timestamp, nonce, body)
    await _store_nonce(db, nonce)
    headers = {
        "Content-Type": "application/json",
        "X-AEON-Timestamp": timestamp,
        "X-AEON-Nonce": nonce,
        "X-AEON-Signature": signature,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.WORKER_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{worker_url.rstrip('/')}{path}", content=body, headers=headers)
    except httpx.HTTPError as exc:
        raise WorkerError(f"worker unreachable: {exc}", "worker_unreachable")

    if response.status_code == 503:
        raise WorkerError("worker is in a forced failure state", "worker_unavailable")
    if response.status_code == 401:
        raise WorkerError("worker rejected the request signature", "signature_rejected")
    if response.status_code != 200:
        raise WorkerError(f"worker returned {response.status_code}", "worker_http_error")

    try:
        envelope = response.json()
    except ValueError:
        raise WorkerError("worker returned invalid JSON", "bad_response")

    result = envelope.get("result")
    checksum = envelope.get("checksum")
    if checksum != canonical_digest(result or {}):
        raise WorkerError("worker result checksum mismatch", "checksum_mismatch")
    return envelope


async def worker_health(worker_url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{worker_url.rstrip('/')}/health")
        if response.status_code != 200:
            return {"url": worker_url, "healthy": False, "error": f"http {response.status_code}"}
        payload = response.json()
        payload["url"] = worker_url
        return payload
    except httpx.HTTPError as exc:
        return {"url": worker_url, "healthy": False, "error": str(exc)[:120]}


async def all_worker_health() -> List[dict]:
    return [await worker_health(url) for url in settings.worker_urls]


async def set_chaos(worker_url: str, fail: bool, db=None) -> dict:
    """Flip the worker's signed chaos switch (real detection, real recovery)."""
    path = "/admin/chaos"
    body = json.dumps({"fail": fail}, sort_keys=True, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    signature = sign("POST", path, timestamp, nonce, body)
    if db is not None:
        await _store_nonce(db, nonce)
    headers = {
        "Content-Type": "application/json",
        "X-AEON-Timestamp": timestamp,
        "X-AEON-Nonce": nonce,
        "X-AEON-Signature": signature,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(f"{worker_url.rstrip('/')}{path}", content=body, headers=headers)
        return {"url": worker_url, "ok": response.status_code == 200, "fail": fail,
                "status": response.status_code}
    except httpx.HTTPError as exc:
        return {"url": worker_url, "ok": False, "fail": fail, "error": str(exc)[:120]}
