"""Deterministic post-Research-Manager integrity check (no LLM involved).

Each case below is drawn from the categories and real-run examples in the
fork README / design spec: a manager reusing already-verified evidence must
PASS; a manager inventing a new operational threshold, sizing rule, or yield
trigger must WARN with the right finding category.
"""

from __future__ import annotations

import pytest

from tradingagents.agents.managers.integrity_check import (
    ManagerFindingCategory,
    build_known_number_pool,
    check_manager_integrity,
    extract_numbers,
)


def _debate(**overrides):
    base = {
        "bull_thesis": {},
        "bear_thesis": {},
        "bull_trade_metrics": {},
        "bear_trade_metrics": {},
        "withdrawn_values": [],
    }
    base.update(overrides)
    return base


@pytest.mark.unit
def test_extract_numbers_handles_currency_percent_and_magnitude_suffixes():
    assert extract_numbers("RSI is 65.3 and volume is 120M, up +0.5 from $189.50") == [
        65.3, 120_000_000, 0.5, 189.50,
    ]


@pytest.mark.unit
def test_manager_reusing_an_analyst_supported_threshold_passes():
    manager_text = "If RSI exceeds 65.3, the momentum thesis strengthens."
    market_report = "Technical snapshot: RSI (14) is currently 65.3, trending up."
    result = check_manager_integrity(manager_text, _debate(), market_report)
    assert result.status == "PASS"
    assert result.findings == []


@pytest.mark.unit
def test_manager_reusing_a_verified_bull_bear_level_passes():
    manager_text = "A close below 178.0 would invalidate the bullish thesis."
    debate = _debate(bull_thesis={"take_profit": 210.0, "stop_loss": 178.0, "entry": {}})
    result = check_manager_integrity(manager_text, debate, "", "", "", "")
    assert result.status == "PASS"


@pytest.mark.unit
def test_manager_using_a_deterministic_derived_metric_passes():
    manager_text = "The setup's reward/risk exceeds 1.78, which supports sizing up."
    debate = _debate(bull_trade_metrics={"reward_risk": 1.78})
    result = check_manager_integrity(manager_text, debate, "", "", "", "")
    assert result.status == "PASS"


@pytest.mark.unit
def test_manager_inventing_a_macd_threshold_warns():
    manager_text = "Only act once the MACD histogram exceeds +0.5."
    result = check_manager_integrity(manager_text, _debate(), "", "", "", "")
    assert result.status == "WARN"
    assert result.findings[0].category == ManagerFindingCategory.NEW_UNSUPPORTED_THRESHOLD.value


@pytest.mark.unit
def test_manager_inventing_a_volume_threshold_warns():
    manager_text = "The plan requires volume to exceed 120M before entering."
    result = check_manager_integrity(manager_text, _debate(), "", "", "", "")
    assert result.status == "WARN"
    assert result.findings[0].category == ManagerFindingCategory.NEW_UNSUPPORTED_THRESHOLD.value


@pytest.mark.unit
def test_manager_inventing_an_allocation_percentage_warns_as_sizing_rule():
    manager_text = "Reduce exposure by 25% immediately given the mixed signals."
    result = check_manager_integrity(manager_text, _debate(), "", "", "", "")
    assert result.status == "WARN"
    assert result.findings[0].category == ManagerFindingCategory.UNSUPPORTED_SIZING_RULE.value


@pytest.mark.unit
def test_manager_inventing_a_yield_trigger_warns():
    manager_text = "If the 30Y yield rises above 5.20%, exit the position."
    result = check_manager_integrity(manager_text, _debate(), "", "", "", "")
    assert result.status == "WARN"
    assert result.findings[0].category == ManagerFindingCategory.NEW_UNSUPPORTED_THRESHOLD.value


@pytest.mark.unit
def test_withdrawn_level_resurfacing_is_flagged():
    manager_text = "Take profit remains at 95000, as originally proposed."
    debate = _debate(withdrawn_values=[95000])
    result = check_manager_integrity(manager_text, debate, "", "", "", "")
    assert result.status == "WARN"
    assert any(
        f.category == ManagerFindingCategory.WITHDRAWN_VALUE_REUSED.value
        for f in result.findings
    )


