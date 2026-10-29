"""HMAC verification and replay protection for signed job requests."""
import hashlib
import hmac
import time
from typing import Dict, Optional, Tuple

from app.settings import settings

_nonces: Dict[str, float] = {}


def canonical_string(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    digest = hashlib.sha256(body).hexdigest()
    return "\n".join([method.upper(), path, timestamp, nonce, digest])


def expected_signature(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    message = canonical_string(method, path, timestamp, nonce, body).encode()
    return hmac.new(settings.hmac_secret.encode(), message, hashlib.sha256).hexdigest()


def check_signature(method: str, path: str, timestamp: str, nonce: str, body: bytes,
                    signature: str) -> Tuple[bool, str]:
    if not timestamp or not nonce or not signature:
        return False, "missing_headers"
    try:
        ts = int(timestamp)
    except ValueError:
        return False, "bad_timestamp"
    if abs(time.time() - ts) > settings.clock_skew_seconds:
        return False, "stale_timestamp"
    if len(nonce) < 8:
        return False, "bad_nonce"
    if not hmac.compare_digest(expected_signature(method, path, timestamp, nonce, body), signature):
        return False, "bad_signature"
    return True, "ok"


def consume_nonce(nonce: str) -> bool:
    """Return True the first time a nonce is seen, False on replay."""
    now = time.time()
    for key, expires in list(_nonces.items()):
        if expires < now:
            _nonces.pop(key, None)
    if nonce in _nonces:
        return False
    _nonces[nonce] = now + settings.nonce_ttl_seconds
    return True


def reset_nonces() -> Optional[None]:
    _nonces.clear()
    return None
