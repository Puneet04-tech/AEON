"""HMAC request signing used for worker job dispatch and PayPal-style webhooks.

Canonical string: METHOD \n PATH \n TIMESTAMP \n NONCE \n SHA256(body)
Signatures are compared with hmac.compare_digest and never logged.
"""
import hashlib
import hmac
import time
from typing import Optional

from app.settings import settings

MAX_SKEW_SECONDS = 300


def _secret(secret: Optional[str]) -> bytes:
    return (secret or settings.HMAC_SHARED_SECRET).encode()


def body_digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def canonical_string(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    return "\n".join([method.upper(), path, timestamp, nonce, body_digest(body)])


def sign(method: str, path: str, timestamp: str, nonce: str, body: bytes,
         secret: Optional[str] = None) -> str:
    msg = canonical_string(method, path, timestamp, nonce, body).encode()
    return hmac.new(_secret(secret), msg, hashlib.sha256).hexdigest()


def sign_bytes(data: bytes, secret: Optional[str] = None) -> str:
    return hmac.new(_secret(secret), data, hashlib.sha256).hexdigest()


def verify(method: str, path: str, timestamp: str, nonce: str, body: bytes,
           signature: str, secret: Optional[str] = None,
           now: Optional[int] = None) -> tuple[bool, str]:
    """Return (ok, reason). Rejects stale timestamps before touching the body."""
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False, "bad_timestamp"
    now = int(time.time()) if now is None else now
    if abs(now - ts) > MAX_SKEW_SECONDS:
        return False, "stale_timestamp"
    if not nonce or len(nonce) < 8:
        return False, "bad_nonce"
    expected = sign(method, path, timestamp, nonce, body, secret)
    if not hmac.compare_digest(expected, signature or ""):
        return False, "bad_signature"
    return True, "ok"
