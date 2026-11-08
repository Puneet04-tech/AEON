"""Double-entry ledger.

Every posting is a balanced transaction: the signed `amount_micro` of all lines
in a txn sums to zero. Balances are cached in `wallets` (one document per agent)
and system accounts are tracked in `account_totals`. The ledger itself is the
source of truth; `rebuild_wallets` regenerates the caches from it.

Money is integer micro-USD. No floats, ever.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

import structlog
from pymongo.errors import DuplicateKeyError

logger = structlog.get_logger()

CURRENCY = "USD"

TREASURY_FLOAT = "treasury_float"
AGENT_AVAILABLE = "agent_available"
AGENT_ESCROW = "agent_escrow"
AGENT_BOND = "agent_bond"
AGENT_DISPUTE_HOLD = "agent_dispute_hold"
PLATFORM_FEES = "platform_fees"
LOAN_RECEIVABLE = "loan_receivable"
LOAN_PAYABLE = "loan_payable"
PAYOUT_IN_FLIGHT = "payout_in_flight"
DUST = "dust"

ACCOUNTS = {
    TREASURY_FLOAT, AGENT_AVAILABLE, AGENT_ESCROW, AGENT_BOND, PLATFORM_FEES,
    LOAN_RECEIVABLE, LOAN_PAYABLE, PAYOUT_IN_FLIGHT, DUST, AGENT_DISPUTE_HOLD,
}
AGENT_ACCOUNTS = {
    AGENT_AVAILABLE: "available_micro",
    AGENT_ESCROW: "escrow_micro",
    AGENT_BOND: "bond_micro",
    AGENT_DISPUTE_HOLD: "dispute_hold_micro",
}


class LedgerError(Exception):
    """Base class for ledger failures."""


class InsufficientFunds(LedgerError):
    def __init__(self, agent_id: str, account: str, wanted: int, available: int):
        super().__init__(f"{agent_id} {account} has {available} micro, needs {wanted}")
        self.agent_id = agent_id
        self.account = account
        self.wanted = wanted
        self.available = available


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:24]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LedgerService:
    def __init__(self, db):
        self.db = db

    # ---------------------------------------------------------------- wallets
    async def wallet(self, agent_id: str) -> dict:
        doc = await self.db.wallets.find_one({"agent_id": agent_id})
        if doc:
            return doc
        doc = {
            "agent_id": agent_id,
            "available_micro": 0,
            "escrow_micro": 0,
            "bond_micro": 0,
            "dispute_hold_micro": 0,
            "dust_micro": 0,
            "currency": CURRENCY,
            "version": 0,
            "created_at": _now(),
            "updated_at": _now(),
        }
        try:
            await self.db.wallets.insert_one(doc)
        except DuplicateKeyError:  # concurrent creation
            doc = await self.db.wallets.find_one({"agent_id": agent_id}) or doc
        return doc

    async def balance(self, agent_id: str, account: str = AGENT_AVAILABLE) -> int:
        field = AGENT_ACCOUNTS.get(account)
        if not field:
            raise LedgerError(f"no wallet field for account {account}")
        doc = await self.wallet(agent_id)
        return int(doc.get(field, 0))

    async def balances(self, agent_id: str) -> dict:
        doc = await self.wallet(agent_id)
        return {
            "agent_id": agent_id,
            "available_micro": int(doc.get("available_micro", 0)),
            "escrow_micro": int(doc.get("escrow_micro", 0)),
            "bond_micro": int(doc.get("bond_micro", 0)),
            "dispute_hold_micro": int(doc.get("dispute_hold_micro", 0)),
            "total_micro": int(doc.get("available_micro", 0)) + int(doc.get("escrow_micro", 0))
            + int(doc.get("bond_micro", 0)) + int(doc.get("dispute_hold_micro", 0)),
        }

    async def all_balances(self) -> List[dict]:
        cursor = self.db.wallets.find({}, {"_id": 0})
        return [doc async for doc in cursor]

    async def treasury_float_micro(self) -> int:
        """Signed counter-account balance (negative while AEON holds funds)."""
        doc = await self.db.account_totals.find_one({"_id": TREASURY_FLOAT})
        return int(doc["amount_micro"]) if doc else 0

    async def treasury_funds_micro(self) -> int:
        """Money actually available at the treasury, i.e. the float magnitude.

        treasury_float is the counter-account for money entering and leaving
        AEON: it is negative while agents hold balances. Reserve and payout caps
        are checked against its magnitude.
        """
        return -await self.treasury_float_micro()

    # ---------------------------------------------------------------- posting
    async def post(self, lines: List[dict], txn_kind: str, ref_type: str, ref_id: str,
                   idem_key: str, memo: str = "", actor: str = "system") -> dict:
        """Write one balanced transaction. Idempotent on `idem_key`."""
        if len(idem_key) < 8:
            raise LedgerError("idem_key must be at least 8 characters")
        clean = self._validate(lines)
        existing = await self.db.ledger_txns.find_one({"_id": idem_key})
        if existing:
            return {"txn_id": existing["txn_id"], "duplicate": True, "entries": []}

        # Fail before writing anything: a debit that cannot be covered must not
        # leave a transaction behind in the append-only ledger.
        await self._check_funds(clean)

        txn_id = new_id("txn_")
        posted_at = _now()
        entries = []
        for index, line in enumerate(clean):
            entries.append({
                "id": new_id("le_"),
                "txn_id": txn_id,
                "account": line["account"],
                "agent_id": line.get("agent_id"),
                "amount_micro": line["amount_micro"],
                "currency": CURRENCY,
                "ref": {"type": ref_type, "id": ref_id},
                "idem_key": f"{idem_key}:{index}",
                "txn_idem": idem_key,
                "memo": memo[:500],
                "posted_at": posted_at,
            })

        # Cache first, ledger second. If the append fails the cache updates are
        # rolled back, so a wallet can never drift from the append-only ledger.
        applied = await self._apply_to_caches(clean, actor)
        try:
            await self.db.ledger_txns.insert_one({
                "_id": idem_key, "txn_id": txn_id, "kind": txn_kind,
                "ref": {"type": ref_type, "id": ref_id}, "memo": memo[:500],
                "currency": CURRENCY, "amount_micro": sum(l["amount_micro"] for l in clean if l["amount_micro"] > 0),
                "posted_at": posted_at, "actor": actor,
            })
            await self.db.ledger_entries.insert_many(entries, ordered=True)
        except DuplicateKeyError:
            # Another writer owns this idempotency key; undo ours and return theirs.
            await self._rollback_caches(applied)
            await self.db.ledger_entries.delete_many({"txn_id": txn_id})
            dup = await self.db.ledger_txns.find_one({"_id": idem_key})
            return {"txn_id": (dup or {}).get("txn_id", txn_id), "duplicate": True, "entries": []}
        except Exception:
            await self._rollback_caches(applied)
            await self.db.ledger_entries.delete_many({"txn_id": txn_id})
            await self.db.ledger_txns.delete_one({"_id": idem_key, "txn_id": txn_id})
            raise

        logger.info("ledger_posted", txn_id=txn_id, kind=txn_kind, ref=ref_id,
                    amount=sum(l["amount_micro"] for l in clean if l["amount_micro"] > 0))
        return {"txn_id": txn_id, "duplicate": False, "entries": entries}

    def _validate(self, lines: Iterable[dict]) -> List[dict]:
        clean = list(lines)
        if not clean:
            raise LedgerError("transaction needs at least one line")
        total = 0
        for line in clean:
            account = line.get("account")
            if account not in ACCOUNTS:
                raise LedgerError(f"unknown account {account}")
            amount = line.get("amount_micro")
            if isinstance(amount, bool) or not isinstance(amount, int):
                raise LedgerError("amount_micro must be an integer")
            if amount == 0:
                raise LedgerError("zero-amount ledger lines are not allowed")
            if account in AGENT_ACCOUNTS and not line.get("agent_id"):
                raise LedgerError(f"account {account} requires agent_id")
            total += amount
        if total != 0:
            raise LedgerError(f"unbalanced transaction: sum={total}")
        return clean

    async def _check_funds(self, lines: List[dict]) -> None:
        """Raise before any write when a debit cannot be covered."""
        for line in lines:
            account = line["account"]
            amount = line["amount_micro"]
            if account in AGENT_ACCOUNTS and amount < 0:
                field = AGENT_ACCOUNTS[account]
                wallet = await self.wallet(line["agent_id"])
                held = int(wallet.get(field, 0))
                if held < -amount:
                    raise InsufficientFunds(line["agent_id"], account, -amount, held)

    async def _apply_to_caches(self, lines: List[dict], actor: str) -> List[dict]:
        """Apply wallet/account cache updates, rolling back if one of them fails."""
        applied: List[dict] = []
        try:
            for line in lines:
                account = line["account"]
                amount = line["amount_micro"]
                if account in AGENT_ACCOUNTS:
                    field = AGENT_ACCOUNTS[account]
                    agent_id = line["agent_id"]
                    await self.wallet(agent_id)
                    if amount < 0:
                        result = await self.db.wallets.update_one(
                            {"agent_id": agent_id, field: {"$gte": -amount}},
                            {"$inc": {field: amount, "version": 1}, "$set": {"updated_at": _now()}},
                        )
                        if result.modified_count != 1:
                            current = await self.db.wallets.find_one({"agent_id": agent_id}) or {}
                            raise InsufficientFunds(agent_id, account, -amount, int(current.get(field, 0)))
                    else:
                        await self.db.wallets.update_one(
                            {"agent_id": agent_id},
                            {"$inc": {field: amount, "version": 1}, "$set": {"updated_at": _now()}},
                        )
                await self.db.account_totals.update_one(
                    {"_id": account},
                    {"$inc": {"amount_micro": amount}, "$set": {"updated_at": _now()}},
                    upsert=True,
                )
                applied.append(line)
        except Exception:
            await self._rollback_caches(applied)
            raise
        return applied

    async def _rollback_caches(self, applied: List[dict]) -> None:
        """Undo cache changes for a posting that will not be committed."""
        for line in reversed(applied):
            account = line["account"]
            amount = line["amount_micro"]
            if account in AGENT_ACCOUNTS:
                await self.db.wallets.update_one(
                    {"agent_id": line["agent_id"]},
                    {"$inc": {AGENT_ACCOUNTS[account]: -amount, "version": 1},
                     "$set": {"updated_at": _now()}},
                )
            await self.db.account_totals.update_one(
                {"_id": account},
                {"$inc": {"amount_micro": -amount}, "$set": {"updated_at": _now()}},
                upsert=True,
            )

    # ------------------------------------------------------------ operations
    async def fund_agent(self, agent_id: str, amount_micro: int, order_id: str) -> dict:
        return await self.post(
            [
                {"account": TREASURY_FLOAT, "amount_micro": -amount_micro},
                {"account": AGENT_AVAILABLE, "agent_id": agent_id, "amount_micro": amount_micro},
            ],
            txn_kind="funding", ref_type="funding_request", ref_id=order_id,
            idem_key=f"funding:{order_id}:credit", memo=f"PayPal capture for {agent_id}",
        )

    async def escrow(self, trade_id: str, buyer_id: str, amount_micro: int) -> dict:
        return await self.post(
            [
                {"account": AGENT_AVAILABLE, "agent_id": buyer_id, "amount_micro": -amount_micro},
                {"account": AGENT_ESCROW, "agent_id": buyer_id, "amount_micro": amount_micro},
            ],
            txn_kind="escrow", ref_type="trade", ref_id=trade_id,
            idem_key=f"trade:{trade_id}:escrow", memo="Trade escrow hold",
        )

    async def release(self, trade_id: str, buyer_id: str, seller_id: str, amount_micro: int) -> dict:
        return await self.post(
            [
                {"account": AGENT_ESCROW, "agent_id": buyer_id, "amount_micro": -amount_micro},
                {"account": AGENT_AVAILABLE, "agent_id": seller_id, "amount_micro": amount_micro},
            ],
            txn_kind="release", ref_type="trade", ref_id=trade_id,
            idem_key=f"trade:{trade_id}:release", memo="Escrow released to provider",
        )

    async def refund(self, trade_id: str, buyer_id: str, amount_micro: int, reason: str = "") -> dict:
        return await self.post(
            [
                {"account": AGENT_ESCROW, "agent_id": buyer_id, "amount_micro": -amount_micro},
                {"account": AGENT_AVAILABLE, "agent_id": buyer_id, "amount_micro": amount_micro},
            ],
            txn_kind="refund", ref_type="trade", ref_id=trade_id,
            idem_key=f"trade:{trade_id}:refund", memo=reason or "Escrow refunded",
        )

    async def penalty(self, trade_id: str, seller_id: str, buyer_id: str, amount_micro: int) -> dict:
        return await self.post(
            [
                {"account": AGENT_BOND, "agent_id": seller_id, "amount_micro": -amount_micro},
                {"account": AGENT_AVAILABLE, "agent_id": buyer_id, "amount_micro": amount_micro},
            ],
            txn_kind="penalty", ref_type="trade", ref_id=trade_id,
            idem_key=f"trade:{trade_id}:penalty", memo="SLA penalty from provider bond",
        )

    async def hold_dispute(self, trade_id: str, seller_id: str, amount_micro: int) -> dict:
        return await self.post(
            [
                {"account": AGENT_AVAILABLE, "agent_id": seller_id, "amount_micro": -amount_micro},
                {"account": AGENT_DISPUTE_HOLD, "agent_id": seller_id, "amount_micro": amount_micro},
            ],
            txn_kind="dispute_hold", ref_type="trade", ref_id=trade_id,
            idem_key=f"trade:{trade_id}:dispute_hold", memo="Provider funds held during dispute",
        )

    async def resolve_dispute(self, trade_id: str, seller_id: str, buyer_id: str,
                              amount_micro: int, refund: bool) -> dict:
        destination = AGENT_AVAILABLE
        destination_agent = buyer_id if refund else seller_id
        return await self.post(
            [
                {"account": AGENT_DISPUTE_HOLD, "agent_id": seller_id, "amount_micro": -amount_micro},
                {"account": destination, "agent_id": destination_agent, "amount_micro": amount_micro},
            ],
            txn_kind="dispute_refund" if refund else "dispute_release",
            ref_type="trade", ref_id=trade_id,
            idem_key=f"trade:{trade_id}:dispute:{'refund' if refund else 'release'}",
            memo="Dispute refund to buyer" if refund else "Dispute released to provider",
        )

    async def charge_fee(self, ref_type: str, ref_id: str, agent_id: str, amount_micro: int) -> dict:
        return await self.post(
            [
                {"account": AGENT_AVAILABLE, "agent_id": agent_id, "amount_micro": -amount_micro},
                {"account": PLATFORM_FEES, "amount_micro": amount_micro},
            ],
            txn_kind="fee", ref_type=ref_type, ref_id=ref_id,
            idem_key=f"fee:{ref_type}:{ref_id}", memo="Platform fee",
        )

    async def post_bond(self, agent_id: str, amount_micro: int, reason: str, ref_id: str) -> dict:
        return await self.post(
            [
                {"account": AGENT_AVAILABLE, "agent_id": agent_id, "amount_micro": -amount_micro},
                {"account": AGENT_BOND, "agent_id": agent_id, "amount_micro": amount_micro},
            ],
            txn_kind="bond", ref_type="bond", ref_id=ref_id,
            idem_key=f"bond:{ref_id}", memo=reason,
        )

    async def loan_disbursement(self, loan_id: str, lender_id: str, borrower_id: str, amount_micro: int) -> dict:
        return await self.post(
            [
                {"account": LOAN_RECEIVABLE, "amount_micro": -amount_micro},
                {"account": AGENT_AVAILABLE, "agent_id": borrower_id, "amount_micro": amount_micro},
            ],
            txn_kind="loan", ref_type="loan", ref_id=loan_id,
            idem_key=f"loan:{loan_id}:disburse", memo=f"Credit line from {lender_id}",
        )

    async def loan_repayment(self, loan_id: str, borrower_id: str, amount_micro: int) -> dict:
        return await self.post(
            [
                {"account": AGENT_AVAILABLE, "agent_id": borrower_id, "amount_micro": -amount_micro},
                {"account": LOAN_RECEIVABLE, "amount_micro": amount_micro},
            ],
            txn_kind="loan_repayment", ref_type="loan", ref_id=loan_id,
            idem_key=f"loan:{loan_id}:repay", memo="Credit line repayment",
        )

    async def start_payout(self, batch_id: str, agent_id: str, amount_micro: int) -> dict:
        return await self.post(
            [
                {"account": AGENT_AVAILABLE, "agent_id": agent_id, "amount_micro": -amount_micro},
                {"account": PAYOUT_IN_FLIGHT, "amount_micro": amount_micro},
            ],
            txn_kind="payout", ref_type="settlement", ref_id=batch_id,
            idem_key=f"settlement:{batch_id}:payout:{agent_id}", memo="Payout in flight",
        )

    async def complete_payout(self, batch_id: str, agent_id: str, amount_micro: int) -> dict:
        return await self.post(
            [
                {"account": PAYOUT_IN_FLIGHT, "amount_micro": -amount_micro},
                {"account": TREASURY_FLOAT, "amount_micro": amount_micro},
            ],
            txn_kind="payout_settled", ref_type="settlement", ref_id=batch_id,
            idem_key=f"settlement:{batch_id}:settled:{agent_id}", memo="Payout captured by PayPal",
        )

    async def reverse_payout(self, batch_id: str, agent_id: str, amount_micro: int, reason: str = "") -> dict:
        return await self.post(
            [
                {"account": PAYOUT_IN_FLIGHT, "amount_micro": -amount_micro},
                {"account": AGENT_AVAILABLE, "agent_id": agent_id, "amount_micro": amount_micro},
            ],
            txn_kind="payout_reversal", ref_type="settlement", ref_id=batch_id,
            idem_key=f"settlement:{batch_id}:reversal:{agent_id}", memo=reason or "Payout failed",
        )

    # -------------------------------------------------------------- integrity
    async def invariant(self) -> dict:
        """Check the blueprint invariants and reconcile caches against the ledger.

        Three things must hold: every transaction sums to zero, no wallet field
        is negative, and every wallet cache equals the sum of its ledger lines.
        Without the third check a failed debit could silently strand a ledger
        transaction that the wallet never saw.
        """
        cursor = self.db.ledger_entries.find({}, {"amount_micro": 1, "txn_id": 1, "account": 1, "agent_id": 1})
        total = 0
        by_txn: Dict[str, int] = {}
        expected: Dict[tuple, int] = {}
        async for entry in cursor:
            amount = int(entry["amount_micro"])
            total += amount
            by_txn[entry["txn_id"]] = by_txn.get(entry["txn_id"], 0) + amount
            field = AGENT_ACCOUNTS.get(entry.get("account"))
            if field and entry.get("agent_id"):
                key = (entry["agent_id"], field)
                expected[key] = expected.get(key, 0) + amount
        unbalanced = [txn for txn, amount in by_txn.items() if amount != 0]

        negative: List[dict] = []
        mismatches: List[dict] = []
        wallets = [wallet async for wallet in self.db.wallets.find({}, {"_id": 0})]
        seen = set()
        for wallet in wallets:
            agent_id = wallet["agent_id"]
            for field in AGENT_ACCOUNTS.values():
                cached = int(wallet.get(field, 0))
                ledger_amount = expected.get((agent_id, field), 0)
                seen.add((agent_id, field))
                if cached < 0:
                    negative.append({"agent_id": agent_id, "field": field, "amount_micro": cached})
                if cached != ledger_amount:
                    mismatches.append({"agent_id": agent_id, "field": field,
                                       "wallet_micro": cached, "ledger_micro": ledger_amount})
        missing = [{"agent_id": agent_id, "field": field, "wallet_micro": 0,
                    "ledger_micro": amount}
                   for (agent_id, field), amount in expected.items()
                   if (agent_id, field) not in seen and amount != 0]

        ok = total == 0 and not unbalanced and not negative and not mismatches and not missing
        return {
            "ok": ok,
            "sum_micro": total,
            "transactions": len(by_txn),
            "unbalanced_txns": unbalanced[:20],
            "negative_wallets": negative[:20],
            "wallet_mismatches": (mismatches + missing)[:20],
            "checked_at": _now().isoformat(),
        }

    async def rebuild_wallets(self) -> int:
        """Recompute wallet and account caches from the append-only ledger."""
        aggregates: Dict[str, int] = {}
        cursor = self.db.ledger_entries.find({}, {"account": 1, "agent_id": 1, "amount_micro": 1})
        async for entry in cursor:
            if entry["account"] in AGENT_ACCOUNTS:
                key = f"{entry['agent_id']}|{entry['account']}"
                aggregates[key] = aggregates.get(key, 0) + int(entry["amount_micro"])

        await self.db.wallets.delete_many({})
        await self.db.account_totals.delete_many({})
        totals: Dict[str, int] = {}
        wallets: Dict[str, dict] = {}
        for entry in await self.db.ledger_entries.distinct("account"):
            totals.setdefault(entry, 0)
        async for entry in self.db.ledger_entries.find({}, {"account": 1, "amount_micro": 1, "agent_id": 1}):
            totals[entry["account"]] = totals.get(entry["account"], 0) + int(entry["amount_micro"])
        for key, amount in aggregates.items():
            agent_id, account = key.split("|")
            doc = wallets.setdefault(agent_id, {
                "agent_id": agent_id, "available_micro": 0, "escrow_micro": 0,
                "bond_micro": 0, "dispute_hold_micro": 0, "dust_micro": 0,
                "currency": CURRENCY, "version": 0,
                "created_at": _now(),
            })
            doc[AGENT_ACCOUNTS[account]] = amount
        if wallets:
            for doc in wallets.values():
                doc["updated_at"] = _now()
            await self.db.wallets.insert_many(list(wallets.values()))
        for account, amount in totals.items():
            await self.db.account_totals.update_one({"_id": account},
                                                    {"$set": {"amount_micro": amount, "updated_at": _now()}},
                                                    upsert=True)
        return len(wallets)

    async def statement(self, agent_id: str, limit: int = 100) -> List[dict]:
        cursor = self.db.ledger_entries.find({"agent_id": agent_id}, {"_id": 0}).sort("posted_at", -1).limit(limit)
        return [doc async for doc in cursor]

    async def entries(self, limit: int = 200, agent_id: Optional[str] = None) -> List[dict]:
        query = {"agent_id": agent_id} if agent_id else {}
        cursor = self.db.ledger_entries.find(query, {"_id": 0}).sort("posted_at", -1).limit(limit)
        return [doc async for doc in cursor]

    async def transaction(self, txn_id: str) -> List[dict]:
        cursor = self.db.ledger_entries.find({"txn_id": txn_id}, {"_id": 0})
        return [doc async for doc in cursor]
