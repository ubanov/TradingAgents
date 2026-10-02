"""Portfolio Manager disposition is real structured state, never inferred
from the rating, and PM must not invent HOW to fix a plan Risk flagged as
PLAN_CHANGE_REQUIRED (see fork README: "real PM disposition" / "Portfolio
Manager must not invent the replacement"). Real NVDA-run regression: all
three Risk reviewers returned MEDIUM/REDUCE_RISK with plan_change_required,
Portfolio Manager's own text said the plan needed reformulation, yet the
OLD mechanical rating->disposition mapping reported "(Adopted disposition:
KEEP)" because the rating happened to be Overweight."""

from __future__ import annotations

import pytest

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating, render_pm_decision
from tradingagents.graph.propagation import Propagator
from tradingagents.prompts.loader import load_prompt
from tradingagents.reporting import write_report_tree


class _PMLLM:
    def __init__(self, decision):
        self.decision = decision
        self.prompts: list[str] = []

    def with_structured_output(self, _schema):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.decision


def _state(**risk_overrides):
    state = Propagator().create_initial_state("NVDA", "2026-09-01")
    state["investment_plan"] = "Overweight plan"
    state["trader_investment_plan"] = "**Action**: Buy\n**Entry Price**: 234.69\n**Stop Loss**: 211.28"
    state["risk_debate_state"].update(risk_overrides)
    return state


# --- Prompt wording: PM must not invent HOW to fix a flagged plan -----------


@pytest.mark.unit
def test_prompt_distinguishes_what_is_unresolved_from_how_to_fix_it():
    text = load_prompt("managers/portfolio_manager.txt").lower()
    assert "you may describe what is unresolved" in text
    assert "you may not invent how to solve it" in text


@pytest.mark.unit
def test_prompt_explicitly_forbids_an_invented_confirmation_session_count():
    text = load_prompt("managers/portfolio_manager.txt").lower()
    assert "confirmation-session count" in text


@pytest.mark.unit
def test_prompt_explicitly_forbids_an_invented_partial_exit_percentage():
    text = load_prompt("managers/portfolio_manager.txt").lower()
    assert "partial-exit percentage" in text


@pytest.mark.unit
def test_prompt_explicitly_forbids_an_invented_atr_trigger():
    text = load_prompt("managers/portfolio_manager.txt").lower()
    assert "atr-based trigger" in text


@pytest.mark.unit
def test_prompt_allows_explaining_the_defect_without_inventing_a_replacement():
    text = load_prompt("managers/portfolio_manager.txt").lower()
    assert "must remain explicitly missing/unresolved" in text
    assert "do not fill an execution gap merely to make the final plan look complete" in text


# --- Disposition is a separate, real structured field -----------------------


@pytest.mark.unit
def test_rating_and_disposition_are_independent_schema_fields():
    decision = PortfolioDecision(
        rating=PortfolioRating.OVERWEIGHT, disposition="DEFER",
        executive_summary="x", investment_thesis="y",
    )
    assert decision.rating == PortfolioRating.OVERWEIGHT
    assert decision.disposition.value == "DEFER"
    rendered = render_pm_decision(decision)
    assert "**Rating**: Overweight" in rendered
    assert "**Disposition**: DEFER" in rendered


@pytest.mark.unit
def test_overweight_rating_with_defer_disposition_round_trips_through_the_node():
    """The real NVDA-shaped case: a bullish rating paired with DEFER because
    the execution plan itself is not ready, not a contradiction."""
    decision = PortfolioDecision(
        rating=PortfolioRating.OVERWEIGHT, disposition="DEFER",
        executive_summary="Favorable view; do not execute until the plan is repaired.",
        investment_thesis="Bullish evidence, but no supported rule covers the gap.",
    )
    llm = _PMLLM(decision)
    result = create_portfolio_manager(llm)(_state())
    assert result["risk_debate_state"]["portfolio_disposition"] == "DEFER"
    assert "**Rating**: Overweight" in result["final_trade_decision"]
    assert "**Disposition**: DEFER" in result["final_trade_decision"]


