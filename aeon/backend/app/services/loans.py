"""Credit lines between agents (the lender-agent story).

The lender agent proposes terms with the LLM; `rules.loan_terms` and the lender's
policy clamp them; the borrower gets a credit line whose repayment is taken from
its settlement payouts.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import structlog

from app.guardrails.rules import loan_terms
from app.ledger.service import AGENT_AVAILABLE, LedgerService, LedgerError
from app.llm.llm_client import LLMUnavailable, get_llm
from app.services import audit, events

logger = structlog.get_logger()

MAX_PRINCIPAL_MICRO = 20_000_000
MAX_RATE_BPS = 2500
DEFAULT_REPAY_SHARE_BPS = 3000
LENDER_SYSTEM = (
    "You are a credit officer agent in a micro-payment clearing house. "
    "Reply with JSON only: {\"approve\": boolean, \"rate_bps\": integer, \"reasoning\": string}. "
    "rate_bps is an annualised basis-point rate between 0 and 2500. "
    "Deny the loan when the borrower's record is weak."
)


def new_loan_id() -> str:
    return f"loan_{uuid.uuid4().hex[:20]}"


async def request_credit(db, borrower_id: str, amount_micro: int,
                         lender_id: Optional[str] = None) -> dict:
    borrower = await db.agents.find_one({"id": borrower_id})
    if not borrower:
        raise ValueError("borrower_not_found")

    if lender_id:
        lender = await db.agents.find_one({"id": lender_id})
    else:
        lender = await _pick_lender(db, borrower_id, amount_micro)
    if not lender:
        raise ValueError("no_lender_available")

    lender_policy = lender.get("policy") or {}
    max_principal = min(int(lender_policy.get("max_principal_micro", MAX_PRINCIPAL_MICRO)), MAX_PRINCIPAL_MICRO)
    target_rate = int(lender_policy.get("base_rate_bps", 800))
    risk = borrower.get("risk") or {}
    late_count = int(risk.get("late_count", 0))
    uptime = float(risk.get("uptime_30d", 1.0))

    llm = get_llm(db)
    user = (
        f"Borrower request: {amount_micro} micro-USD. "
        f"Borrower uptime_30d: {uptime}. Late deliveries: {late_count}. "
        f"Lender balance: {await LedgerService(db).balance(lender['id'], AGENT_AVAILABLE)} micro. "
        f"Base rate: {target_rate} bps. Decide approve/reject and set the rate."
    )
    try:
        result = await llm.complete_json("credit_decision", LENDER_SYSTEM, user)
        data = result["data"]
        approve = bool(data.get("approve"))
        rate_bps = data.get("rate_bps", target_rate)
        reasoning = str(data.get("reasoning", ""))[:300]
        meta = {k: result[k] for k in ("source", "provider", "model", "latency_ms")}
    except LLMUnavailable:
        # Deterministic fallback: price the risk instead of refusing outright.
        approve = late_count < 2 and amount_micro <= max_principal
        rate_bps = target_rate + late_count * 200
        reasoning = "deterministic fallback: approve with a risk premium, refuse after two late deliveries"
        meta = {"source": "fallback", "provider": "none", "model": "none", "latency_ms": 0}

    if not isinstance(rate_bps, int) or isinstance(rate_bps, bool):
        rate_bps = target_rate
    checks = loan_terms(amount_micro, rate_bps, max_principal, MAX_RATE_BPS)
    guard_ok = all(c.passed for c in checks)
    if not guard_ok:
        approve = False

    liquidity = await LedgerService(db).balance(lender["id"], AGENT_AVAILABLE)
    if liquidity < amount_micro:
        approve = False

    loan_id = new_loan_id()
    state = "APPROVED" if approve else "DENIED"
    doc = {
        "id": loan_id,
        "lender_id": lender["id"],
        "borrower_id": borrower_id,
        "principal_micro": amount_micro,
        "rate_bps": max(0, min(rate_bps, MAX_RATE_BPS)),
        "repay_share_bps": DEFAULT_REPAY_SHARE_BPS,
        "outstanding_micro": amount_micro,
        "state": state,
        "decision": {"llm": meta, "reasoning": reasoning,
                     "guardrail": [c.to_dict() for c in checks], "guardrail_passed": guard_ok},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db.loans.insert_one({**doc})
    await events.emit(db, "loan.decision", {"loan_id": loan_id, "borrower_id": borrower_id,
                                            "lender_id": lender["id"], "approve": approve,
                                            "amount_micro": amount_micro, "rate_bps": doc["rate_bps"]},
                       actor=lender["id"])
    await audit.record(db, actor_type="agent", actor_id=lender["id"], action="loan.decision",
                       subject_type="loan", subject_id=loan_id,
                       detail={"approve": approve, "amount_micro": amount_micro,
                               "rate_bps": doc["rate_bps"]})
    if approve:
        await disburse_approved(db, loan_id, actor=lender["id"])
    return await db.loans.find_one({"id": loan_id}, {"_id": 0})


async def _pick_lender(db, borrower_id: str, amount_micro: int) -> Optional[dict]:
    ledger = LedgerService(db)
    best = None
    async for agent in db.agents.find({"role": "lender", "status": "ACTIVE"}):
        if agent["id"] == borrower_id:
            continue
        available = await ledger.balance(agent["id"], AGENT_AVAILABLE)
        if available >= amount_micro and (best is None or available > best[0]):
            best = (available, agent)
    return best[1] if best else None


async def disburse_approved(db, loan_id: str, actor: str = "system") -> dict:
    loan = await db.loans.find_one({"id": loan_id})
    if not loan:
        raise ValueError("loan_not_found")
    if loan["state"] not in {"APPROVED"}:
        if loan["state"] in {"ACTIVE", "DISBURSED"}:
            return loan
        raise ValueError(f"loan_is_{loan['state'].lower()}")
    ledger = LedgerService(db)
    try:
        await ledger.loan_disbursement(loan_id, loan["lender_id"], loan["borrower_id"],
                                       int(loan["principal_micro"]))
    except LedgerError as exc:
        await db.loans.update_one({"id": loan_id},
                                  {"$set": {"state": "FAILED",
                                            "failure": {"code": "insufficient_lender_funds",
                                                        "message": str(exc)}}})
        raise ValueError(str(exc))

    await db.loans.update_one({"id": loan_id},
                              {"$set": {"state": "ACTIVE",
                                        "disbursed_at": datetime.now(timezone.utc),
                                        "updated_at": datetime.now(timezone.utc)}})
    await events.emit(db, "loan.disbursed", {"loan_id": loan_id,
                                             "amount_micro": loan["principal_micro"],
                                             "borrower_id": loan["borrower_id"]}, actor=actor)
    await audit.record(db, actor_type="agent", actor_id=loan["lender_id"], action="loan.disbursed",
                       subject_type="loan", subject_id=loan_id,
                       detail={"amount_micro": loan["principal_micro"]})
    return await db.loans.find_one({"id": loan_id}, {"_id": 0})


async def repay_from_settlement(db, settlement_id: str) -> List[dict]:
    """Take repayments from agents who were just paid out."""
    ledger = LedgerService(db)
    repaid = []
    items = [item async for item in db.payout_items.find({"settlement_id": settlement_id, "state": "SUCCESS"})]
    for item in items:
        borrower_id = item["agent_id"]
        loans = [loan async for loan in db.loans.find({"borrower_id": borrower_id, "state": "ACTIVE"})]
        for loan in loans:
            share = int(item["amount_micro"]) * int(loan.get("repay_share_bps", DEFAULT_REPAY_SHARE_BPS)) // 10000
            due = min(share, int(loan["outstanding_micro"]))
            available = await ledger.balance(borrower_id, AGENT_AVAILABLE)
            amount = min(due, available)
            if amount <= 0:
                continue
            try:
                await ledger.loan_repayment(loan["id"], borrower_id, amount)
            except LedgerError:
                continue
            outstanding = int(loan["outstanding_micro"]) - amount
            await db.loans.update_one(
                {"id": loan["id"]},
                {"$set": {"outstanding_micro": max(0, outstanding),
                          "state": "REPAID" if outstanding <= 0 else "ACTIVE",
                          "updated_at": datetime.now(timezone.utc)}},
            )
            repaid.append({"loan_id": loan["id"], "amount_micro": amount,
                           "outstanding_micro": max(0, outstanding)})
            await events.emit(db, "loan.repaid", {"loan_id": loan["id"],
                                                  "amount_micro": amount}, actor="reconciler")
    return repaid


async def list_loans(db, limit: int = 50) -> List[dict]:
    cursor = db.loans.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return [doc async for doc in cursor]
