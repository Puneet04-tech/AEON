"""PayPal funding, webhooks and net settlement (mock adapter, our code paths)."""
import json

import pytest

from app.ledger.service import LedgerService
from app.paypal import webhooks as webhook_service
from app.paypal.client import PayPalClient, micro_to_decimal, to_micro
from app.security.hmac_signing import sign_bytes
from app.services import funding as funding_service
from app.services import settlement as settlement_service
from app.settings import settings
from tests.conftest import fake_dispatch


def test_money_conversion_is_exact():
    assert micro_to_decimal(1_000_000) == "1.00"
    assert micro_to_decimal(10_000) == "0.01"
    assert to_micro("0.01") == 10_000
    assert to_micro("1.23") == 1_230_000


async def test_funding_capture_credits_ledger(db, seeded):
    ledger = LedgerService(db)
    before = await ledger.balance("agt_atlas")

    funding = await funding_service.create_funding(db, "agt_atlas", 2_000_000)
    assert funding["state"] == "CREATED"
    assert funding["mock"] is True  # no sandbox credentials in tests

    captured = await funding_service.capture_funding(db, funding["id"])
    assert captured["state"] == "CAPTURED"
    assert await ledger.balance("agt_atlas") == before + 2_000_000
    assert (await ledger.invariant())["ok"] is True


async def test_capture_is_idempotent(db, seeded):
    ledger = LedgerService(db)
    funding = await funding_service.create_funding(db, "agt_atlas", 1_000_000)
    await funding_service.capture_funding(db, funding["id"])
    balance = await ledger.balance("agt_atlas")
    await funding_service.capture_funding(db, funding["id"])
    assert await ledger.balance("agt_atlas") == balance


async def test_funding_guardrail_blocks_oversize(db, seeded):
    with pytest.raises(ValueError, match="funding_cap"):
        await funding_service.create_funding(db, "agt_atlas", settings.FUNDING_MAX_MICRO + 1)


async def test_capture_with_wrong_amount_is_not_credited(db, seeded, monkeypatch):
    ledger = LedgerService(db)
    funding = await funding_service.create_funding(db, "agt_atlas", 1_000_000)
    before = await ledger.balance("agt_atlas")

    from app.paypal import orders

    async def wrong_amount(client, order_id):
        return {"order_id": order_id, "status": "COMPLETED", "capture_id": "cap",
                "amount_micro": 5, "currency": "USD", "payer_email": "", "mock": True}

    monkeypatch.setattr(orders, "capture_order", wrong_amount)
    with pytest.raises(Exception):
        await funding_service.capture_funding(db, funding["id"])
    assert await ledger.balance("agt_atlas") == before
    doc = await db.funding_requests.find_one({"id": funding["id"]})
    assert doc["state"] == "AMOUNT_MISMATCH"


async def test_webhook_requires_valid_signature(db, seeded):
    event = {"id": "WH-1", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {"id": "cap"}}
    raw = json.dumps(event).encode()
    client = PayPalClient(db)
    forged = await webhook_service.verify_webhook(client, {"paypal-transmission-sig": "deadbeef"}, raw)
    assert forged["verified"] is False
    good = await webhook_service.verify_webhook(
        client, {"paypal-transmission-sig": sign_bytes(raw)}, raw)
    assert good["verified"] is True


async def test_webhook_credits_funding_once(seeded, client, db):
    funding = await funding_service.create_funding(db, "agt_atlas", 1_500_000)
    order_id = funding["paypal_order_id"]
    event = {
        "id": "WH-CAPTURE-1",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": "CAP-1",
            "amount": {"value": "1.50", "currency_code": "USD"},
            "supplementary_data": {"related_ids": {"order_id": order_id}},
        },
    }
    raw = json.dumps(event).encode()
    headers = {"paypal-transmission-sig": sign_bytes(raw), "Content-Type": "application/json"}

    first = await client.post("/webhooks/paypal", content=raw, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["result"]["action"] == "credited"

    balance = await LedgerService(db).balance("agt_atlas")
    second = await client.post("/webhooks/paypal", content=raw, headers=headers)
    assert second.status_code == 200
    assert await LedgerService(db).balance("agt_atlas") == balance

    forged = await client.post("/webhooks/paypal", content=raw,
                               headers={"paypal-transmission-sig": "bad"})
    assert forged.status_code == 400


async def test_settlement_pays_net_positive_agents(db, seeded, monkeypatch):
    from app.services import trades as trades_service

    monkeypatch.setattr(trades_service, "dispatch_job", fake_dispatch())
    job = {"type": "image_resize", "size": 640 * 480, "params": {}, "deadline_s": 30}
    trade = await trades_service.run_trade(db, "agt_atlas", job, seller_id="agt_cirrus")
    assert trade["state"] == "SETTLED"

    ledger = LedgerService(db)
    seller_balance = await ledger.balance("agt_cirrus")
    assert seller_balance > 0

    batch = await settlement_service.propose_settlement(db, actor="operator", has_approval=True)
    assert batch["state"] == "SUCCEEDED", batch
    assert batch["simulated"] is True
    assert batch["totals"]["items"] >= 1
    assert await ledger.balance("agt_cirrus") == 0
    assert (await ledger.invariant())["ok"] is True

    items = await settlement_service.list_payouts(db, settlement_id=batch["id"])
    seller_item = next(i for i in items if i["agent_id"] == "agt_cirrus")
    assert seller_item["state"] == "SUCCESS"
    assert seller_item["paypal_item_id"]


async def test_settlement_requires_approval_above_threshold(db, seeded, monkeypatch):
    from app.services import trades as trades_service

    monkeypatch.setattr(settlement_service, "_approval_threshold", lambda: 10)
    monkeypatch.setattr(trades_service, "dispatch_job", fake_dispatch())
    job = {"type": "image_resize", "size": 640 * 480, "params": {}, "deadline_s": 30}
    await trades_service.run_trade(db, "agt_atlas", job, seller_id="agt_cirrus")

    draft = await settlement_service.propose_settlement(db, actor="operator", has_approval=False)
    assert draft["state"] == "AWAITING_APPROVAL"
    assert draft["approval_id"]

    from app.services import approvals

    result = await approvals.decide(db, draft["approval_id"], "APPROVED", actor="operator")
    assert result["execution"]["state"] == "SUCCEEDED"


async def test_settlement_failure_reverses_funds(db, seeded, monkeypatch):
    from app.paypal import payouts
    from app.paypal.client import PayPalError
    from app.services import trades as trades_service

    monkeypatch.setattr(trades_service, "dispatch_job", fake_dispatch())
    job = {"type": "image_resize", "size": 640 * 480, "params": {}, "deadline_s": 30}
    await trades_service.run_trade(db, "agt_atlas", job, seller_id="agt_cirrus")
    ledger = LedgerService(db)
    balance = await ledger.balance("agt_cirrus")

    async def boom(client, sender_batch_id, items, email_subject=""):
        raise PayPalError("payouts exploded", code="network")

    monkeypatch.setattr(payouts, "create_payout", boom)
    with pytest.raises(PayPalError):
        await settlement_service.propose_settlement(db, actor="operator", has_approval=True)

    assert await ledger.balance("agt_cirrus") == balance  # reversed back to available
    assert (await ledger.invariant())["ok"] is True
