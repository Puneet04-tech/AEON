"""Ledger correctness: balance, escrow, idempotency, invariants, property tests."""
import pytest
from hypothesis import given, settings as hyp_settings, strategies as st

from app.ledger import invariants
from app.ledger.service import (
    AGENT_AVAILABLE,
    AGENT_ESCROW,
    InsufficientFunds,
    LedgerError,
    LedgerService,
    TREASURY_FLOAT,
)


async def fund(ledger, agent_id, amount):
    await ledger.wallet(agent_id)
    return await ledger.post(
        [{"account": TREASURY_FLOAT, "amount_micro": -amount},
         {"account": AGENT_AVAILABLE, "agent_id": agent_id, "amount_micro": amount}],
        txn_kind="test", ref_type="test", ref_id=f"fund:{agent_id}",
        idem_key=f"test:fund:{agent_id}:{amount}",
    )


async def test_post_is_balanced_and_auditable(db, ledger):
    await fund(ledger, "a1", 5_000)
    entries = await ledger.entries(agent_id="a1")
    assert len(entries) == 1
    assert entries[0]["amount_micro"] == 5_000
    assert entries[0]["currency"] == "USD"
    report = await ledger.invariant()
    assert report["ok"] is True
    assert report["sum_micro"] == 0


async def test_unbalanced_transaction_is_rejected(ledger):
    with pytest.raises(LedgerError):
        await ledger.post([{"account": TREASURY_FLOAT, "amount_micro": -100}],
                          txn_kind="bad", ref_type="x", ref_id="x", idem_key="bad:key:0001")


async def test_float_amounts_are_rejected(ledger):
    with pytest.raises(LedgerError):
        await ledger.post(
            [{"account": TREASURY_FLOAT, "amount_micro": -1.5},
             {"account": AGENT_AVAILABLE, "agent_id": "a1", "amount_micro": 1.5}],
            txn_kind="bad", ref_type="x", ref_id="x", idem_key="bad:key:0002")


async def test_escrow_release_and_refund(db, ledger):
    await fund(ledger, "buyer", 10_000)
    await ledger.escrow("t1", "buyer", 4_000)
    assert await ledger.balance("buyer", AGENT_AVAILABLE) == 6_000
    assert await ledger.balance("buyer", AGENT_ESCROW) == 4_000

    await ledger.release("t1", "buyer", "seller", 4_000)
    assert await ledger.balance("buyer", AGENT_ESCROW) == 0
    assert await ledger.balance("seller", AGENT_AVAILABLE) == 4_000

    await ledger.escrow("t2", "buyer", 1_000)
    assert await ledger.balance("buyer", AGENT_AVAILABLE) == 5_000
    await ledger.refund("t2", "buyer", 1_000)
    assert await ledger.balance("buyer", AGENT_AVAILABLE) == 6_000
    assert (await ledger.invariant())["ok"] is True


async def test_overdraft_is_impossible(db, ledger):
    await fund(ledger, "poor", 500)
    with pytest.raises(InsufficientFunds):
        await ledger.escrow("t3", "poor", 501)
    assert await ledger.balance("poor", AGENT_AVAILABLE) == 500


async def test_posting_is_idempotent(db, ledger):
    first = await fund(ledger, "a1", 1_000)
    second = await ledger.post(
        [{"account": TREASURY_FLOAT, "amount_micro": -1_000},
         {"account": AGENT_AVAILABLE, "agent_id": "a1", "amount_micro": 1_000}],
        txn_kind="test", ref_type="test", ref_id="fund:a1",
        idem_key="test:fund:a1:1000",
    )
    assert second["duplicate"] is True
    assert second["txn_id"] == first["txn_id"]
    assert await ledger.balance("a1", AGENT_AVAILABLE) == 1_000


async def test_penalty_moves_bond_to_buyer(db, ledger):
    await fund(ledger, "seller", 2_000)
    await ledger.post_bond("seller", 2_000, "bond", "bond-1")
    await ledger.penalty("t4", "seller", "buyer", 500)
    assert await ledger.balance("seller") == 0
    assert await ledger.balance("buyer", AGENT_AVAILABLE) == 500
    assert (await ledger.invariant())["ok"] is True


async def test_rebuild_wallets_restores_cache(db, ledger):
    await fund(ledger, "a1", 3_000)
    await ledger.escrow("t5", "a1", 1_250)
    await db.wallets.update_one({"agent_id": "a1"}, {"$set": {"available_micro": 0, "escrow_micro": 0}})
    await ledger.rebuild_wallets()
    assert await ledger.balance("a1", AGENT_AVAILABLE) == 1_750
    assert await ledger.balance("a1", AGENT_ESCROW) == 1_250
    assert (await ledger.invariant())["ok"] is True


@hyp_settings(max_examples=40, deadline=None)
@given(
    amounts=st.lists(st.integers(min_value=2, max_value=100_000), min_size=1, max_size=6),
    fractions=st.lists(st.floats(min_value=0.05, max_value=0.95, allow_nan=False), min_size=1, max_size=6),
)
def test_pure_invariant_holds_for_random_postings(amounts, fractions):
    """For any balanced postings, totals are zero and wallet caches agree."""
    entries = []
    expected = {"a": 0, "b": 0}
    for index, amount in enumerate(amounts):
        split = max(1, min(amount - 1, int(amount * fractions[index % len(fractions)])))
        txn = f"txn{index}"
        entries.append({"txn_id": txn, "account": TREASURY_FLOAT, "amount_micro": -amount})
        entries.append({"txn_id": txn, "account": AGENT_AVAILABLE, "agent_id": "a", "amount_micro": split})
        entries.append({"txn_id": txn, "account": AGENT_AVAILABLE, "agent_id": "b", "amount_micro": amount - split})
        expected["a"] += split
        expected["b"] += amount - split
    wallets = {agent: {"available_micro": total} for agent, total in expected.items()}
    assert invariants.double_entry_holds(entries, wallets.values())
    assert invariants.ledger_matches_wallets(entries, wallets)


async def test_invariant_detects_corruption(db, ledger):
    await fund(ledger, "a1", 1_000)
    await db.ledger_entries.insert_one({
        "id": "le_corrupt", "txn_id": "txn_corrupt", "account": TREASURY_FLOAT,
        "agent_id": None, "amount_micro": -7, "currency": "USD", "ref": {"type": "x", "id": "y"},
        "idem_key": "corrupt:key:1", "posted_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc),
    })
    report = await ledger.invariant()
    assert report["ok"] is False
    assert report["sum_micro"] != 0
