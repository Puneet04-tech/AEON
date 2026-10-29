"""HMAC signing for idempotency keys and request verification"""
import hmac
import hashlib
import base64
from typing import Any, Optional

# HMAC secret - should be set via environment variable
HMAC_SECRET = __import__("os").getenv("HMAC_SHARED_SECRET", "default_shared_secret_change_me")


def sign_payload(payload: dict, secret: str = None) -> str:
    """Sign a payload dictionary and return base64-encoded signature."""
    if secret is None:
        secret = HMAC_SECRET
    payload_bytes = str(sorted(payload.items())).encode()
    signature = hmac.new(
        secret.encode(), payload_bytes, hashlib.sha256
    ).digest()
    return base64.b64encode(signature).decode()


def verify_payload(token: str, payload: dict = None, secret: str = None) -> Optional[dict]:
    """Verify a payload signature. Returns payload if valid, None otherwise."""
    if secret is None:
        secret = HMAC_SECRET
    
    # If payload is provided, re-sign and compare
    if payload is not None:
        expected_signature = sign_payload(payload, secret)
        # Compare with the provided token
        try:
            # token could be just the signature or payload:sig format
            if ":" in token:
                _, sig = token.split(":", 1)
            else:
                sig = token
            
            signature_bytes = base64.b64decode(sig)
            expected_bytes = base64.b64decode(expected_signature)
            
            return hmac.compare_digest(signature_bytes, expected_bytes)
        except Exception:
            return False
    
    return None


def compute_hmac(data: bytes, key: bytes = None) -> str:
    """Compute HMAC-SHA256 of data with optional key."""
    if key is None:
        key = HMAC_SECRET.encode()
    return hmac.new(key, data, hashlib.sha256).hexdigest()