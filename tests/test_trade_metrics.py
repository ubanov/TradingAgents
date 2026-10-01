"""Deterministic trade-plan metrics (fork README: Deterministic trade calculations)."""

from __future__ import annotations

import pytest

from tradingagents.agents.researchers.trade_metrics import (
    compute_trade_metrics,
    entry_reference,
    render_trade_metrics,
)


@pytest.mark.unit
def test_worked_example_matches_spec_numbers():
    metrics = compute_trade_metrics(
        entry_price=83000, take_profit=87000, stop_loss=80500, atr=2192.41
    )
    assert metrics.entry_reference == 83000
    assert metrics.risk == pytest.approx(2500)
    assert metrics.reward == pytest.approx(4000)
    assert metrics.reward_risk == pytest.approx(1.6)
    assert metrics.stop_atr == pytest.approx(2500 / 2192.41)
    assert metrics.target_atr == pytest.approx(4000 / 2192.41)
    assert metrics.risk_pct == pytest.approx(2500 / 83000 * 100)
    assert metrics.reward_pct == pytest.approx(4000 / 83000 * 100)


@pytest.mark.unit
def test_entry_range_uses_midpoint_as_reference():
    assert entry_reference(None, 82900, 83300) == pytest.approx(83100)
    metrics = compute_trade_metrics(entry_low=82900, entry_high=83300, take_profit=87360, stop_loss=80920)
    assert metrics.entry_reference == pytest.approx(83100)


@pytest.mark.unit
def test_one_sided_range_falls_back_to_the_present_bound():
    assert entry_reference(None, 100, None) == 100
    assert entry_reference(None, None, 200) == 200
    assert entry_reference(None, None, None) is None


@pytest.mark.unit
def test_point_entry_takes_precedence_over_range_fields():
    assert entry_reference(150, 100, 200) == 150


@pytest.mark.unit
def test_missing_entry_tp_sl_does_not_crash():
    metrics = compute_trade_metrics()
    assert metrics.entry_reference is None
    assert metrics.risk is None
    assert metrics.reward is None
    assert metrics.reward_risk is None
    assert metrics.stop_atr is None
    assert metrics.target_atr is None

    metrics = compute_trade_metrics(entry_price=100)
    assert metrics.entry_reference == 100
    assert metrics.risk is None
    assert metrics.reward is None

    metrics = compute_trade_metrics(entry_price=100, stop_loss=90)
    assert metrics.risk == pytest.approx(10)
    assert metrics.reward is None
    assert metrics.reward_risk is None  # no reward => no ratio, not a crash


@pytest.mark.unit
def test_zero_entry_and_zero_atr_do_not_crash():
    metrics = compute_trade_metrics(entry_price=0, take_profit=10, stop_loss=-10)
    assert metrics.entry_reference == 0
    assert metrics.risk is None
    assert metrics.reward is None

    metrics = compute_trade_metrics(entry_price=100, take_profit=110, stop_loss=90, atr=0)
    assert metrics.risk == pytest.approx(10)
    assert metrics.stop_atr is None
    assert metrics.target_atr is None


@pytest.mark.unit
def test_render_trade_metrics_handles_missing_values():
    metrics = compute_trade_metrics()
    rendered = render_trade_metrics(metrics)
    assert "N/A" in rendered
    assert "Reward/Risk" in rendered
