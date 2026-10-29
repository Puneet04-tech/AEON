"""PayPal webhook verification and event processing.

Every event is stored with a unique event id (dedupe), its verification result
and a hash of the raw body. Processing is idempotent.
"""
import hashlib
from datetime import datetime, timezone
from typing import Optional

import structlog

from app.paypal.client import PayPalClient, PayPalError
from app.security.hmac_signing import sign_bytes
from app.settings import settings

logger = structlog.get_logger()

HEADERS = {
    "auth_algo": "paypal-auth-algo",
    "cert_url": "paypal-cert-url",
    "transmission_id": "paypal-transmission-id",
    "transmission_sig": "paypal-transmission-sig",
    "transmission_time": "paypal-transmission-time",
}


async def verify_webhook(client: PayPalClient, headers, raw_body: bytes) -> dict:
    """Return {'verified': bool, 'reason': str}."""
    if client.is_mock:
        expected = sign_bytes(raw_body)
        provided = headers.get("paypal-transmission-sig", "")
        verified = bool(provided) and provided == expected
        return {"verified": verified, "reason": "mock_hmac" if verified else "mock_signature_mismatch"}

    if not settings.PAYPAL_WEBHOOK_ID:
        return {"verified": False, "reason": "webhook_id_not_configured"}
    try:
        event = __import__("json").loads(raw_body)
    except ValueError:
        return {"verified": False, "reason": "invalid_json"}
    payload = {
        "auth_algo": headers.get(HEADERS["auth_algo"], ""),
        "cert_url": headers.get(HEADERS["cert_url"], ""),
        "transmission_id": headers.get(HEADERS["transmission_id"], ""),
        "transmission_sig": headers.get(HEADERS["transmission_sig"], ""),
        "transmission_time": headers.get(HEADERS["transmission_time"], ""),
        "webhook_id": settings.PAYPAL_WEBHOOK_ID,
        "webhook_event": event,
    }
    try:
        result = await client.request("POST", "/v1/notifications/verify-webhook-signature", json=payload)
    except PayPalError as exc:
        return {"verified": False, "reason": f"verify_call_failed: {exc.code}"}
    status = result.get("verification_status")
    return {"verified": status == "SUCCESS", "reason": status or "unknown"}


async def store_event(db, event: dict, verified: dict, raw_body: bytes) -> Optional[dict]:
    event_id = event.get("id") or hashlib.sha256(raw_body).hexdigest()[:32]
    existing = await db.webhook_events.find_one({"event_id": event_id})
    if existing:
        return existing
    doc = {
        "event_id": event_id,
        "type": event.get("event_type", "unknown"),
        "verified": bool(verified.get("verified")),
        "verify_reason": verified.get("reason", ""),
        "received_at": datetime.now(timezone.utc),
        "processed_at": None,
        "resource_ref": (event.get("resource") or {}).get("id", ""),
        "raw_hash": hashlib.sha256(raw_body).hexdigest(),
    }
    await db.webhook_events.insert_one({**doc})
    return doc


async def process_event(db, event: dict) -> dict:
    """Route a verified event to the funding or settlement reconciler."""
    from app.services import funding, settlement

    event_type = (event.get("event_type") or "").upper()
    resource = event.get("resource") or {}

    if event_type in {"PAYMENT.CAPTURE.COMPLETED", "CHECKOUT.ORDER.COMPLETED"}:
        return await funding.on_capture_webhook(db, resource)
    if event_type == "CHECKOUT.ORDER.APPROVED":
        return {"handled": True, "action": "order_approved", "note": "awaiting capture"}
    if event_type.startswith("PAYOUTS-ITEM") or event_type.startswith("PAYOUT."):
        return await settlement.on_payout_webhook(db, event_type, resource)
    return {"handled": False, "action": "ignored", "type": event_type}
