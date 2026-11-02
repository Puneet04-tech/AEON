"""Demo seed: six agents, policies, bonds and opening balances.

Openal balances are booked against `treasury_float`, i.e. a simulated
pre-funded treasury. They are clearly demo data, not real money.
"""
from datetime import datetime, timezone
from typing import List

import structlog

from app.ledger.service import AGENT_AVAILABLE, AGENT_BOND, LedgerService
from app.settings import settings

logger = structlog.get_logger()

OPENING_FLOAT_MICRO = 500_000_000  # 500 USD of simulated treasury float
AGENTS: List[dict] = [
    {
        "id": "agt_atlas", "name": "Atlas", "role": "consumer", "status": "ACTIVE",
        "region_label": "Region A (simulated)", "paypal_email": "atlas-buyer@example.com",
        "profile": {"capacity_cpu_s_per_min": 600, "base_cost_micro": 250000,
                    "worker_url": ""},
        "policy": {"per_trade_cap_micro": 5_000_000, "daily_cap_micro": 40_000_000,
                   "price_band_bps": 2500, "allowlist": [], "approval_threshold_micro": 25_000_000,
                   "velocity_per_min": 12},
        "bond_micro": 5_000_000, "balance_micro": 25_000_000,
        "risk": {"uptime_30d": 1.0, "late_count": 0},
    },
    {
        "id": "agt_boreal", "name": "Boreal", "role": "consumer", "status": "ACTIVE",
        "region_label": "Region B (simulated)", "paypal_email": "boreal-buyer@example.com",
        "profile": {"capacity_cpu_s_per_min": 900, "base_cost_micro": 250000,
                    "worker_url": ""},
        "policy": {"per_trade_cap_micro": 3_000_000, "daily_cap_micro": 15_000_000,
                   "price_band_bps": 2000, "allowlist": [], "approval_threshold_micro": 25_000_000,
                   "velocity_per_min": 8},
        "bond_micro": 0, "balance_micro": 12_000_000,
        "risk": {"uptime_30d": 1.0, "late_count": 0},
    },
    {
        "id": "agt_cirrus", "name": "Cirrus", "role": "provider", "status": "ACTIVE",
        "region_label": "Region A (simulated)", "paypal_email": "sb-wl43b753640533@personal.example.com",
        "profile": {"capacity_cpu_s_per_min": 1800, "base_cost_micro": 220000,
                    "worker_url": settings.worker_urls[0] if settings.worker_urls else "http://localhost:8001"},
        "policy": {"cash_out": True, "per_trade_cap_micro": 5_000_000, "daily_cap_micro": 40_000_000,
                   "price_band_bps": 2500, "allowlist": [], "approval_threshold_micro": 25_000_000,
                   "velocity_per_min": 30},
        "bond_micro": 8_000_000, "balance_micro": 0,
        "risk": {"uptime_30d": 0.99, "late_count": 0},
    },
    {
        "id": "agt_dunlin", "name": "Dunlin", "role": "provider", "status": "ACTIVE",
        "region_label": "Region B (simulated)", "paypal_email": "sb-thdmb53676380@personal.example.com",
        "profile": {"capacity_cpu_s_per_min": 1200, "base_cost_micro": 190000,
                    "worker_url": settings.worker_urls[1] if len(settings.worker_urls) > 1 else "http://localhost:8002"},
        "policy": {"cash_out": True, "per_trade_cap_micro": 5_000_000, "daily_cap_micro": 30_000_000,
                   "price_band_bps": 2500, "allowlist": [], "approval_threshold_micro": 25_000_000,
                   "velocity_per_min": 30},
        "bond_micro": 6_000_000, "balance_micro": 0,
        "risk": {"uptime_30d": 0.97, "late_count": 0},
    },
    {
        "id": "agt_ember", "name": "Ember", "role": "lender", "status": "ACTIVE",
        "region_label": "Region A (simulated)", "paypal_email": "ember-lender@example.com",
        "profile": {"capacity_cpu_s_per_min": 0, "base_cost_micro": 250000, "worker_url": ""},
        "policy": {"per_trade_cap_micro": 0, "daily_cap_micro": 0, "price_band_bps": 2500,
                   "allowlist": [], "approval_threshold_micro": 25_000_000, "velocity_per_min": 0,
                   "max_principal_micro": 20_000_000, "base_rate_bps": 800},
        "bond_micro": 0, "balance_micro": 60_000_000,
        "risk": {"uptime_30d": 1.0, "late_count": 0},
    },
]


async def seed(db, reset: bool = False) -> dict:
    ledger = LedgerService(db)
    if reset:
        for collection in ("agents", "trades", "jobs", "negotiations", "journal", "ledger_entries",
                           "ledger_txns", "wallets", "account_totals", "funding_requests",
                           "settlements", "payout_items", "approvals", "loans", "reservations",
                           "scenario_runs", "events", "webhook_events", "audit_log",
                           "idempotency_keys", "forecasts", "kv"):
            await db[collection].delete_many({})

    # Opening balances are booked against treasury_float, which therefore carries
    # a negative balance: it is the counter-account for simulated money entering
    # AEON. No separate opening post is needed.
    created = 0
    now = datetime.now(timezone.utc)
    all_ids = [a["id"] for a in AGENTS]
    for spec in AGENTS:
        doc = {
            **{k: v for k, v in spec.items() if k not in {"balance_micro", "bond_micro"}},
            "owner": "demo-operator",
            "paypal_email": spec["paypal_email"],
            "policy": {**spec["policy"],
                       "allowlist": [a for a in all_ids if a != spec["id"]]},
            "created_at": now,
            "updated_at": now,
        }
        await db.agents.update_one({"id": spec["id"]}, {"$set": doc}, upsert=True)
        created += 1
        await ledger.wallet(spec["id"])

        opening = int(spec["balance_micro"]) + int(spec["bond_micro"])
        if opening:
            await ledger.post(
                [{"account": "treasury_float", "amount_micro": -opening},
                 {"account": AGENT_AVAILABLE, "agent_id": spec["id"], "amount_micro": opening}],
                txn_kind="seed", ref_type="seed", ref_id=f"opening:{spec['id']}",
                idem_key=f"seed:opening:{spec['id']}", memo="Simulated opening balance",
            )
        if spec["bond_micro"]:
            bond = int(spec["bond_micro"])
            await ledger.post(
                [{"account": AGENT_AVAILABLE, "agent_id": spec["id"], "amount_micro": -bond},
                 {"account": AGENT_BOND, "agent_id": spec["id"], "amount_micro": bond}],
                txn_kind="seed", ref_type="seed", ref_id=f"bond:{spec['id']}",
                idem_key=f"seed:bond:{spec['id']}", memo="Performance bond",
            )

    await db.kv.update_one({"key": "seed:opening"}, {"$set": {"value": now.isoformat()}}, upsert=True)
    logger.info("seed_complete", agents=created)
    return {"agents": created, "ids": [a["id"] for a in AGENTS]}


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    from app.db.client import connect_to_mongo, get_database

    async def main() -> None:
        await connect_to_mongo()
        await seed(get_database())

    asyncio.run(main())
