"""Small consistency cleanup requested after the Risk redesign was accepted:

1. "sized by how decisively it wins" (Research Manager / Portfolio Manager)
   conflicted with the policy that evidence strength must not become
   portfolio sizing -- replaced with an explicit "do not translate
   decisiveness into ... size" instruction.
2. Global policy's "lowering a position" was ambiguous with a portfolio
   position -- replaced with "lowering conviction".
3. The Trader could not preserve a verified entry RANGE (forced to collapse
   it into a single invented price) -- TraderProposal now supports
   entry_price_low/entry_price_high alongside the single entry_price, plus an
   explicitly labelled reference_entry calculation value.
"""

from __future__ import annotations

import pytest

from tradingagents.agents.schemas import (
    PortfolioDecision,
    ResearchPlan,
    TraderProposal,
    render_trader_proposal,
)
from tradingagents.prompts.loader import load_prompt

# --- 1: no more "sized by how decisively it wins" ---------------------------


@pytest.mark.unit
@pytest.mark.parametrize("path", ["managers/research_manager.txt", "managers/portfolio_manager.txt"])
def test_decisively_it_wins_wording_is_gone_from_prompts(path):
    text = load_prompt(path)
    assert "decisively it wins" not in text


@pytest.mark.unit
@pytest.mark.parametrize("path", ["managers/research_manager.txt", "managers/portfolio_manager.txt"])
def test_prompts_explicitly_forbid_translating_decisiveness_into_sizing(path):
    text = load_prompt(path)
    assert "do not translate decisiveness into portfolio size" in text.lower()


@pytest.mark.unit
def test_research_plan_recommendation_description_has_no_decisively_it_wins_wording():
    description = ResearchPlan.model_fields["recommendation"].description or ""
    assert "decisively it wins" not in description
    assert "do not translate decisiveness" in description.lower()


@pytest.mark.unit
def test_portfolio_decision_rating_description_has_no_decisively_it_wins_wording():
    description = PortfolioDecision.model_fields["rating"].description or ""
    assert "decisively it wins" not in description
    assert "do not translate decisiveness" in description.lower()


# --- 2: global policy says "lowering conviction", not "lowering a position" -


@pytest.mark.unit
def test_global_policy_says_lowering_conviction_not_lowering_a_position():
    text = load_prompt("global_policy.txt")
    assert "lowering a position" not in text
    assert "lowering conviction" in text
    # Preserve the intended meaning: correction is success, not loss.
    assert "correction is success, not loss" in text.lower()


# --- 3: Trader preserves a verified entry range ------------------------------


@pytest.mark.unit
def test_trader_prompt_no_longer_forbids_a_range_outright():
    system_text = load_prompt("trader/system.txt").lower()
    assert "never a percentage or a range" not in system_text
    assert "preserve both bounds" in system_text


@pytest.mark.unit
def test_trader_system_prompt_distinguishes_reference_from_execution_entry():
    text = load_prompt("trader/system.txt").lower()
    assert "reference calculation value" in text
    assert "silent substitute" in text


@pytest.mark.unit
def test_verified_entry_range_is_preserved_as_both_bounds():
    proposal = TraderProposal(
        action="Buy", reasoning="x",
        entry_price_low=223.13, entry_price_high=225.45,
        stop_loss=210.0,
    )
    rendered = render_trader_proposal(proposal)
    assert "**Entry Price**: 223.13 - 225.45" in rendered
    assert "**Entry Price**: 224.29" not in rendered  # no invented midpoint


@pytest.mark.unit
def test_verified_single_entry_is_preserved_as_a_single_price():
    proposal = TraderProposal(action="Buy", reasoning="x", entry_price=189.5, stop_loss=180.0)
    rendered = render_trader_proposal(proposal)
    assert "**Entry Price**: 189.5" in rendered
    assert " - " not in rendered.split("**Entry Price**:")[1].splitlines()[0]


@pytest.mark.unit
def test_no_arbitrary_midpoint_is_invented_when_only_a_range_is_given():
    """Setting a range must not also silently populate the single entry_price
    field with a midpoint -- the two are mutually exclusive in practice."""
    proposal = TraderProposal(
        action="Buy", reasoning="x", entry_price_low=100.0, entry_price_high=110.0,
    )
    assert proposal.entry_price is None


@pytest.mark.unit
def test_deterministic_reference_entry_is_distinguishable_from_execution_entry():
    proposal = TraderProposal(
        action="Buy", reasoning="x",
        entry_price_low=223.13, entry_price_high=225.45,
        reference_entry=224.29,
    )
    rendered = render_trader_proposal(proposal)
    assert "**Entry Price**: 223.13 - 225.45" in rendered
    assert "**Reference Entry (calculated)**: 224.29" in rendered


@pytest.mark.unit
def test_reference_entry_line_is_absent_when_not_provided():
    proposal = TraderProposal(action="Buy", reasoning="x", entry_price=189.5)
    rendered = render_trader_proposal(proposal)
    assert "Reference Entry" not in rendered


@pytest.mark.unit
def test_research_trade_plan_shows_entry_reference_distinct_from_entry():
    from tradingagents.agents.researchers.research_summary import render_trade_plan_for_trader

    debate = {
        "bull_thesis": {
            "direction": "LONG",
            "entry": {"type": "range", "low": 223.13, "high": 225.45},
            "take_profit": 240.0, "stop_loss": 210.0,
            "suggested_risk_unit": "MEDIUM",
        },
        "bull_trade_metrics": {"entry_reference": 224.29, "reward_risk": 1.5},
    }
    text = render_trade_plan_for_trader(debate)
    assert "Entry: 223.13 - 225.45 (range)" in text
    assert "Entry Reference" in text
    assert "224.29" in text
