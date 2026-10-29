"""Deterministic guardrail rules.

Every rule is pure and unit-tested. The LLM never decides whether a rule
passes: it only proposes numbers, and these functions accept or reject them.
"""
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from app.settings import settings


@dataclass
class RuleResult:
    rule: str
    passed: bool
    reason: str
    detail: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"rule": self.rule, "passed": self.passed, "reason": self.reason, "detail": self.detail}


@dataclass
class GuardrailDecision:
    passed: bool
    results: List[RuleResult]

    @property
    def failed(self) -> List[str]:
        return [r.rule for r in self.results if not r.passed]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "failed": self.failed,
            "results": [r.to_dict() for r in self.results],
        }


def _decision(results: List[RuleResult]) -> GuardrailDecision:
    return GuardrailDecision(passed=all(r.passed for r in results), results=results)


def price_band(price_micro: int, reference_micro: int, band_bps: int) -> RuleResult:
    """Price must sit inside (reference +/- band). 1 bps = 0.01%."""
    if reference_micro <= 0:
        return RuleResult("price_band", False, "reference price unavailable",
                          {"price_micro": price_micro})
    low = reference_micro * (10000 - band_bps) // 10000
    high = reference_micro * (10000 + band_bps) // 10000
    ok = low <= price_micro <= high
    return RuleResult(
        "price_band", ok,
        f"price {price_micro} within band [{low}, {high}]" if ok else f"price {price_micro} outside band [{low}, {high}]",
        {"price_micro": price_micro, "reference_micro": reference_micro, "band_bps": band_bps,
         "low_micro": low, "high_micro": high},
    )


def per_trade_cap(price_micro: int, cap_micro: int) -> RuleResult:
    if price_micro > cap_micro:
        return RuleResult("per_trade_cap", False, f"price {price_micro} exceeds per-trade cap {cap_micro}",
                          {"cap_micro": cap_micro})
    return RuleResult("per_trade_cap", True, "within per-trade cap", {"cap_micro": cap_micro})


def daily_cap(spent_today_micro: int, price_micro: int, cap_micro: int) -> RuleResult:
    total = spent_today_micro + price_micro
    ok = total <= cap_micro
    return RuleResult("daily_cap", ok,
                      f"daily spend {total}/{cap_micro}" if ok else f"daily cap exceeded: {total}/{cap_micro}",
                      {"spent_today_micro": spent_today_micro, "cap_micro": cap_micro})


def budget_available(available_micro: int, price_micro: int) -> RuleResult:
    ok = available_micro >= price_micro
    return RuleResult("budget_available", ok,
                      "buyer can cover escrow" if ok else "insufficient available balance for escrow",
                      {"available_micro": available_micro, "price_micro": price_micro})


def allowlist(counterparty_id: str, allowed: Sequence[str]) -> RuleResult:
    if allowed and counterparty_id not in allowed:
        return RuleResult("allowlist", False, f"{counterparty_id} is not on the allowlist",
                          {"allowed": list(allowed)})
    return RuleResult("allowlist", True, "counterparty allowed", {"allowed": list(allowed)})


def self_trade(buyer_id: str, seller_id: str) -> RuleResult:
    ok = buyer_id != seller_id
    return RuleResult("self_trade", ok, "distinct counterparties" if ok else "buyer and seller are the same agent")


def velocity(recent_count: int, limit_per_min: int) -> RuleResult:
    ok = recent_count < limit_per_min
    return RuleResult("velocity", ok,
                      f"{recent_count}/{limit_per_min} trades in the last minute",
                      {"recent_count": recent_count, "limit": limit_per_min})


def approval_threshold(amount_micro: int, has_approval: bool,
                       threshold_micro: Optional[int] = None) -> RuleResult:
    threshold = settings.APPROVAL_THRESHOLD_MICRO if threshold_micro is None else threshold_micro
    if amount_micro >= threshold and not has_approval:
        return RuleResult("approval_threshold", False,
                          f"{amount_micro} micro needs operator approval (threshold {threshold})",
                          {"threshold_micro": threshold})
    return RuleResult("approval_threshold", True, "approval requirement satisfied",
                      {"threshold_micro": threshold})


def funding_cap(amount_micro: int) -> RuleResult:
    ok = 0 < amount_micro <= settings.FUNDING_MAX_MICRO
    return RuleResult("funding_cap", ok,
                      f"amount {amount_micro} within funding cap" if ok else f"amount {amount_micro} outside funding cap",
                      {"max_micro": settings.FUNDING_MAX_MICRO})


def payout_minimum(amount_micro: int) -> RuleResult:
    ok = amount_micro >= settings.PAYOUT_MIN_MICRO
    return RuleResult("payout_minimum", ok,
                      f"{amount_micro} at or above payout floor" if ok else f"{amount_micro} below payout floor",
                      {"min_micro": settings.PAYOUT_MIN_MICRO})


