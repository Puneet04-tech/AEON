"""Trade lifecycle: negotiate, escrow, dispatch, verify, book, penalise, reroute.

States
  NEGOTIATING -> AGREED -> ESCROWED -> DISPATCHED -> DELIVERED -> VERIFIED -> SETTLED
Failure paths
  NEGOTIATION_FAILED, REJECTED_BY_GUARDRAIL, FAILED (refunded + penalised),
  REROUTED (a replacement trade continues under links.rerouted_to)
"""
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import structlog

from app.agents.negotiation import Negotiator, reference_quote
from app.db.validators import ACCOUNTS  # noqa: F401  (keeps schema import local)
from app.guardrails import policy
from app.ledger.service import AGENT_BOND, LedgerService, LedgerError
from app.services import audit, events
from app.services.pricing import energy_factor, estimate_cpu_seconds
from app.services.worker_client import WorkerError, canonical_digest, dispatch_job
from app.services.trust import build_evidence, verify_evidence, refresh_provider_reputation, selection_explanation
from app.settings import settings

logger = structlog.get_logger()

MAX_ATTEMPTS = 2
PENALTY_BPS = 1000  # 10% of trade value from the provider's bond
PLATFORM_FEE_BPS = 50  # 0.5%


def new_trade_id() -> str:
    return f"trd_{uuid.uuid4().hex[:20]}"


async def _emit(db, trade: dict, event_type: str, payload: Optional[dict] = None) -> None:
    await events.emit(db, event_type, {
        "trade_id": trade["id"],
        "state": trade["state"],
        "buyer_id": trade["buyer_id"],
        "seller_id": trade["seller_id"],
        **(payload or {}),
    }, trade_id=trade["id"])


async def _transition(db, trade: dict, state: str, **fields) -> dict:
    trade["state"] = state
    update = {"state": state, "updated_at": datetime.now(timezone.utc), **fields}
    await db.trades.update_one({"id": trade["id"]}, {"$set": update, "$inc": {"version": 1}})
    trade.update(fields)
    await _emit(db, trade, f"trade.{state.lower()}")
    return trade


async def select_provider(db, buyer_id: str, job: dict, exclude: Optional[List[str]] = None,
                          energy: float = 1.0) -> Optional[dict]:
    excluded = set(exclude or [])
    best = None
    cursor = db.agents.find({"role": "provider", "status": "ACTIVE"})
    async for agent in cursor:
        if agent["id"] == buyer_id or agent["id"] in excluded:
            continue
        if not (agent.get("profile") or {}).get("worker_url"):
            continue
        quote = reference_quote(agent, job, energy)
        score = quote["reference_price_micro"] / max(0.1, float((agent.get("risk") or {}).get("uptime_30d", 1.0)))
        candidate = (score, quote["reference_price_micro"], agent)
        if best is None or candidate[0] < best[0]:
            best = candidate
    return best[2] if best else None


