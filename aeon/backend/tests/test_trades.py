"""Trade lifecycle: happy path, guardrail rejection, worker failure + reroute."""
import pytest

from app.ledger.service import AGENT_AVAILABLE, AGENT_DISPUTE_HOLD, AGENT_ESCROW, LedgerService
from app.services import trades as trades_service
from tests.conftest import fake_dispatch

JOB = {"type": "image_resize", "size": 640 * 480, "params": {"width": 320, "height": 240},
       "deadline_s": 30}


async def test_happy_path_settles_and_balances(db, seeded, monkeypatch):
    monkeypatch.setattr(trades_service, "dispatch_job", fake_dispatch())
    trade = await trades_service.run_trade(db, "agt_atlas", JOB, seller_id="agt_cirrus")

    assert trade["state"] == "SETTLED", trade
    assert trade["agreed"]["price_micro"] > 0
    assert trade["metering"]["cpu_s"] > 0
    assert trade["sla"]["breached"] is False

    ledger = LedgerService(db)
    assert await ledger.balance("agt_atlas", AGENT_ESCROW) == 0
    assert await ledger.balance("agt_cirrus", AGENT_AVAILABLE) > 0
    assert (await ledger.invariant())["ok"] is True
    assert trade["negotiation"]["rounds"] >= 1


async def test_dispute_holds_net_proceeds_not_gross(db, seeded, client, auth, monkeypatch):
    """The provider is credited price - fee, so the hold must use that amount."""
    monkeypatch.setattr(trades_service, "dispatch_job", fake_dispatch())
    trade = await trades_service.run_trade(db, "agt_atlas", JOB, seller_id="agt_cirrus")
    assert trade["state"] == "SETTLED"
    settlement = trade["settlement"]

    response = await client.post(
        f"/api/v1/trades/{trade['id']}/dispute",
        json={"reason": "checksum mismatch observed in the evidence envelope"},
        headers={**auth, "Idempotency-Key": "test-dispute-hold-1"},
    )
    assert response.status_code == 201, response.text
    dispute = response.json()
    expected = settlement["price_micro"] - settlement["fee_micro"] - settlement["penalty_micro"]
    assert dispute["amount_micro"] == expected

    ledger = LedgerService(db)
    assert await ledger.balance("agt_cirrus", AGENT_DISPUTE_HOLD) == expected
    assert (await ledger.invariant())["ok"] is True


async def test_negotiation_transcript_is_stored(db, seeded, monkeypatch):
    monkeypatch.setattr(trades_service, "dispatch_job", fake_dispatch())
    trade = await trades_service.run_trade(db, "agt_atlas", JOB, seller_id="agt_cirrus")
    transcript = await trades_service.negotiation_transcript(db, trade["id"])
    assert transcript
    for row in transcript:
        assert row["from"] in {"agt_atlas", "agt_cirrus"}
        assert isinstance(row["offer"]["price_micro"], int)
        assert row["guardrail"]["passed"] is True
        assert row["llm"]["source"] in {"fallback", "cache", "replay", "live"}


async def test_guardrail_rejects_over_cap(db, seeded, monkeypatch):
    monkeypatch.setattr(trades_service, "dispatch_job", fake_dispatch())
    await db.agents.update_one({"id": "agt_atlas"},
                              {"$set": {"policy.per_trade_cap_micro": 1,
                                        "policy.price_band_bps": 9000}})
    trade = await trades_service.run_trade(db, "agt_atlas", JOB, seller_id="agt_cirrus")
    assert trade["state"] == "REJECTED_BY_GUARDRAIL"
    assert trade["guardrail"]["passed"] is False
    assert trade["guardrail"]["failed"]
    ledger = LedgerService(db)
    assert await ledger.balance("agt_atlas", AGENT_ESCROW) == 0


async def test_insufficient_funds_is_rejected(db, seeded, monkeypatch):
    monkeypatch.setattr(trades_service, "dispatch_job", fake_dispatch())
    await db.agents.update_one({"id": "agt_boreal"},
                              {"$set": {"policy.per_trade_cap_micro": 50_000_000,
                                        "policy.daily_cap_micro": 50_000_000}})
    # drain Boreal's balance so escrow cannot be funded
    ledger = LedgerService(db)
    await db.wallets.update_one({"agent_id": "agt_boreal"}, {"$set": {"available_micro": 1}})
    trade = await trades_service.run_trade(db, "agt_boreal", JOB, seller_id="agt_cirrus")
    assert trade["state"] == "REJECTED_BY_GUARDRAIL"
    assert trade["failure"]["code"] in {"insufficient_funds", "guardrail"}
    assert await ledger.balance("agt_boreal", AGENT_AVAILABLE) == 1
    assert await ledger.balance("agt_boreal", AGENT_ESCROW) == 0


async def test_worker_failure_reroutes_and_penalises(db, seeded, monkeypatch):
    atlas = await db.agents.find_one({"id": "agt_atlas"})
    cirrus = await db.agents.find_one({"id": "agt_cirrus"})
    dunlin = await db.agents.find_one({"id": "agt_dunlin"})
    failing_url = cirrus["profile"]["worker_url"]
    good_dispatch = fake_dispatch()
    calls = []

    async def flaky(db_, worker_url, job):
        calls.append(worker_url)
        if worker_url == failing_url:
            from app.services.worker_client import WorkerError

            raise WorkerError("forced chaos", "worker_unavailable")
        return await good_dispatch(db_, worker_url, job)

    monkeypatch.setattr(trades_service, "dispatch_job", flaky)
    before_bond = await LedgerService(db).balance("agt_cirrus", "agent_bond")

    trade = await trades_service.run_trade(db, "agt_atlas", JOB, seller_id="agt_cirrus",
                                           allow_reroute=True)
    assert trade["state"] == "SETTLED", trade
    assert len(calls) >= 2
    assert dunlin["profile"]["worker_url"] in calls

    original = await db.trades.find_one({"id": trade["links"]["rerouted_from"]})
    assert original["state"] == "FAILED"
    assert original["links"]["rerouted_to"] == trade["id"]
    assert original["failure"]["code"] == "worker_unavailable"

    ledger = LedgerService(db)
    assert await ledger.balance("agt_cirrus", "agent_bond") < before_bond  # penalty booked
    assert (await ledger.invariant())["ok"] is True


async def test_kill_switch_blocks_trades(db, seeded, monkeypatch):
    monkeypatch.setattr(trades_service, "dispatch_job", fake_dispatch())
    from app.guardrails import policy

    await policy.set_kill_switch(db, True, "test", "stop everything")
    with pytest.raises(ValueError, match="kill_switch_active"):
        await trades_service.run_trade(db, "agt_atlas", JOB, seller_id="agt_cirrus")


async def test_trade_api_requires_auth(seeded, client):
    response = await client.post("/api/v1/trades", json={"buyer_id": "agt_atlas", "job": JOB})
    assert response.status_code == 401


async def test_trade_api_run_and_fetch(seeded, client, auth, monkeypatch):
    monkeypatch.setattr(trades_service, "dispatch_job", fake_dispatch())
    response = await client.post("/api/v1/trades", headers=auth,
                                 json={"buyer_id": "agt_atlas", "seller_id": "agt_cirrus", "job": JOB})
    assert response.status_code == 201, response.text
    trade = response.json()
    assert trade["state"] == "SETTLED"

    detail = await client.get(f"/api/v1/trades/{trade['id']}", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["negotiation_transcript"]
