"""PayPal webhook receiver. Signature is verified before anything is processed."""
import json

import structlog
from fastapi import APIRouter, HTTPException, Request, status

from app.db.client import get_database
from app.paypal import webhooks as webhook_service
from app.paypal.client import PayPalClient
from app.services import audit, events

logger = structlog.get_logger()
router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/paypal")
async def paypal_webhook(request: Request):
    raw = await request.body()
    if len(raw) > 128 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "payload too large")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid JSON")

    db = get_database()
    client = PayPalClient(db)
    verified = await webhook_service.verify_webhook(client, request.headers, raw)
    stored = await webhook_service.store_event(db, event, verified, raw)

    if not verified.get("verified"):
        await audit.record(db, actor_type="system", actor_id="paypal_webhook",
                           action="webhook.rejected", subject_type="webhook_event",
                           subject_id=str((stored or {}).get("event_id", "")),
                           severity="warning",
                           detail={"reason": verified.get("reason", "")})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "webhook signature verification failed")
    if stored and stored.get("processed_at"):
        return {"ok": True, "duplicate": True}

    result = await webhook_service.process_event(db, event)
    await db.webhook_events.update_one({"event_id": (stored or {}).get("event_id")},
                                       {"$set": {"processed_at": __import__("datetime").datetime.now(
                                           __import__("datetime").timezone.utc)}})
    await events.emit(db, "webhook.processed", {"type": event.get("event_type"),
                                                "result": result}, actor="paypal_webhook")
    return {"ok": True, "result": result}
