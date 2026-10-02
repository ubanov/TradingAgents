"""Signed corrected/withdrawn values are tracked and detected on reuse, without
a broad number-extraction change that would misread a hyphenated range (e.g.
"5-10") as a negative number (see fork README / completion report: the real
NVDA regression where a corrected "-8.8%" figure resurfaced later).

The fix is scoped to ``extract_signed_numbers``/``find_withdrawn_values_reused``
in ``integrity_shared.py`` -- the general-purpose ``extract_numbers`` used for
threshold/sizing/historical scanning is unchanged."""

from __future__ import annotations

import pytest

from tradingagents.agents.integrity_shared import (
    extract_corrected_away_numbers,
    extract_numbers,
    extract_signed_numbers,
    find_withdrawn_values_reused,
)
from tradingagents.agents.managers.integrity_check import (
    ManagerFindingCategory,
    check_manager_integrity,
)
from tradingagents.agents.risk_mgmt.integrity_check import (
    RiskFindingCategory,
    check_risk_integrity,
)


def _debate(**overrides):
    base = {
        "bull_thesis": {}, "bear_thesis": {},
        "bull_trade_metrics": {}, "bear_trade_metrics": {},
        "withdrawn_values": [],
    }
    base.update(overrides)
    return base


def _risk_state(**overrides):
    base = {
        "investment_debate_state": _debate(),
        "trader_investment_plan": "**Action**: Buy\n**Entry Price**: 100.0\n**Stop Loss**: 95.0",
        "market_report": "", "sentiment_report": "", "news_report": "", "fundamentals_report": "",
    }
    base.update(overrides)
    return base


# 1. corrected -8.8% is recorded as retired/corrected numerical provenance ---


@pytest.mark.unit
def test_corrected_negative_percentage_is_extracted_as_retired_provenance():
    notes = [
        "- -8.8% normalized sequential decline corrected to +18.2% using consistent "
        "quarter-over-quarter normalization"
    ]
    assert extract_corrected_away_numbers(notes) == [-8.8]


# 2. later reuse of -8.8% by Research Manager is detected ---------------------


@pytest.mark.unit
def test_research_manager_reusing_corrected_negative_percentage_warns():
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


# 3. later reuse of -8.8% during Risk is detected when applicable ------------


@pytest.mark.unit
def test_risk_reusing_corrected_negative_percentage_warns():
    state = _risk_state(
        investment_debate_state=_debate(withdrawn_values=[-8.8]),
    )
    text = "The normalized profit declined -8.8% sequentially, which raises concerns."
    result = check_risk_integrity(text, state)
    assert result.status == "WARN"
    assert any(
        f.category == RiskFindingCategory.WITHDRAWN_VALUE_REUSED.value for f in result.findings
    )


# 4. a range like 5-10 is still parsed as positive endpoints, not 5 and -10 --


@pytest.mark.unit
def test_hyphenated_range_is_not_misread_as_a_negative_number():
    assert extract_signed_numbers("a 5-10 trading session horizon") == [5.0, 10.0]
    assert extract_numbers("a 5-10 trading session horizon") == [5.0, 10.0]


@pytest.mark.unit
def test_range_mention_does_not_trigger_a_false_withdrawn_match():
    # Withdrawn value -10 would only ever come from an actual negative figure;
    # a plain range mentioning "10" must not spuriously match it as "-10".
    findings = find_withdrawn_values_reused("The horizon is 5-10 trading sessions.", [-10.0])
    assert findings == []


@pytest.mark.unit
def test_manager_integrity_does_not_misfire_on_a_research_horizon_range():
    debate = _debate(withdrawn_values=[-10.0])
    manager_text = "The recommended holding period is a 5-10 trading session horizon."
    result = check_manager_integrity(manager_text, debate, "", "", "", "")
    assert result.status == "PASS"


# 5. ordinary negative indicators (MACD histogram) remain valid, unflagged ---


@pytest.mark.unit
def test_macd_histogram_negative_value_is_not_treated_as_a_corrected_value():
    debate = _debate(withdrawn_values=[])  # nothing was actually withdrawn
    manager_text = "MACD histogram is -0.163, confirming bearish momentum."
    result = check_manager_integrity(manager_text, debate, "", "", "", "")
    assert result.status == "PASS"


@pytest.mark.unit
def test_macd_histogram_value_coincidentally_matching_a_withdrawn_figure_is_still_flagged():
    """Sign-awareness must not become a blanket exemption for negative
    numbers -- if -0.163 really was withdrawn, reusing it is still a finding."""
    debate = _debate(withdrawn_values=[-0.163])
    manager_text = "MACD histogram is -0.163, confirming bearish momentum."
    result = check_manager_integrity(manager_text, debate, "", "", "", "")
    assert result.status == "WARN"
