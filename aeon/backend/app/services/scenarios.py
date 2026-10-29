"""Guided demo scenarios (S1-S4).

Each run is recorded in `scenario_runs` with its steps so the dashboard can show
exactly what happened, and so a judge can replay a run.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import structlog

from app.ledger.service import LedgerService
from app.services import audit, events, forecasts, reservations, settlement, trades, worker_client

logger = structlog.get_logger()

SCENARIOS = {
    "S1": "Happy path: negotiate, run a real job, book it, settle the ledger",
    "S2": "Worker failure: detect, reroute, penalise the bond, credit line, repay",
    "S3": "Forecast reservation: weather-priced forward capacity, then resale",
    "S4": "Settlement: net balances and pay net-positive agents with one PayPal batch",
}

DEFAULT_JOB = {"type": "image_resize", "size": 640 * 480, "params": {"width": 320, "height": 240},
               "deadline_s": 30}


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:20]}"


class Run:
    def __init__(self, db, scenario: str, actor: str):
        self.db = db
        self.scenario = scenario
        self.actor = actor
        self.run_id = new_run_id()
        self.steps: List[dict] = []

    async def step(self, name: str, detail: Optional[dict] = None, state: str = "OK") -> None:
        entry = {"step": name, "state": state, "detail": detail or {},
                 "at": datetime.now(timezone.utc).isoformat()}
        self.steps.append(entry)
        await events.emit(self.db, "scenario.step", {"run_id": self.run_id,
                                                     "scenario": self.scenario, **entry},
                          actor=self.actor)

    async def finish(self, state: str, error: str = "") -> dict:
        doc = {
            "id": self.run_id,
            "run_id": self.run_id,
            "scenario": self.scenario,
            "actor": self.actor,
            "state": state,
            "steps": self.steps,
            "error": error[:500],
            "started_at": self.steps[0]["at"] if self.steps else datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.scenario_runs.update_one({"run_id": self.run_id}, {"$set": doc}, upsert=True)
        await events.emit(self.db, "scenario.finished", {"run_id": self.run_id,
                                                         "scenario": self.scenario,
                                                         "state": state}, actor=self.actor)
        return doc


async def _demo_agents(db) -> Dict[str, dict]:
    agents = {}
    async for agent in db.agents.find({"status": {"$in": ["ACTIVE", "PAUSED"]}}):
        agents.setdefault(agent["name"].split(" ")[0].upper() if agent.get("name") else agent["id"], agent)
    return agents


async def _agents_by_role(db, role: str) -> List[dict]:
    return [agent async for agent in db.agents.find({"role": role, "status": "ACTIVE"})]


async def _pick_pair(db) -> tuple[dict, dict]:
    consumers = await _agents_by_role(db, "consumer")
    providers = await _agents_by_role(db, "provider")
    if not consumers or not providers:
        raise ValueError("seed_data_missing")
    return consumers[0], providers[0]


async def run_scenario(db, name: str, actor: str = "judge", job: Optional[dict] = None) -> dict:
    name = name.upper()
    if name not in SCENARIOS:
        raise ValueError("unknown_scenario")
    run = Run(db, name, actor)
    try:
        if name == "S1":
            await _s1(db, run, job)
        elif name == "S2":
            await _s2(db, run, job)
        elif name == "S3":
            await _s3(db, run)
        else:
            await _s4(db, run)
    except Exception as exc:  # a failed scenario is a recorded result, not a crash
        logger.warning("scenario_failed", scenario=name, error=str(exc))
        await run.step("error", {"message": str(exc)[:300]}, state="ERROR")
        return await run.finish("FAILED", error=str(exc))
    return await run.finish("COMPLETED")


async def _s1(db, run: Run, job: Optional[dict]) -> None:
    buyer, provider = await _pick_pair(db)
    await run.step("agents_selected", {"buyer": buyer["id"], "seller": provider["id"]})
    trade_job = job or DEFAULT_JOB
    energy = await forecasts.energy_factor_now(db)
    trade = await trades.run_trade(db, buyer["id"], trade_job, seller_id=provider["id"],
                                   actor=run.actor, energy=energy)
    await run.step("trade_finished", {
        "trade_id": trade["id"], "state": trade["state"],
        "price_micro": (trade.get("agreed") or {}).get("price_micro"),
        "rounds": (trade.get("negotiation") or {}).get("rounds"),
        "cpu_s": (trade.get("metering") or {}).get("cpu_s"),
        "penalty_micro": (trade.get("settlement") or {}).get("penalty_micro"),
    }, state="OK" if trade["state"] == "SETTLED" else "WARN")
    if trade["state"] != "SETTLED":
        raise ValueError(f"trade ended in {trade['state']}")
    await run.step("ledger_checked", await _invariant_ok(db))


async def _s2(db, run: Run, job: Optional[dict]) -> None:
    buyer, provider = await _pick_pair(db)
    worker_url = (provider.get("profile") or {}).get("worker_url")
    if not worker_url:
        raise ValueError("provider_has_no_worker")

    await run.step("agents_selected", {"buyer": buyer["id"], "provider": provider["id"],
                                       "worker_url": worker_url})
    chaos = await worker_client.set_chaos(worker_url, True, db=db)
    await run.step("chaos_injected", chaos, state="OK" if chaos.get("ok") else "WARN")

    energy = await forecasts.energy_factor_now(db)
    trade = await trades.run_trade(db, buyer["id"], job or DEFAULT_JOB, seller_id=provider["id"],
                                   actor=run.actor, allow_reroute=True, energy=energy)
    links = trade.get("links") or {}
    await run.step("failure_detected", {
        "trade_id": trade["id"], "state": trade["state"],
        "failure": trade.get("failure"),
        "rerouted_from": links.get("rerouted_from"),
        "rerouted_to": links.get("rerouted_to"),
    }, state="OK" if trade["state"] == "SETTLED" else "WARN")

    restored = await worker_client.set_chaos(worker_url, False, db=db)
    await run.step("worker_recovered", restored, state="OK" if restored.get("ok") else "WARN")

    refreshed = await db.agents.find_one({"id": provider["id"]}, {"_id": 0})
    await run.step("bond_status", {
        "status": refreshed.get("status"),
        "risk": refreshed.get("risk"),
        "bond_suspended": refreshed.get("status") != "ACTIVE",
    })

    loan = None
    try:
        from app.services import loans

        loan = await loans.request_credit(db, provider["id"], 5_000_000)
        await run.step("credit_line", {"loan_id": loan["id"], "state": loan["state"],
                                       "rate_bps": loan["rate_bps"],
                                       "approve": loan["state"] in {"ACTIVE", "DISBURSED"}},
                       state="OK" if loan["state"] == "ACTIVE" else "WARN")
    except ValueError as exc:
        await run.step("credit_line", {"error": str(exc)}, state="WARN")

    if trade["state"] == "SETTLED" and loan and loan["state"] == "ACTIVE":
        from app.services import loans as loans_module

        repaid = await loans_module.repay_from_settlement(db, trade["id"])  # noqa: F841
        await run.step("repayment_scheduled", {"note": "repayment is taken from the next successful settlement"},
                       state="OK")
    await run.step("ledger_checked", await _invariant_ok(db))


async def _s3(db, run: Run) -> None:
    buyer, provider = await _pick_pair(db)
    forecast = await forecasts.get_forecast(db)
    await run.step("forecast_loaded", {
        "source": forecast["source"],
        "temp_c": forecast["payload_summary"]["temp_c"],
        "energy_factor": forecast["payload_summary"]["energy_factor"],
        "simulated_pricing": True,
    })
    reservation = await reservations.create_reservation(db, buyer["id"], provider["id"], 30)
    await run.step("reservation_created", {"reservation_id": reservation["id"],
                                           "price_micro": reservation["price_micro"],
                                           "region": reservation["region_label"]})

    ask = int(reservation["price_micro"]) * 105 // 100
    consumers = await _agents_by_role(db, "consumer")
    ledger = LedgerService(db)
    reseller = None
    for candidate in consumers:
        if candidate["id"] == buyer["id"]:
            continue
        if await ledger.balance(candidate["id"]) >= ask:
            reseller = candidate
            break
    if reseller:
        resold = await reservations.resell(db, reservation["id"], reseller["id"], ask)
        await run.step("reservation_resold", {"to": reseller["id"],
                                              "price_micro": resold["resale"]["price_micro"]})
    else:
        await run.step("reservation_resale_skipped", {"ask_micro": ask,
                                                       "reason": "no resale buyer with enough balance"},
                       state="WARN")
    await run.step("ledger_checked", await _invariant_ok(db))


async def _s4(db, run: Run) -> None:
    batch = await settlement.propose_settlement(db, actor=run.actor, has_approval=True)
    await run.step("batch_submitted", {"settlement_id": batch["id"], "state": batch["state"],
                                       "totals": batch.get("totals"),
                                       "paypal_batch_id": batch.get("paypal_batch_id"),
                                       "simulated": batch.get("simulated")})
    if batch["state"] == "AWAITING_APPROVAL":
        raise ValueError("settlement requires operator approval in the dashboard")
    if batch["state"] not in {"SUCCEEDED", "PARTIAL"}:
        raise ValueError(f"settlement ended in {batch['state']}")
    items = await settlement.list_payouts(db, settlement_id=batch["id"])
    await run.step("payouts", {"items": len(items),
                               "succeeded": sum(1 for i in items if i["state"] == "SUCCESS")})
    await run.step("ledger_checked", await _invariant_ok(db))


async def _invariant_ok(db) -> dict:
    from app.ledger.service import LedgerService

    report = await LedgerService(db).invariant()
    return {"ok": report["ok"], "sum_micro": report["sum_micro"],
            "transactions": report["transactions"]}


async def list_runs(db, limit: int = 20) -> List[dict]:
    cursor = db.scenario_runs.find({}, {"_id": 0}).sort("started_at", -1).limit(limit)
    return [doc async for doc in cursor]


async def get_run(db, run_id: str) -> Optional[dict]:
    return await db.scenario_runs.find_one({"run_id": run_id}, {"_id": 0})
