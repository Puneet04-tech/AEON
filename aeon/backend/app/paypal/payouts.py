"""PayPal Payouts v1: one batch from the treasury to net-positive agents.

Money leaves AEON here. The clearing-house model is why a single treasury batch
can settle many internal trades at once.
"""
from datetime import datetime, timezone
from typing import List

import structlog

from app.paypal.client import PayPalClient, PayPalError, micro_to_decimal, to_micro
from app.settings import settings

logger = structlog.get_logger()


async def create_payout(client: PayPalClient, sender_batch_id: str, items: List[dict],
                        email_subject: str = "AEON settlement") -> dict:
    """items: [{sender_item_id, receiver_email, amount_micro, note}]"""
    if client.is_mock:
        payout_batch_id = client.mock_id("PAYOUT")
        doc = {
            "batch_header": {
                "payout_batch_id": payout_batch_id,
                "batch_status": "SUCCESS",
                "sender_batch_id": sender_batch_id,
                "time_created": datetime.now(timezone.utc).isoformat(),
                "amount": {"value": micro_to_decimal(sum(i["amount_micro"] for i in items)),
                           "currency": settings.PAYPAL_CURRENCY},
            },
            "items": [
                {"sender_item_id": item["sender_item_id"],
                 "payout_item_id": client.mock_id("ITEM"),
                 "transaction_status": "SUCCESS",
                 "payout_item": {"receiver": item["receiver_email"],
                                 "amount": {"value": micro_to_decimal(item["amount_micro"]),
                                            "currency": settings.PAYPAL_CURRENCY},
                                 "note": item.get("note", "")}}
                for item in items
            ],
            "mock": True,
        }
        await client._mock_store(f"paypal_mock_payout:{payout_batch_id}", doc)
        return doc

    payload = {
        "sender_batch_header": {
            "sender_batch_id": sender_batch_id,
            "email_subject": email_subject,
            "email_message": "AEON settled your compute earnings. This is PayPal sandbox money.",
        },
        "items": [{
            "recipient_type": "EMAIL",
            "amount": {"value": micro_to_decimal(item["amount_micro"]),
                       "currency": settings.PAYPAL_CURRENCY},
            "receiver": item["receiver_email"],
            "note": item.get("note", "AEON settlement")[:127],
            "sender_item_id": item["sender_item_id"],
        } for item in items],
    }
    return await client.request("POST", "/v1/payments/payouts", json=payload)


async def get_payout(client: PayPalClient, payout_batch_id: str) -> dict:
    if client.is_mock:
        doc = await client._mock_get(f"paypal_mock_payout:{payout_batch_id}")
        if not doc:
            raise PayPalError("unknown mock payout", status=404, code="payout_not_found")
        return doc
    return await client.request("GET", f"/v1/payments/payouts/{payout_batch_id}")


def normalize_items(payload: dict) -> List[dict]:
    """Map PayPal's payout item shape onto AEON's settlement item shape."""
    normalized = []
    for item in payload.get("items", []):
        payout_item = item.get("payout_item") or {}
        amount = (payout_item.get("amount") or {}).get("value", "0")
        normalized.append({
            "sender_item_id": item.get("sender_item_id") or (item.get("payout_item_id", "")),
            "payout_item_id": item.get("payout_item_id", ""),
            "status": (item.get("transaction_status") or "").upper(),
            "amount_micro": to_micro(amount),
            "receiver": payout_item.get("receiver", ""),
            "error": item.get("errors"),
        })
    return normalized
