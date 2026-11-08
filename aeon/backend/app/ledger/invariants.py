"""Pure invariant helpers.

These operate on plain data so they can be property-tested without a database.
"""
from typing import Dict, Iterable, List, Sequence


def txn_balances(lines: Sequence[dict]) -> int:
    return sum(int(line["amount_micro"]) for line in lines)


def is_balanced(lines: Sequence[dict]) -> bool:
    return txn_balances(lines) == 0


def all_transactions_balanced(entries: Iterable[dict]) -> bool:
    totals: Dict[str, int] = {}
    for entry in entries:
        totals[entry["txn_id"]] = totals.get(entry["txn_id"], 0) + int(entry["amount_micro"])
    return all(v == 0 for v in totals.values())


def wallets_non_negative(wallets: Iterable[dict]) -> bool:
    fields = ("available_micro", "escrow_micro", "bond_micro", "dispute_hold_micro")
    return all(int(w.get(f, 0)) >= 0 for w in wallets for f in fields)


def double_entry_holds(entries: Iterable[dict], wallets: Iterable[dict]) -> bool:
    entries = list(entries)
    return (sum(int(e["amount_micro"]) for e in entries) == 0
            and all_transactions_balanced(entries)
            and wallets_non_negative(wallets))


def ledger_matches_wallets(entries: Iterable[dict], wallets: Dict[str, dict]) -> bool:
    """Wallet caches must equal the sum of their ledger lines."""
    expected: Dict[str, Dict[str, int]] = {}
    fields = ("available_micro", "escrow_micro", "bond_micro", "dispute_hold_micro")
    field_for = {"agent_available": "available_micro", "agent_escrow": "escrow_micro",
                 "agent_bond": "bond_micro", "agent_dispute_hold": "dispute_hold_micro"}
    for entry in entries:
        field = field_for.get(entry["account"])
        if not field:
            continue
        bucket = expected.setdefault(entry["agent_id"], {name: 0 for name in fields})
        bucket[field] += int(entry["amount_micro"])
    for agent_id, bucket in expected.items():
        wallet = wallets.get(agent_id)
        if wallet is None:
            return False
        for field, amount in bucket.items():
            if int(wallet.get(field, 0)) != amount:
                return False
    return True


def assert_balanced(lines: List[dict]) -> List[dict]:
    if not is_balanced(lines):
        raise ValueError(f"unbalanced transaction: {txn_balances(lines)}")
    return lines
