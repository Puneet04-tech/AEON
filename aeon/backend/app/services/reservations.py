"""Forward capacity reservations priced from the weather forecast (F8).

A consumer agent books CPU-seconds ahead of time at the forecast price, funded
from its available balance, and can resell the reservation to another agent.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import structlog

from app.ledger.service import AGENT_AVAILABLE, LedgerService, LedgerError
from app.services import audit, events
from app.services.forecasts import energy_factor_now
from app.services.pricing import reference_price_micro

logger = structlog.get_logger()


def new_reservation_id() -> str:
    return f"rsv_{uuid.uuid4().hex[:20]}"


async def price_reservation(db, provider: dict, cpu_seconds: int) -> int:
    energy = await energy_factor_now(db)
    profile = {**(provider.get("profile") or {}),
               "region_label": provider.get("region_label", "Region A (simulated)")}
    # Reuse the deterministic reference model with a synthetic job size.
    size = max(1, int(cpu_seconds * 1_250_000))  # inverse of the image_resize estimate
    return reference_price_micro(profile, "image_resize", size, energy, 1)


async def create_reservation(db, buyer_id: str, provider_id: str, cpu_seconds: int,
                             region_label: Optional[str] = None) -> dict:
    buyer = await db.agents.find_one({"id": buyer_id})
    provider = await db.agents.find_one({"id": provider_id})
    if not buyer or not provider:
        raise ValueError("agent_not_found")
    if buyer_id == provider_id:
        raise ValueError("cannot_reserve_from_self")

    price = await price_reservation(db, provider, cpu_seconds)
    ledger = LedgerService(db)
    available = await ledger.balance(buyer_id, AGENT_AVAILABLE)
    if available < price:
        raise ValueError("insufficient_available_balance")

    reservation_id = new_reservation_id()
    try:
        await ledger.escrow(reservation_id, buyer_id, price)
    except LedgerError as exc:
        raise ValueError(str(exc))

    now = datetime.now(timezone.utc)
    doc = {
        "id": reservation_id,
        "buyer_id": buyer_id,
        "provider_id": provider_id,
        "region_label": region_label or provider.get("region_label", "Region A (simulated)"),
        "cpu_s": int(cpu_seconds),
        "price_micro": price,
        "forecast_ref": "forecast:current",
        "state": "RESERVED",
        "resale": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.reservations.insert_one({**doc})
    await events.emit(db, "reservation.created", {"reservation_id": reservation_id,
                                                  "buyer_id": buyer_id, "provider_id": provider_id,
                                                  "cpu_s": cpu_seconds, "price_micro": price},
                      actor=buyer_id)
    await audit.record(db, actor_type="agent", actor_id=buyer_id, action="reservation.created",
                       subject_type="reservation", subject_id=reservation_id,
                       after={"price_micro": price, "cpu_s": cpu_seconds})
    return doc


async def resell(db, reservation_id: str, new_buyer_id: str, ask_micro: Optional[int] = None) -> dict:
    reservation = await db.reservations.find_one({"id": reservation_id})
    if not reservation:
        raise ValueError("reservation_not_found")
    if reservation["state"] != "RESERVED":
        raise ValueError(f"reservation_is_{reservation['state'].lower()}")
    new_buyer = await db.agents.find_one({"id": new_buyer_id})
    if not new_buyer:
        raise ValueError("buyer_not_found")

    ask = int(ask_micro or int(reservation["price_micro"]) * 11 // 10)
    ledger = LedgerService(db)
    if await ledger.balance(new_buyer_id, AGENT_AVAILABLE) < ask:
        raise ValueError("insufficient_available_balance")
    try:
        await ledger.escrow(reservation_id + ":resale", new_buyer_id, ask)
    except LedgerError as exc:
        raise ValueError(str(exc))

    original_buyer = reservation["buyer_id"]
    paid = min(ask, int(reservation["price_micro"]))
    await ledger.release(reservation_id + ":resale", new_buyer_id, original_buyer, paid)
    remainder = ask - paid
    if remainder > 0:
        await ledger.refund(reservation_id + ":resale", new_buyer_id, remainder, reason="resale premium")

    await db.reservations.update_one(
        {"id": reservation_id},
        {"$set": {"state": "RESOLD", "resale": {"price_micro": ask, "buyer_id": new_buyer_id,
                                                "at": datetime.now(timezone.utc)},
                  "updated_at": datetime.now(timezone.utc)}},
    )
    await events.emit(db, "reservation.resold", {"reservation_id": reservation_id,
                                                 "from": original_buyer, "to": new_buyer_id,
                                                 "price_micro": ask}, actor=original_buyer)
    return await db.reservations.find_one({"id": reservation_id}, {"_id": 0})


async def release(db, reservation_id: str, actor: str = "operator") -> dict:
    reservation = await db.reservations.find_one({"id": reservation_id})
    if not reservation:
        raise ValueError("reservation_not_found")
    if reservation["state"] != "RESERVED":
        raise ValueError(f"reservation_is_{reservation['state'].lower()}")
    ledger = LedgerService(db)
    await ledger.refund(reservation_id, reservation["buyer_id"], int(reservation["price_micro"]),
                        reason="reservation released")
    await db.reservations.update_one(
        {"id": reservation_id},
        {"$set": {"state": "CANCELLED", "updated_at": datetime.now(timezone.utc)}},
    )
    await audit.record(db, actor_type="operator", actor_id=actor, action="reservation.cancelled",
                       subject_type="reservation", subject_id=reservation_id)
    return await db.reservations.find_one({"id": reservation_id}, {"_id": 0})


async def list_reservations(db, limit: int = 50) -> List[dict]:
    cursor = db.reservations.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return [doc async for doc in cursor]
