"""Portfolio Manager provenance restrictions: Risk arguments are assessments,
not new evidence -- an unsupported claim raised only during Risk must never
be promoted as verified input, and Portfolio Manager has no structured field
through which it could invent a replacement entry/stop/take-profit level
(see fork README: "Portfolio Manager provenance restrictions")."""

from __future__ import annotations

import pytest

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating
from tradingagents.graph.propagation import Propagator


class _PMLLM:
    def __init__(self, decision: PortfolioDecision):
        self.decision = decision
        self.prompts: list[str] = []

    def with_structured_output(self, _schema):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.decision


def _state(**risk_overrides):
    state = Propagator().create_initial_state("NVDA", "2026-09-01")
    state["investment_plan"] = "Buy plan"
    state["trader_investment_plan"] = "**Action**: Buy\n**Entry Price**: 100.0\n**Stop Loss**: 95.0"
    state["risk_debate_state"].update(
        {
            "history": "\nAggressive Reviewer (Independent Assessment): Risk level: LOW\n"
            "Disposition: KEEP\nRationale: fine.\n"
            "\nConservative Reviewer (Cross-Review): If volatility exceeds 5.5%, reduce exposure.",
        }
    )
    state["risk_debate_state"].update(risk_overrides)
    return state


@pytest.mark.unit
def test_portfolio_manager_receives_risk_integrity_findings_in_its_prompt():
    """A Risk turn containing an unsupported threshold must surface as a named
    finding in the Portfolio Manager's own prompt."""
    llm = _PMLLM(PortfolioDecision(
        rating=PortfolioRating.HOLD, disposition="DEFER", executive_summary="x", investment_thesis="y",
    ))
    create_portfolio_manager(llm)(_state())
    prompt = llm.prompts[0]
    assert "Risk Integrity Check" in prompt
    assert "5.5" in prompt  # the unsupported threshold itself is visible


@pytest.mark.unit
def test_portfolio_manager_prompt_instructs_not_to_treat_unsupported_risk_claims_as_evidence():
    llm = _PMLLM(PortfolioDecision(
        rating=PortfolioRating.HOLD, disposition="DEFER", executive_summary="x", investment_thesis="y",
    ))
    create_portfolio_manager(llm)(_state())
    prompt = llm.prompts[0]
    assert "assessments, not new evidence" in prompt
    assert "do not treat them as verified input" in prompt.lower() or "not treat it as verified input" in prompt.lower()


@pytest.mark.unit
def test_portfolio_manager_stores_risk_integrity_status_and_findings():
    llm = _PMLLM(PortfolioDecision(
        rating=PortfolioRating.HOLD, disposition="DEFER", executive_summary="x", investment_thesis="y",
    ))
    result = create_portfolio_manager(llm)(_state())
    risk_state = result["risk_debate_state"]
    assert risk_state["risk_integrity_status"] == "WARN"
    assert any(f["category"] for f in risk_state["risk_integrity_findings"])


@pytest.mark.unit
def test_portfolio_manager_passes_when_risk_discussion_has_no_unsupported_claims():
    state = _state(history="\nAggressive Reviewer (Independent Assessment): The plan looks fine.")
    llm = _PMLLM(PortfolioDecision(
        rating=PortfolioRating.HOLD, disposition="DEFER", executive_summary="x", investment_thesis="y",
    ))
    result = create_portfolio_manager(llm)(state)
    assert result["risk_debate_state"]["risk_integrity_status"] == "PASS"
    assert "No unsupported claims detected" in llm.prompts[0]


@pytest.mark.unit
@pytest.mark.parametrize(
    "rating", [PortfolioRating.BUY, PortfolioRating.OVERWEIGHT, PortfolioRating.HOLD,
               PortfolioRating.UNDERWEIGHT, PortfolioRating.SELL]
)
def test_portfolio_manager_accepts_every_rating_without_inventing_replacement_levels(rating):
    """PortfolioDecision has no entry/stop/take-profit override field, so
    whichever of KEEP(Buy/Overweight)/DEFER(Hold)/REDUCE_RISK(Underweight)/
    REJECT_PLAN(Sell) the call lands on, there is structurally no field
    through which it could invent a replacement level."""
    llm = _PMLLM(
        PortfolioDecision(
            rating=rating, disposition="KEEP", executive_summary="summary", investment_thesis="thesis",
        )
    )
    result = create_portfolio_manager(llm)(_state())
    assert f"**Rating**: {rating.value}" in result["final_trade_decision"]
    assert set(PortfolioDecision.model_fields) & {"entry_price", "stop_loss", "take_profit"} == set()


@pytest.mark.unit
def test_portfolio_manager_prompt_says_to_preserve_traders_levels_when_no_supported_change_exists():
    llm = _PMLLM(PortfolioDecision(
        rating=PortfolioRating.HOLD, disposition="DEFER", executive_summary="x", investment_thesis="y",
    ))
    create_portfolio_manager(llm)(_state())
    prompt = llm.prompts[0]
    assert "preserve the trader's existing levels" in prompt.lower()
