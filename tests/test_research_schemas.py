"""Structured Bull/Bear trade hypothesis and review-outcome schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tradingagents.agents.schemas import (
    ConvictionScore,
    EntryLevel,
    EntryLevelType,
    InitialResearchThesis,
    NewDataException,
    ResearchDirection,
    ResearchReviewOutcome,
    SuggestedRiskUnit,
    TradePlanAction,
    TradePlanFieldChange,
    render_initial_thesis,
    render_review_outcome,
    suggested_risk_unit_for,
)


@pytest.mark.unit
def test_conviction_total_is_always_the_sum_of_components_even_if_llm_lies():
    score = ConvictionScore.model_validate(
        {
            "evidence_quality": 18,
            "internal_consistency": 21,
            "robustness_to_challenge": 17,
            "trade_plan_coherence": 19,
            "total": 80,  # deliberately wrong arithmetic; must not survive validation
        }
    )
    assert score.total == 75


@pytest.mark.unit
def test_conviction_components_and_total_are_bounded():
    with pytest.raises(ValidationError):
        ConvictionScore(
            evidence_quality=26,
            internal_consistency=0,
            robustness_to_challenge=0,
            trade_plan_coherence=0,
        )
    score = ConvictionScore(
        evidence_quality=25, internal_consistency=25,
        robustness_to_challenge=25, trade_plan_coherence=25,
    )
    assert score.total == 100
    score = ConvictionScore(
        evidence_quality=0, internal_consistency=0,
        robustness_to_challenge=0, trade_plan_coherence=0,
    )
    assert score.total == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    "total, expected",
    [
        (0, SuggestedRiskUnit.NO_TRADE),
        (49, SuggestedRiskUnit.NO_TRADE),
        (50, SuggestedRiskUnit.LOW),
        (64, SuggestedRiskUnit.LOW),
        (65, SuggestedRiskUnit.MEDIUM),
        (79, SuggestedRiskUnit.MEDIUM),
        (80, SuggestedRiskUnit.HIGH),
        (100, SuggestedRiskUnit.HIGH),
    ],
)
def test_suggested_risk_unit_mapping(total, expected):
    assert suggested_risk_unit_for(total) is expected


def _conviction(total_target=75):
    # Components chosen to sum to total_target for readability in tests below.
    quarter = total_target // 4
    remainder = total_target - quarter * 4
    return ConvictionScore(
        evidence_quality=quarter + remainder,
        internal_consistency=quarter,
        robustness_to_challenge=quarter,
        trade_plan_coherence=quarter,
    )


@pytest.mark.unit
def test_entry_level_reference_uses_midpoint_for_a_range():
    entry = EntryLevel(type=EntryLevelType.RANGE, low=82900, high=83300)
    assert entry.reference == pytest.approx(83100)
    entry = EntryLevel(type=EntryLevelType.POINT, price=100)
    assert entry.reference == 100


@pytest.mark.unit
def test_initial_thesis_contains_all_required_fields_and_derives_risk_unit():
    thesis = InitialResearchThesis(
        direction=ResearchDirection.BULL,
        conviction=_conviction(75),
        horizon="5-10 trading sessions",
        entry=EntryLevel(type=EntryLevelType.RANGE, low=82900, high=83300),
        take_profit=87360,
        stop_loss=80920,
        thesis="The uptrend remains intact with supportive momentum.",
        evidence=["RSI in the 50-65 bucket", "Price above SMA50"],
        risks=["Macro event risk this week"],
        data_gaps=["No options-flow data supplied"],
    )
    assert thesis.direction is ResearchDirection.BULL
    assert thesis.conviction.total == 75
    assert thesis.suggested_risk_unit is SuggestedRiskUnit.MEDIUM  # 65-79 -> MEDIUM
    rendered = render_initial_thesis(thesis)
    for expected in (
        "BULL", "5-10 trading sessions", "82900", "83300", "87360.0", "80920.0",
        "NOT a probability", "MEDIUM", "not a position size", "RSI in the 50-65 bucket",
    ):
        assert expected in rendered


@pytest.mark.unit
def test_initial_thesis_rejects_placeholder_tp_sl_like_other_price_fields():
    thesis = InitialResearchThesis(
        direction=ResearchDirection.BEAR,
        conviction=_conviction(40),
        horizon="5-10 trading sessions",
        entry=EntryLevel(type=EntryLevelType.POINT, price=100),
        take_profit="N/A",
        stop_loss="tbd",
        thesis="Caution warranted.",
    )
    assert thesis.take_profit is None
    assert thesis.stop_loss is None
    assert thesis.suggested_risk_unit is SuggestedRiskUnit.NO_TRADE


@pytest.mark.unit
def test_review_outcome_records_keep_revise_withdraw_and_conviction_change():
    outcome = ResearchReviewOutcome(
        accepted=["Corrected subtraction is 3,126.56"],
        rejected=["Selective-evidence objection has no supplied support"],
        unresolved=["Whether the macro catalyst materializes this week"],
        trade_plan_changes={
            "entry": {"action": "KEEP"},
            "take_profit": {
                "action": "WITHDRAW",
                "reason": "Original target came from a low-confidence social post.",
            },
            "stop_loss": {
                "action": "REVISE",
                "old": 80920,
                "new": 76860,
                "reason": "Original stop was inconsistent with the stated horizon.",
            },
        },
        conviction_before=82,
        conviction_after=68,
        conviction_reason="One macro assumption was withdrawn.",
        remaining_disagreements=["Valuation interpretation"],
    )
    assert outcome.trade_plan_changes.stop_loss.action is TradePlanAction.REVISE
    assert outcome.trade_plan_changes.take_profit.action is TradePlanAction.WITHDRAW
    assert outcome.trade_plan_changes.entry.action is TradePlanAction.KEEP

    rendered = render_review_outcome(outcome)
    assert rendered.startswith("ACCEPTED: Corrected subtraction is 3,126.56")
    assert "REJECTED: Selective-evidence objection has no supplied support" in rendered
    assert "UNRESOLVED: Whether the macro catalyst materializes this week" in rendered
    assert "Stop Loss: REVISE (80920.0 -> 76860.0)" in rendered
    assert "Take Profit: WITHDRAW" in rendered
    assert "82 -> 68" in rendered
    assert "not a probability" in rendered


@pytest.mark.unit
def test_review_outcome_can_increase_decrease_or_hold_conviction():
    increase = ResearchReviewOutcome(conviction_before=50, conviction_after=65)
    decrease = ResearchReviewOutcome(conviction_before=65, conviction_after=50)
    unchanged = ResearchReviewOutcome(conviction_before=60, conviction_after=60)
    assert increase.conviction_after > increase.conviction_before
    assert decrease.conviction_after < decrease.conviction_before
    assert unchanged.conviction_after == unchanged.conviction_before


@pytest.mark.unit
def test_review_outcome_normalises_loose_dict_and_string_inputs():
    outcome = ResearchReviewOutcome.model_validate(
        {
            "accepted": {"claim": "Bear's correction", "reason": "arithmetic was wrong"},
            "rejected": "A single string instead of a list",
            "conviction_before": 70,
            "conviction_after": 70,
            "new_data_exceptions": {
                "datum": "New CPI print",
                "reason": "Corrects a stale inflation assumption",
                "source": "Fundamentals report",
            },
        }
    )
    assert outcome.accepted == ["Bear's correction | arithmetic was wrong"]
    assert outcome.rejected == ["A single string instead of a list"]
    assert len(outcome.new_data_exceptions) == 1
    assert isinstance(outcome.new_data_exceptions[0], NewDataException)


@pytest.mark.unit
def test_new_data_exception_is_explicit_and_machine_identifiable():
    outcome = ResearchReviewOutcome(
        conviction_before=60,
        conviction_after=60,
        new_data_exceptions=[
            NewDataException(
                datum="Unscheduled rate decision",
                reason="Materially changes the horizon-relevant risk",
                source="News report",
            )
        ],
    )
    rendered = render_review_outcome(outcome)
    assert "NEW_DATA_EXCEPTION" in rendered
    assert "Unscheduled rate decision" in rendered


@pytest.mark.unit
def test_initial_thesis_coerces_json_stringified_list_fields():
    """Regression (batch run 2026-10-01): a weak structured-output call
    serialized risks/data_gaps as a JSON-encoded string instead of a native
    array, which used to fail the whole call with a list_type error."""
    thesis = InitialResearchThesis(
        direction=ResearchDirection.BULL,
        conviction=_conviction(70),
        horizon="5-10 trading sessions",
        entry=EntryLevel(type=EntryLevelType.POINT, price=100),
        thesis="Test.",
        evidence='["Price above SMA50", "RSI neutral"]',
        risks='["Macro event risk this week"]',
        data_gaps="[]",
    )
    assert thesis.evidence == ["Price above SMA50", "RSI neutral"]
    assert thesis.risks == ["Macro event risk this week"]
    assert thesis.data_gaps == []


@pytest.mark.unit
def test_initial_thesis_wraps_a_plain_string_list_field_instead_of_failing():
    thesis = InitialResearchThesis(
        direction=ResearchDirection.BULL,
        conviction=_conviction(70),
        horizon="5-10 trading sessions",
        entry=EntryLevel(type=EntryLevelType.POINT, price=100),
        thesis="Test.",
        risks="Single risk as a bare string, not a list",
    )
    assert thesis.risks == ["Single risk as a bare string, not a list"]


@pytest.mark.unit
def test_trade_plan_field_change_coerces_placeholder_numbers():
    change = TradePlanFieldChange.model_validate(
        {"action": "REVISE", "old": "80,920", "new": "N/A", "reason": "test"}
    )
    assert change.old == 80920
    assert change.new is None