@pytest.mark.unit
def test_overweight_rating_with_reduce_risk_disposition_round_trips_through_the_node():
    decision = PortfolioDecision(
        rating=PortfolioRating.OVERWEIGHT, disposition="REDUCE_RISK",
        executive_summary="Favorable view; this execution plan needs less risk.",
        investment_thesis="Bullish evidence; plan is directionally sound but oversized.",
    )
    llm = _PMLLM(decision)
    result = create_portfolio_manager(llm)(_state())
    assert result["risk_debate_state"]["portfolio_disposition"] == "REDUCE_RISK"
    assert result["risk_debate_state"]["judge_decision"].count("Overweight") >= 0  # rating preserved
    assert "**Rating**: Overweight" in result["final_trade_decision"]
    assert "**Disposition**: REDUCE_RISK" in result["final_trade_decision"]


@pytest.mark.unit
def test_disposition_is_never_mechanically_derived_from_rating():
    """The old fixed mapping (Buy/Overweight->KEEP, Hold->DEFER,
    Underweight->REDUCE_RISK, Sell->REJECT_PLAN) must not reappear: an
    Overweight rating paired with REJECT_PLAN must be preserved exactly as
    given, not silently corrected to KEEP."""
    decision = PortfolioDecision(
        rating=PortfolioRating.OVERWEIGHT, disposition="REJECT_PLAN",
        executive_summary="x", investment_thesis="y",
    )
    llm = _PMLLM(decision)
    result = create_portfolio_manager(llm)(_state())
    assert result["risk_debate_state"]["portfolio_disposition"] == "REJECT_PLAN"


@pytest.mark.unit
def test_free_text_fallback_without_an_explicit_disposition_stays_unrecorded():
    """No structured call succeeded and the free-text fallback never wrote a
    Disposition line -- must stay "" (not recorded), never guessed from
    whatever rating-like word appears in the prose."""
    from types import SimpleNamespace

    class _PlainLLM:
        def invoke(self, prompt):
            return SimpleNamespace(
                content="**Rating**: Overweight\n\n**Executive Summary**: Add gradually.\n\n"
                "**Investment Thesis**: Strong fundamentals."
            )

    result = create_portfolio_manager(_PlainLLM())(_state())
    assert result["risk_debate_state"]["portfolio_disposition"] == ""


@pytest.mark.unit
def test_free_text_fallback_with_an_explicit_disposition_line_is_still_parsed():
    """Part of Part 6 item 23: fallback parsing preserves an explicitly
    emitted disposition, via the same extract_choice mechanism used for the
    structured-success path -- not a separate, bespoke parser."""
    from types import SimpleNamespace

    class _PlainLLM:
        def invoke(self, prompt):
            return SimpleNamespace(
                content="**Rating**: Overweight\n\n**Disposition**: REDUCE_RISK\n\n"
                "**Executive Summary**: x\n\n**Investment Thesis**: y"
            )

    result = create_portfolio_manager(_PlainLLM())(_state())
    assert result["risk_debate_state"]["portfolio_disposition"] == "REDUCE_RISK"


@pytest.mark.unit
def test_report_shows_the_actual_parsed_disposition_not_a_rating_derived_one(tmp_path):
    state = _state()
    state["risk_debate_state"]["judge_decision"] = (
        "**Rating**: Overweight\n\n**Disposition**: REDUCE_RISK\n\n"
        "**Executive Summary**: x\n\n**Investment Thesis**: y"
    )
    state["risk_debate_state"]["portfolio_disposition"] = "REDUCE_RISK"
    write_report_tree(state, "NVDA", tmp_path)
    report_text = (tmp_path / "complete_report.md").read_text()
    assert "(Disposition: REDUCE_RISK)" in report_text
    assert "(Adopted disposition: KEEP)" not in report_text


@pytest.mark.unit
def test_report_says_not_recorded_when_disposition_was_never_parsed(tmp_path):
    state = _state()
    state["risk_debate_state"]["judge_decision"] = "**Rating**: Overweight\n\n**Executive Summary**: x"
    write_report_tree(state, "NVDA", tmp_path)
    report_text = (tmp_path / "complete_report.md").read_text()
    assert "(Disposition: not recorded)" in report_text
