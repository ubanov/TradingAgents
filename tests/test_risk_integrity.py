"""Deterministic post-Risk integrity check (no LLM involved) -- see fork
README: "Risk integrity check". Each case is drawn from the categories and
real-run examples in the task spec: Risk reusing already-verified/frozen
evidence must PASS; Risk inventing a new threshold, sizing rule, historical
claim, probability, or arithmetic/relational error must WARN."""

from __future__ import annotations

import pytest

from tradingagents.agents.risk_mgmt.integrity_check import (
    RiskFindingCategory,
    check_risk_integrity,
)


def _state(**overrides):
    base = {
        "investment_debate_state": {
            "bull_trade_metrics": {"reward_risk": 2.0},
            "bear_trade_metrics": {},
            "withdrawn_values": [],
        },
        "trader_investment_plan": "**Action**: Buy\n**Entry Price**: 100.0\n**Stop Loss**: 95.0",
        "market_report": "RSI is 55",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
    }
    base.update(overrides)
    return base


@pytest.mark.unit
def test_supported_trader_entry_reused_passes():
    text = "The plan enters at 100.0 with a stop at 95.0, consistent with the trader's proposal."
    assert check_risk_integrity(text, _state()).status == "PASS"


@pytest.mark.unit
def test_new_arbitrary_threshold_warns():
    text = "If volatility exceeds 5.5%, reduce exposure immediately."
    result = check_risk_integrity(text, _state())
    assert result.status == "WARN"


@pytest.mark.unit
def test_reduce_portfolio_percentage_without_portfolio_context_warns():
    text = "We should reduce the portfolio by 25% to control risk."
    assert check_risk_integrity(text, _state()).status == "WARN"


@pytest.mark.unit
def test_historical_frequency_claim_not_in_frozen_evidence_warns():
    text = "Historically, this setup succeeds 70% of the time."
    result = check_risk_integrity(text, _state())
    assert result.status == "WARN"
    assert any(
        f.category == RiskFindingCategory.UNSUPPORTED_HISTORICAL_CLAIM.value
        for f in result.findings
    )


@pytest.mark.unit
def test_fabricated_probability_warns():
    text = "There is a 65% probability of a pullback here."
    result = check_risk_integrity(text, _state())
    assert result.status == "WARN"
    assert any(
        f.category == RiskFindingCategory.UNSUPPORTED_PROBABILITY_OR_FREQUENCY.value
        for f in result.findings
    )


@pytest.mark.unit
def test_arithmetic_error_in_reward_risk_warns():
    text = "The reward/risk ratio of 3.5:1 looks attractive here."
    result = check_risk_integrity(text, _state())
    assert result.status == "WARN"
    assert any(f.category == RiskFindingCategory.ARITHMETIC_ERROR.value for f in result.findings)


@pytest.mark.unit
def test_reward_risk_matching_deterministic_metrics_passes():
    text = "The reward/risk ratio of 2.0:1 confirms the plan is well-structured."
    assert check_risk_integrity(text, _state()).status == "PASS"


@pytest.mark.unit
def test_simple_relational_error_warns():
    text = "Note that 216.48 is below 199.81, confirming the downtrend."
    result = check_risk_integrity(text, _state())
    assert result.status == "WARN"
    assert any(f.category == RiskFindingCategory.RELATIONAL_ERROR.value for f in result.findings)


@pytest.mark.unit
def test_correct_relational_claim_passes():
    text = "Note that 199.81 is below 216.48, consistent with the chart."
    assert check_risk_integrity(text, _state()).status == "PASS"


@pytest.mark.unit
def test_retired_or_revised_value_reused_warns():
    state = _state(
        investment_debate_state={
            "bull_trade_metrics": {}, "bear_trade_metrics": {}, "withdrawn_values": [90.0],
        }
    )
    text = "The original stop at 90.0 still applies regardless of the trader's update."
    result = check_risk_integrity(text, state)
    assert result.status == "WARN"
    assert any(
        f.category == RiskFindingCategory.WITHDRAWN_VALUE_REUSED.value for f in result.findings
    )


@pytest.mark.unit
def test_contradiction_with_trader_stop_warns():
    text = "The trader stop should actually be 80.0 given recent volatility."
    result = check_risk_integrity(text, _state())
    assert result.status == "WARN"
    assert any(
        f.category == RiskFindingCategory.CONTRADICTION_WITH_TRADER.value for f in result.findings
    )


@pytest.mark.unit
def test_normal_narrative_with_no_dangerous_new_numbers_passes():
    text = "The plan looks reasonable given current conditions and should hold up well."
    assert check_risk_integrity(text, _state()).status == "PASS"


@pytest.mark.unit
def test_free_text_fallback_is_still_checked():
    """A free-text-fallback Risk turn (no structured assessment) is plain
    prose -- the integrity check runs on whatever text it produced regardless
    of whether structured output succeeded."""
    text = "Plain prose fallback argument: reduce exposure by 40% immediately."
    assert check_risk_integrity(text, _state()).status == "WARN"


@pytest.mark.unit
def test_empty_text_and_empty_state_do_not_crash():
    result = check_risk_integrity("", {})
    assert result.status == "PASS"


@pytest.mark.unit
def test_unit_error_percentage_used_as_a_price_level_warns():
    text = "The stop loss should be set at 5% as an absolute level."
    result = check_risk_integrity(text, _state())
    assert result.status == "WARN"
    assert any(f.category == RiskFindingCategory.UNIT_ERROR.value for f in result.findings)
