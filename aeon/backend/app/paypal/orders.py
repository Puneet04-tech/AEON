"""PayPal Orders v2: create an order for an agent top-up, then capture it."""
from datetime import datetime, timezone
from typing import Optional

import structlog

from app.paypal.client import PayPalClient, PayPalError, micro_to_decimal
from app.settings import settings

logger = structlog.get_logger()


async def create_order(client: PayPalClient, agent_id: str, agent_name: str,
                       amount_micro: int) -> dict:
    if client.is_mock:
        order_id = client.mock_id("ORDER")
        doc = {
            "id": order_id,
            "status": "CREATED",
            "amount_micro": amount_micro,
            "agent_id": agent_id,
            "mock": True,
            "approve_url": f"http://localhost:5173/?mock_approve={order_id}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await client._mock_store(f"paypal_mock_order:{order_id}", doc)
        return doc

    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": agent_id,
            "description": f"AEON funding for {agent_name[:80]}",
            "custom_id": agent_id[:127],
            "amount": {"currency_code": settings.PAYPAL_CURRENCY,
                       "value": micro_to_decimal(amount_micro)},
        }],
        "application_context": {
            "brand_name": "AEON Clearing House",
            "user_action": "PAY_NOW",
            "return_url": settings.PAYPAL_RETURN_URL,
            "cancel_url": settings.PAYPAL_CANCEL_URL,
        },
    }
    body = await client.request("POST", "/v2/checkout/orders", json=payload,
                                headers={"Prefer": "return=representation"})
    approve = next((link["href"] for link in body.get("links", []) if link.get("rel") == "approve"), "")
    return {
        "id": body.get("id"),
        "status": body.get("status", "CREATED"),
        "amount_micro": amount_micro,
        "agent_id": agent_id,
        "mock": False,
        "approve_url": approve,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def capture_order(client: PayPalClient, order_id: str) -> dict:
    if client.is_mock:
        doc = await client._mock_get(f"paypal_mock_order:{order_id}")
        if not doc:
            raise PayPalError("unknown mock order", status=404, code="order_not_found")
        doc["status"] = "COMPLETED"
        doc["capture_id"] = client.mock_id("CAPTURE")
        doc["captured_at"] = datetime.now(timezone.utc).isoformat()
        await client._mock_store(f"paypal_mock_order:{order_id}", doc)
        return {
            "order_id": order_id,
            "status": "COMPLETED",
            "capture_id": doc["capture_id"],
            "amount_micro": doc["amount_micro"],
            "currency": settings.PAYPAL_CURRENCY,
            "payer_email": "mock-payer@example.com",
            "mock": True,
        }

    body = await client.request("POST", f"/v2/checkout/orders/{order_id}/capture", json={},
                                headers={"Prefer": "return=representation"})
    purchase_units = (body.get("purchase_units") or [{}])[0]
    captures = ((purchase_units.get("payments") or {}).get("captures") or [{}])
    capture = captures[0] if captures else {}
    amount = (capture.get("amount") or {})
    from app.paypal.client import to_micro

    return {
        "order_id": body.get("id", order_id),
        "status": capture.get("status", body.get("status", "")),
        "capture_id": capture.get("id", ""),
        "amount_micro": to_micro(amount.get("value", "0")),
        "currency": amount.get("currency_code", settings.PAYPAL_CURRENCY),
        "payer_email": ((body.get("payer") or {}).get("email_address") or ""),
        "mock": False,
    }


async def get_order(client: PayPalClient, order_id: str) -> dict:
    if client.is_mock:
        doc = await client._mock_get(f"paypal_mock_order:{order_id}")
        if not doc:
            raise PayPalError("unknown mock order", status=404, code="order_not_found")
        return doc
    return await client.request("GET", f"/v2/checkout/orders/{order_id}")