async def _job_deadline(seconds: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


async def run_trade(db, buyer_id: str, job: dict, seller_id: Optional[str] = None,
                    quantity: int = 1, has_approval: bool = False, actor: str = "operator",
                    allow_reroute: bool = True, energy: float = 1.0,
                    idempotency_key: str = "") -> dict:
    ledger = LedgerService(db)
    buyer = await db.agents.find_one({"id": buyer_id})
    if not buyer:
        raise ValueError("buyer_not_found")
    if buyer.get("status") != "ACTIVE":
        raise ValueError("buyer_not_active")

    if await policy.kill_switch_active(db):
        raise ValueError("kill_switch_active")

    attempts: List[str] = []
    excluded: List[str] = []
    trade = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        seller = None
        if seller_id and attempt == 1:
            seller = await db.agents.find_one({"id": seller_id})
        if seller is None:
            seller = await select_provider(db, buyer_id, job, excluded, energy)
        if seller is None:
            if trade is None:
                raise ValueError("no_provider_available")
            await _transition(db, trade, "FAILED", failure={"code": "no_provider_available",
                                                            "message": "no healthy provider left to reroute to"})
            break

        excluded.append(seller["id"])
        quote = reference_quote(seller, job, energy, quantity)
        reference = quote["reference_price_micro"]

        trade = await _create_trade(db, buyer, seller, job, quantity, reference, attempt, trade)
        explanation = await selection_explanation(db, seller, reference)
        await db.trades.update_one({"id": trade["id"]}, {"$set": {"selection": explanation}})
        trade["selection"] = explanation
        attempts.append(trade["id"])
        await _emit(db, trade, "trade.created", {"reference_micro": reference, "attempt": attempt})

        negotiation = await Negotiator(db).run(trade["id"], buyer, seller, job, reference, quantity)
        price = negotiation["agreed_price_micro"]
        await db.trades.update_one(
            {"id": trade["id"]},
            {"$set": {"negotiation": {
                "rounds": negotiation["rounds"],
                "agreed_price_micro": price,
                "reference_micro": reference,
                "transcript": negotiation["transcript"],
            }}},
        )
        trade["negotiation"] = {"rounds": negotiation["rounds"], "agreed_price_micro": price}

        if price is None:
            await _transition(db, trade, "NEGOTIATION_FAILED",
                              failure={"code": "no_agreement", "message": "no price agreed in 3 rounds"})
            return await _finish(db, trade)

        decision = await policy.check_trade(db, buyer, seller, price, quantity, reference, has_approval)
        await db.trades.update_one({"id": trade["id"]}, {"$set": {"guardrail": decision.to_dict()}})
        trade["guardrail"] = decision.to_dict()
        if not decision.passed:
            await _transition(db, trade, "REJECTED_BY_GUARDRAIL",
                              failure={"code": "guardrail", "message": ", ".join(decision.failed)})
            await audit.record(db, actor_type="agent", actor_id=buyer_id, action="trade.rejected",
                               subject_type="trade", subject_id=trade["id"],
                               detail={"failed": decision.failed})
            return await _finish(db, trade)

        agreed = {"price_micro": price, "quantity": quantity}
        await db.trades.update_one({"id": trade["id"]}, {"$set": {"agreed": agreed}})
        trade["agreed"] = agreed
        await _transition(db, trade, "AGREED")

        try:
            await ledger.escrow(trade["id"], buyer_id, price)
        except LedgerError as exc:
            await _transition(db, trade, "REJECTED_BY_GUARDRAIL",
                              failure={"code": "insufficient_funds", "message": str(exc)})
            return await _finish(db, trade)
        trade["escrow_micro"] = price
        await _transition(db, trade, "ESCROWED", escrow_micro=price)
        await audit.record(db, actor_type="agent", actor_id=buyer_id, action="trade.escrowed",
                           subject_type="trade", subject_id=trade["id"],
                           detail={"price_micro": price})

        deadline = await _job_deadline(int(job.get("deadline_s", 30)))
        await db.trades.update_one({"id": trade["id"]},
                                   {"$set": {"sla": {"deadline": deadline, "breached": False}}})

        dispatch = {
            "job_id": trade["job_id"],
            "trade_id": trade["id"],
            "type": job["type"],
            "size": int(job["size"]),
            "params": job.get("params", {}),
            "deadline_s": int(job.get("deadline_s", 30)),
        }
        await _transition(db, trade, "DISPATCHED")
        started = time.perf_counter()
        try:
            envelope = await dispatch_job(db, seller["profile"]["worker_url"], dispatch)
        except WorkerError as exc:
            await _handle_failure(db, trade, buyer, seller, price, exc.code, str(exc))
            if allow_reroute and attempt < MAX_ATTEMPTS:
                await db.trades.update_one({"id": trade["id"]},
                                           {"$set": {"links.rerouted_to": None}})
                continue
            return await _finish(db, trade)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        result = envelope.get("result") or {}
        cpu_seconds = float(envelope.get("cpu_seconds", 0.0))
        checksum = envelope.get("checksum")
        evidence = build_evidence(trade, dispatch, envelope, elapsed_ms)
        await db.execution_evidence.replace_one({"trade_id": trade["id"]}, evidence, upsert=True)
        await _transition(db, trade, "DELIVERED", metering={
            "cpu_s": cpu_seconds,
            "checksum": checksum,
            "worker_id": envelope.get("worker_id", ""),
            "wall_ms": elapsed_ms,
        })
        await db.jobs.update_one({"job_id": trade["job_id"]},
                                 {"$set": {"state": "DELIVERED", "finished_at": datetime.now(timezone.utc),
                                           "cpu_seconds": cpu_seconds, "checksum": checksum}},
                                 upsert=True)

        # Consumer-side verification: recompute the digest from the returned payload.
        verification = verify_evidence(evidence, result)
        verifier_url = next(
            (url for url in settings.worker_urls if url != seller["profile"].get("worker_url")),
            None,
        )
        if verifier_url:
            try:
                verifier_envelope = await dispatch_job(db, verifier_url, dispatch)
                independent_passed = verifier_envelope.get("checksum") == checksum
                verification["level"] = "independent_deterministic"
                verification["checks"].append({
                    "name": "independent_worker_agreement",
                    "passed": independent_passed,
                    "worker_id": verifier_envelope.get("worker_id", ""),
                })
                verification["passed"] = verification["passed"] and independent_passed
            except WorkerError as exc:
                verification["checks"].append({
                    "name": "independent_worker_agreement",
                    "passed": None,
                    "error": exc.code,
                })
                verification["level"] = "signed_execution"
        await db.verifications.insert_one({**verification, "trade_id": trade["id"]})
        await db.trades.update_one({"id": trade["id"]}, {"$set": {"evidence_id": evidence["id"],
                                                                  "verification": verification}})
        trade["verification"] = verification
        if not verification["passed"]:
            await _handle_failure(db, trade, buyer, seller, price, "verification_failed",
                                  "result checksum did not verify")
            if allow_reroute and attempt < MAX_ATTEMPTS:
                continue
            return await _finish(db, trade)
        trade["metering"] = {"cpu_s": cpu_seconds, "checksum": checksum}
        await _transition(db, trade, "VERIFIED", metering={
            "cpu_s": cpu_seconds, "checksum": checksum,
            "worker_id": envelope.get("worker_id", ""), "wall_ms": elapsed_ms,
        })

        breached = datetime.now(timezone.utc) > deadline
        fee = max(1, price * PLATFORM_FEE_BPS // 10000)
        await ledger.release(trade["id"], buyer_id, seller["id"], price)
        try:
            await ledger.charge_fee("trade", trade["id"], seller["id"], fee)
        except LedgerError as exc:  # fee is best-effort, never blocks settlement
            logger.warning("fee_charge_skipped", trade_id=trade["id"], error=str(exc))

        penalty = 0
        if breached:
            bond = await ledger.balance(seller["id"], AGENT_BOND)
            penalty = min(bond, max(1, price * PENALTY_BPS // 10000))
            if penalty > 0:
                await ledger.penalty(trade["id"], seller["id"], buyer_id, penalty)

        await _transition(db, trade, "SETTLED", sla={"deadline": deadline, "breached": breached},
                          links={"rerouted_from": (trade.get("links") or {}).get("rerouted_from"),
                                 "rerouted_to": None}, settlement={
                              "price_micro": price, "fee_micro": fee, "penalty_micro": penalty})
        await _update_risk(db, seller["id"], breached)
        await refresh_provider_reputation(db, seller["id"])
        await audit.record(db, actor_type="agent", actor_id=seller["id"], action="trade.settled",
                           subject_type="trade", subject_id=trade["id"],
                           detail={"price_micro": price, "fee_micro": fee, "penalty_micro": penalty,
                                   "breached": breached})
        return await _finish(db, trade)

    return await _finish(db, trade)


async def _create_trade(db, buyer: dict, seller: dict, job: dict, quantity: int,
                        reference: int, attempt: int, previous: Optional[dict]) -> dict:
    trade_id = new_trade_id()
    job_id = f"job_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc)
    trade = {
        "id": trade_id,
        "job_id": job_id,
        "buyer_id": buyer["id"],
        "seller_id": seller["id"],
        "state": "NEGOTIATING",
        "version": 0,
        "job": {"type": job["type"], "size": int(job["size"]),
                "params_hash": canonical_digest(job.get("params", {}))[:32],
                "quantity": quantity},
        "agreed": {"price_micro": 0, "quantity": quantity},
        "reference_micro": reference,
        "escrow_micro": 0,
        "attempt": attempt,
        "links": {"rerouted_from": previous["id"] if previous else None, "rerouted_to": None},
        "created_at": now,
        "updated_at": now,
    }
    await db.trades.insert_one({**trade})
    await db.jobs.insert_one({
        "id": job_id, "job_id": job_id, "trade_id": trade_id,
        "worker_id": seller["id"], "state": "QUEUED",
        "created_at": now, "request_hash": trade["job"]["params_hash"],
    })
    if previous:
        await db.trades.update_one({"id": previous["id"]},
                                   {"$set": {"links.rerouted_to": trade_id}})
    return trade


async def _handle_failure(db, trade: dict, buyer: dict, seller: dict, price: int,
                          code: str, message: str) -> None:
    ledger = LedgerService(db)
    await _transition(db, trade, "FAILED", failure={"code": code, "message": message[:300]})
    try:
        await ledger.refund(trade["id"], buyer["id"], price, reason=f"worker failure: {code}")
    except LedgerError as exc:
        logger.error("refund_failed", trade_id=trade["id"], error=str(exc))
    bond = await ledger.balance(seller["id"], AGENT_BOND)
    penalty = min(bond, max(1, price * PENALTY_BPS // 10000))
    if penalty > 0:
        try:
            await ledger.penalty(trade["id"], seller["id"], buyer["id"], penalty)
        except LedgerError as exc:
            logger.error("penalty_failed", trade_id=trade["id"], error=str(exc))
    await _update_risk(db, seller["id"], True, late=True)
    await audit.record(db, actor_type="system", actor_id="trade_runner", action="trade.failed",
                       subject_type="trade", subject_id=trade["id"], severity="warning",
                       detail={"code": code, "message": message[:300], "penalty_micro": penalty})


async def _update_risk(db, seller_id: str, breached: bool, late: bool = False) -> None:
    agent = await db.agents.find_one({"id": seller_id})
    if not agent:
        return
    risk = agent.get("risk") or {"uptime_30d": 1.0, "late_count": 0}
    late_count = int(risk.get("late_count", 0)) + (1 if (breached or late) else 0)
    uptime = max(0.5, float(risk.get("uptime_30d", 1.0)) - (0.02 if (breached or late) else 0))
    status = agent.get("status", "ACTIVE")
    if late_count >= 3 and status == "ACTIVE":
        status = "PAUSED"  # bond suspension after repeated SLA failures
    await db.agents.update_one({"id": seller_id},
                               {"$set": {"risk": {"uptime_30d": round(uptime, 3), "late_count": late_count},
                                         "status": status,
                                         "updated_at": datetime.now(timezone.utc)}})


async def _finish(db, trade: dict) -> dict:
    doc = await db.trades.find_one({"id": trade["id"]}, {"_id": 0})
    await _emit(db, doc, "trade.finished", {"agreed_price_micro": (doc.get("agreed") or {}).get("price_micro", 0)})
    return doc


async def list_trades(db, limit: int = 50, state: Optional[str] = None,
                      buyer_id: Optional[str] = None, seller_id: Optional[str] = None) -> List[dict]:
    query: dict = {}
    if state:
        query["state"] = state
    if buyer_id:
        query["buyer_id"] = buyer_id
    if seller_id:
        query["seller_id"] = seller_id
    cursor = db.trades.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    return [doc async for doc in cursor]


async def get_trade(db, trade_id: str) -> Optional[dict]:
    return await db.trades.find_one({"id": trade_id}, {"_id": 0})


async def negotiation_transcript(db, trade_id: str) -> List[dict]:
    cursor = db.negotiations.find({"trade_id": trade_id}, {"_id": 0}).sort([("round", 1), ("created_at", 1)])
    return [doc async for doc in cursor]