@pytest.mark.unit
def test_conviction_described_as_probability_is_flagged():
    manager_text = "Our conviction of 75 implies a 75% probability of the bullish outcome."
    result = check_manager_integrity(manager_text, _debate(), "", "", "", "")
    assert result.status == "WARN"
    assert any(
        f.category == ManagerFindingCategory.CONVICTION_AS_PROBABILITY.value
        for f in result.findings
    )


@pytest.mark.unit
def test_ordinary_narrative_numbers_do_not_trigger_false_positives():
    manager_text = (
        "The debate ran for 2 rounds. Q3 revenue was $50B, roughly in line with estimates. "
        "The stock closed at 189.5 on 2026-09-30."
    )
    result = check_manager_integrity(manager_text, _debate(), "", "", "", "")
    assert result.status == "PASS"


@pytest.mark.unit
def test_build_known_number_pool_covers_reports_theses_and_metrics():
    debate = _debate(
        bull_thesis={"entry": {"price": 100}, "take_profit": 110, "stop_loss": 90},
        bear_trade_metrics={"reward_risk": 1.5, "risk": 10.0},
    )
    pool = build_known_number_pool(debate, "RSI is 55")
    for expected in (55, 100, 110, 90, 1.5, 10.0):
        assert expected in pool


@pytest.mark.unit
def test_empty_manager_output_and_empty_debate_do_not_crash():
    result = check_manager_integrity("", {}, "", "", "", "")
    assert result.status == "PASS"


@pytest.mark.unit
def test_manager_reusing_a_claim_bull_bear_already_corrected_warns():
    """Real-run example (NVDA): Bull/Bear corrected a flawed '-8.8% normalized
    sequential profit' claim to approximately '+18.2%' during review; the
    Research Manager later reintroduced the retired -8.8% figure. Sign-aware
    reuse detection lives in ``extract_signed_numbers``/
    ``find_withdrawn_values_reused`` (see test_signed_withdrawn_values.py)."""
    debate = _debate(
        review_outcomes=(
            "ACCEPTED: normalized profit growth\n\n**Arithmetic Corrections**:\n"
            "- -8.8% normalized sequential decline corrected to +18.2% using consistent "
            "quarter-over-quarter normalization\n"
        ),
    )
    manager_text = "The normalized profit declined -8.8% sequentially, which is a concern."
    result = check_manager_integrity(manager_text, debate, "", "", "", "")
    assert result.status == "WARN"
    assert any(
        f.category == ManagerFindingCategory.WITHDRAWN_VALUE_REUSED.value for f in result.findings
    )


@pytest.mark.unit
def test_manager_reward_risk_inconsistent_with_deterministic_metrics_warns():
    """Real-run example (SPY): Manager stated an R/R of 1.59:1 for levels
    whose deterministic reward_risk is approximately 1.00."""
    debate = _debate(bull_trade_metrics={"reward_risk": 1.00})
    manager_text = "The Bull setup offers an R/R of 1.59:1 given the proposed levels."
    result = check_manager_integrity(manager_text, debate, "", "", "", "")
    assert result.status == "WARN"
    assert any(
        f.category == ManagerFindingCategory.ARITHMETIC_ERROR.value for f in result.findings
    )


@pytest.mark.unit
def test_manager_relational_comparison_error_warns():
    """Real-run example (NVDA): a relational error equivalent to saying
    216.48 is below 199.81."""
    manager_text = "The current price of 216.48 is below the prior resistance of 199.81."
    result = check_manager_integrity(manager_text, _debate(), "", "", "", "")
    assert result.status == "WARN"
    assert any(
        f.category == ManagerFindingCategory.RELATIONAL_ERROR.value for f in result.findings
    )


@pytest.mark.unit
def test_manager_consistent_structured_arithmetic_and_relations_pass():
    debate = _debate(bull_trade_metrics={"reward_risk": 1.78})
    manager_text = (
        "The reward/risk ratio of 1.78:1 is attractive, and the current price of 199.81 "
        "is below the prior resistance of 216.48."
    )
    result = check_manager_integrity(manager_text, debate, "", "", "", "")
    assert result.status == "PASS"