def payout_daily_cap(batch_micro: int, paid_today_micro: int) -> RuleResult:
    total = batch_micro + paid_today_micro
    ok = total <= settings.PAYOUT_DAILY_CAP_MICRO
    return RuleResult("payout_daily_cap", ok,
                      f"daily payouts {total}/{settings.PAYOUT_DAILY_CAP_MICRO}" if ok
                      else f"daily payout cap exceeded: {total}/{settings.PAYOUT_DAILY_CAP_MICRO}",
                      {"paid_today_micro": paid_today_micro})


def treasury_reserve(batch_micro: int, treasury_float_micro: int) -> RuleResult:
    remaining = treasury_float_micro - batch_micro
    ok = remaining >= settings.TREASURY_RESERVE_MICRO
    return RuleResult("treasury_reserve", ok,
                      f"treasury float after batch {remaining}" if ok
                      else f"batch would breach treasury reserve: {remaining}",
                      {"treasury_float_micro": treasury_float_micro,
                       "reserve_micro": settings.TREASURY_RESERVE_MICRO})


def kill_switch(active: bool) -> RuleResult:
    ok = not active
    return RuleResult("kill_switch", ok,
                      "kill switch inactive" if ok else "kill switch active: state changes blocked")


def job_limits(job_type: str, size: int, allowed: Dict[str, int]) -> RuleResult:
    limit = allowed.get(job_type)
    if limit is None:
        return RuleResult("job_limits", False, f"job type {job_type} is not allowed", {"allowed": list(allowed)})
    ok = 0 < size <= limit
    return RuleResult("job_limits", ok,
                      f"{job_type} size {size} within limit {limit}" if ok else f"{job_type} size {size} exceeds limit {limit}",
                      {"limit": limit})


def loan_terms(principal_micro: int, rate_bps: int, max_principal_micro: int, max_rate_bps: int) -> List[RuleResult]:
    results = [
        RuleResult("loan_principal", 0 < principal_micro <= max_principal_micro,
                   f"principal {principal_micro} vs max {max_principal_micro}",
                   {"max_principal_micro": max_principal_micro}),
        RuleResult("loan_rate", 0 <= rate_bps <= max_rate_bps,
                   f"rate {rate_bps}bps vs max {max_rate_bps}bps", {"max_rate_bps": max_rate_bps}),
    ]
    return results


def evaluate_trade(buyer_policy: dict, seller_policy: dict, price_micro: int, reference_micro: int,
                   buyer_available_micro: int, spent_today_micro: int, recent_trades: int,
                   has_approval: bool = False, kill_active: bool = False) -> GuardrailDecision:
    """The full deterministic gate applied before escrow."""
    allowed = list(buyer_policy.get("allowlist") or [])
    results = [
        kill_switch(kill_active),
        per_trade_cap(price_micro, int(buyer_policy.get("per_trade_cap_micro", settings.MAX_TRADE_MICRO))),
        daily_cap(spent_today_micro, price_micro, int(buyer_policy.get("daily_cap_micro", settings.MAX_TRADE_MICRO))),
        budget_available(buyer_available_micro, price_micro),
        price_band(price_micro, reference_micro, int(buyer_policy.get("price_band_bps", 2500))),
        price_band(price_micro, reference_micro, int(seller_policy.get("price_band_bps", 2500))),
        allowlist(seller_policy.get("agent_id", ""), allowed) if allowed else RuleResult(
            "allowlist", True, "no allowlist configured", {}),
        velocity(recent_trades, int(buyer_policy.get("velocity_per_min", 12))),
        approval_threshold(price_micro, has_approval,
                           int(buyer_policy.get("approval_threshold_micro", settings.APPROVAL_THRESHOLD_MICRO))),
    ]
    return _decision(results)


def evaluate_offer(price_micro: int, quantity: int, reference_micro: int, band_bps: int,
                   cap_micro: int) -> GuardrailDecision:
    """Gate applied to each negotiation move before it is sent to the counterparty."""
    results = [
        RuleResult("positive_offer", price_micro > 0 and quantity > 0,
                   "offer is positive", {"price_micro": price_micro, "quantity": quantity}),
        price_band(price_micro, reference_micro, band_bps),
        per_trade_cap(price_micro, cap_micro),
    ]
    return _decision(results)


def evaluate_settlement(batch_micro: int, paid_today_micro: int, treasury_float_micro: int,
                        has_approval: bool, kill_active: bool = False) -> GuardrailDecision:
    results = [
        kill_switch(kill_active),
        payout_minimum(batch_micro),
        payout_daily_cap(batch_micro, paid_today_micro),
        treasury_reserve(batch_micro, treasury_float_micro),
        approval_threshold(batch_micro, has_approval),
    ]
    return _decision(results)


def evaluate_funding(amount_micro: int, kill_active: bool = False) -> GuardrailDecision:
    return _decision([kill_switch(kill_active), funding_cap(amount_micro)])


def clamp_offer(price_micro: int, reference_micro: int, band_bps: int, floor_micro: int = 1) -> int:
    """Deterministic fallback when the LLM is unavailable or proposes nonsense."""
    low = max(floor_micro, reference_micro * (10000 - band_bps) // 10000)
    high = max(low, reference_micro * (10000 + band_bps) // 10000)
    return max(low, min(high, price_micro))
