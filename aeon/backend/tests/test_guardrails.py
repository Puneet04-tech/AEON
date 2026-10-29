"""Every guardrail rule has an explicit pass and fail case."""
from app.guardrails import rules


def test_price_band_edges():
    assert rules.price_band(10_000, 10_000, 2500).passed
    assert rules.price_band(7_500, 10_000, 2500).passed
    assert rules.price_band(12_500, 10_000, 2500).passed
    assert not rules.price_band(7_499, 10_000, 2500).passed
    assert not rules.price_band(12_501, 10_000, 2500).passed


def test_price_band_without_reference_fails_closed():
    assert not rules.price_band(100, 0, 2500).passed


def test_caps():
    assert rules.per_trade_cap(1_000, 1_000).passed
    assert not rules.per_trade_cap(1_001, 1_000).passed
    assert rules.daily_cap(500, 500, 1_000).passed
    assert not rules.daily_cap(600, 500, 1_000).passed
    assert rules.budget_available(1_000, 1_000).passed
    assert not rules.budget_available(999, 1_000).passed


def test_allowlist_and_self_trade():
    assert rules.allowlist("b", ["a", "b"]).passed
    assert not rules.allowlist("c", ["a", "b"]).passed
    assert rules.allowlist("c", []).passed  # empty allowlist means "anyone"
    assert not rules.self_trade("a", "a").passed
    assert rules.self_trade("a", "b").passed


def test_velocity_and_approval():
    assert rules.velocity(0, 2).passed
    assert not rules.velocity(2, 2).passed
    assert rules.approval_threshold(100, False, 1_000).passed
    assert not rules.approval_threshold(1_000, False, 1_000).passed
    assert rules.approval_threshold(1_000, True, 1_000).passed


def test_funding_and_payout_rules(monkeypatch):
    monkeypatch.setattr(rules.settings, "FUNDING_MAX_MICRO", 1_000)
    assert rules.funding_cap(1_000).passed
    assert not rules.funding_cap(1_001).passed
    assert not rules.funding_cap(0).passed

    monkeypatch.setattr(rules.settings, "PAYOUT_MIN_MICRO", 500)
    assert rules.payout_minimum(500).passed
    assert not rules.payout_minimum(499).passed

    monkeypatch.setattr(rules.settings, "PAYOUT_DAILY_CAP_MICRO", 1_000)
    assert rules.payout_daily_cap(500, 500).passed
    assert not rules.payout_daily_cap(500, 501).passed


def test_treasury_reserve(monkeypatch):
    monkeypatch.setattr(rules.settings, "TREASURY_RESERVE_MICRO", 100)
    assert rules.treasury_reserve(50, 150).passed
    assert not rules.treasury_reserve(51, 150).passed


def test_kill_switch_blocks():
    assert rules.kill_switch(False).passed
    assert not rules.kill_switch(True).passed


def test_job_limits():
    allowed = {"image_resize": 1_000, "matrix_multiply": 10}
    assert rules.job_limits("image_resize", 500, allowed).passed
    assert not rules.job_limits("image_resize", 1_001, allowed).passed
    assert not rules.job_limits("gpu_training", 1, allowed).passed


def test_loan_terms():
    results = rules.loan_terms(1_000, 800, 5_000, 2_500)
    assert all(r.passed for r in results)
    results = rules.loan_terms(6_000, 2_600, 5_000, 2_500)
    assert not any(r.passed for r in results)


def test_evaluate_trade_aggregates_failures():
    buyer = {"agent_id": "buyer", "per_trade_cap_micro": 1_000, "daily_cap_micro": 10_000,
             "price_band_bps": 2500, "allowlist": ["seller"], "velocity_per_min": 5,
             "approval_threshold_micro": 10_000}
    seller = {"agent_id": "seller", "price_band_bps": 2500}
    good = rules.evaluate_trade(buyer, seller, price_micro=1_000, reference_micro=1_000,
                                buyer_available_micro=5_000, spent_today_micro=0, recent_trades=0)
    assert good.passed, good.to_dict()

    too_expensive = rules.evaluate_trade(buyer, seller, price_micro=2_000, reference_micro=1_000,
                                         buyer_available_micro=5_000, spent_today_micro=0,
                                         recent_trades=0)
    assert not too_expensive.passed
    assert {"price_band", "per_trade_cap"} <= set(too_expensive.failed)

    blocked = rules.evaluate_trade(buyer, seller, price_micro=1_000, reference_micro=1_000,
                                   buyer_available_micro=5_000, spent_today_micro=0,
                                   recent_trades=0, kill_active=True)
    assert "kill_switch" in blocked.failed


def test_clamp_offer_stays_in_band():
    assert rules.clamp_offer(1, 10_000, 2500) == 7_500
    assert rules.clamp_offer(1_000_000, 10_000, 2500) == 12_500
    assert rules.clamp_offer(10_100, 10_000, 2500) == 10_100
