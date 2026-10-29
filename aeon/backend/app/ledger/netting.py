"""Netting: many tiny trades become a few payout lines.

Only `available` balance is payable; escrow and bond stay inside AEON because
they still back open trades and SLA obligations.
"""
from datetime import datetime, timezone
from typing import Dict, Iterable, List

from app.settings import settings


def net_positions(wallets: Iterable[dict], paypal_emails: Dict[str, str],
                  exclude: Iterable[str] = (),
                  eligible: Iterable[str] = None) -> List[dict]:
    """Net payable positions, largest first, dropping anything below the floor.

    `eligible` restricts the batch to agents that opted into cash-out; agents
    that are net-positive but keep their balance in AEON are skipped.
    """
    excluded = set(exclude)
    allowed = set(eligible) if eligible is not None else None
    positions: List[dict] = []
    for wallet in wallets:
        agent_id = wallet["agent_id"]
        if agent_id in excluded:
            continue
        if allowed is not None and agent_id not in allowed:
            continue
        available = int(wallet.get("available_micro", 0))
        if available < settings.PAYOUT_MIN_MICRO:
            continue
        email = paypal_emails.get(agent_id)
        if not email:
            continue  # cannot pay an agent with no PayPal email
        positions.append({
            "agent_id": agent_id,
            "paypal_email": email,
            "amount_micro": available,
        })
    positions.sort(key=lambda p: p["amount_micro"], reverse=True)
    return positions


def apply_caps(positions: List[dict], available_float_micro: int, daily_remaining_micro: int) -> List[dict]:
    """Trim the batch to the treasury float, daily cap and reserve."""
    budget = max(0, min(available_float_micro - settings.TREASURY_RESERVE_MICRO,
                        daily_remaining_micro))
    accepted: List[dict] = []
    for position in positions:
        if position["amount_micro"] <= budget:
            accepted.append(position)
            budget -= position["amount_micro"]
    return accepted


def totals(positions: List[dict]) -> Dict[str, int]:
    return {"items": len(positions), "amount_micro": sum(p["amount_micro"] for p in positions)}


def day_start_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def requires_approval(amount_micro: int) -> bool:
    return amount_micro >= settings.APPROVAL_THRESHOLD_MICRO
