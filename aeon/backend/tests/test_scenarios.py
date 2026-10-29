"""Guided scenarios run end to end and leave the ledger balanced."""
import pytest

from app.ledger.service import LedgerService
from app.services import scenarios, trades as trades_service
from tests.conftest import fake_dispatch


@pytest.fixture
def patch_worker(monkeypatch):
    monkeypatch.setattr(trades_service, "dispatch_job", fake_dispatch())


async def test_s1_happy_path(db, seeded, patch_worker):
    run = await scenarios.run_scenario(db, "S1", actor="judge")
    assert run["state"] == "COMPLETED", run
    steps = {step["step"]: step for step in run["steps"]}
    assert steps["trade_finished"]["detail"]["state"] == "SETTLED"
    assert steps["ledger_checked"]["detail"]["ok"] is True


async def test_s3_reservation_and_resale(db, seeded, monkeypatch):
    async def offline_weather():
        return {"source": "fallback", "hourly_temps_c": [21.0] * 6, "temp_c": 21.0}

    monkeypatch.setattr(scenarios.forecasts, "_fetch_weather", offline_weather)
    run = await scenarios.run_scenario(db, "S3", actor="judge")
    assert run["state"] == "COMPLETED", run
    steps = {step["step"]: step for step in run["steps"]}
    assert steps["reservation_created"]["detail"]["price_micro"] > 0
    assert steps["reservation_resold"]["detail"]["price_micro"] > 0
    assert (await LedgerService(db).invariant())["ok"] is True


async def test_s4_settlement_payout(db, seeded, patch_worker):
    job = {"type": "image_resize", "size": 640 * 480, "params": {}, "deadline_s": 30}
    await trades_service.run_trade(db, "agt_atlas", job, seller_id="agt_cirrus")
    run = await scenarios.run_scenario(db, "S4", actor="judge")
    assert run["state"] == "COMPLETED", run
    steps = {step["step"]: step for step in run["steps"]}
    assert steps["batch_submitted"]["detail"]["state"] in {"SUCCEEDED", "PARTIAL"}
    assert steps["payouts"]["detail"]["succeeded"] >= 1


async def test_s2_failure_recovery(db, seeded, monkeypatch):
    cirrus = await db.agents.find_one({"id": "agt_cirrus"})
    failing = cirrus["profile"]["worker_url"]
    good = fake_dispatch()

    async def flaky(db_, worker_url, job):
        if worker_url == failing:
            from app.services.worker_client import WorkerError

            raise WorkerError("chaos", "worker_unavailable")
        return await good(db_, worker_url, job)

    async def no_worker(url, fail, db=None):
        return {"url": url, "ok": True, "fail": fail}

    monkeypatch.setattr(trades_service, "dispatch_job", flaky)
    monkeypatch.setattr(scenarios.worker_client, "set_chaos", no_worker)

    run = await scenarios.run_scenario(db, "S2", actor="judge")
    assert run["state"] == "COMPLETED", run
    steps = {step["step"]: step for step in run["steps"]}
    assert steps["failure_detected"]["detail"]["state"] == "SETTLED"
    assert steps["failure_detected"]["detail"]["rerouted_from"]
    assert steps["credit_line"]["detail"].get("loan_id")
    assert (await LedgerService(db).invariant())["ok"] is True


async def test_scenario_api_meters_judges(seeded, client, judge_token, monkeypatch):
    monkeypatch.setattr(trades_service, "dispatch_job", fake_dispatch())
    headers = {"Authorization": f"Bearer {judge_token}"}
    quotas = await client.get("/api/v1/session/me", headers=headers)
    left = quotas.json()["quotas"]["scenarios_left"]

    response = await client.post("/api/v1/scenarios/S1/run", headers=headers, json={})
    assert response.status_code == 201, response.text
    assert response.json()["state"] == "COMPLETED"

    after = await client.get("/api/v1/session/me", headers=headers)
    assert after.json()["quotas"]["scenarios_left"] == left - 1


async def test_scenario_api_rejects_unknown(seeded, client, auth):
    response = await client.post("/api/v1/scenarios/S9/run", headers=auth, json={})
    assert response.status_code == 404


async def test_kill_switch_endpoint_blocks_trades(seeded, client, auth, db):
    response = await client.post("/api/v1/control/kill-switch", headers=auth,
                                 json={"active": True, "reason": "drill"})
    assert response.status_code == 200
    assert response.json()["active"] is True
    trade = await client.post("/api/v1/trades", headers=auth,
                              json={"buyer_id": "agt_atlas",
                                    "job": {"type": "image_resize", "size": 100, "params": {}}})
    assert trade.status_code == 400
    assert "kill_switch" in trade.text
