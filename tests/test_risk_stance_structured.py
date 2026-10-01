"""Structured output for the Risk Management debators (Aggressive/Conservative/
Neutral), mirroring the Trader/Research pattern: a small risk_level signal
rides alongside the free-form debate argument, with a free-text fallback."""

from __future__ import annotations

import pytest

from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.schemas import RiskStanceAssessment
from tradingagents.graph.propagation import Propagator


class _StructuredLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.outputs.pop(0)


def _state():
    state = Propagator().create_initial_state("NVDA", "2026-09-01")
    state.update(
        {
            "market_report": "MARKET",
            "sentiment_report": "SENTIMENT",
            "news_report": "NEWS",
            "fundamentals_report": "FUNDAMENTALS",
            "trader_investment_plan": "Buy, 5% allocation.",
        }
    )
    return state


def _apply(state, node):
    state["risk_debate_state"] = node(state)["risk_debate_state"]


@pytest.mark.unit
def test_aggressive_debator_structured_turn_sets_risk_level_and_argument():
    state = _state()
    llm = _StructuredLLM(
        [RiskStanceAssessment(risk_level="LOW", argument="This plan is too timid.")]
    )
    _apply(state, create_aggressive_debator(llm))

    debate = state["risk_debate_state"]
    assert debate["aggressive_risk_level"] == "LOW"
    assert "This plan is too timid." in debate["current_aggressive_response"]
    assert debate["current_aggressive_response"].startswith("Aggressive Analyst:")


@pytest.mark.unit
def test_conservative_and_neutral_each_track_their_own_risk_level():
    state = _state()
    conservative_llm = _StructuredLLM(
        [RiskStanceAssessment(risk_level="HIGH", argument="Too much exposure.")]
    )
    _apply(state, create_conservative_debator(conservative_llm))
    assert state["risk_debate_state"]["conservative_risk_level"] == "HIGH"
    assert state["risk_debate_state"]["aggressive_risk_level"] == ""

    neutral_llm = _StructuredLLM(
        [RiskStanceAssessment(risk_level="MEDIUM", argument="A balanced view.")]
    )
    _apply(state, create_neutral_debator(neutral_llm))
    assert state["risk_debate_state"]["neutral_risk_level"] == "MEDIUM"
    # Earlier speakers' levels survive an unrelated turn.
    assert state["risk_debate_state"]["conservative_risk_level"] == "HIGH"


@pytest.mark.unit
def test_risk_level_persists_across_turns_until_that_debator_speaks_again():
    state = _state()
    llm = _StructuredLLM(
        [
            RiskStanceAssessment(risk_level="LOW", argument="Round 1."),
            RiskStanceAssessment(risk_level="MEDIUM", argument="Round 2."),
        ]
    )
    aggressive = create_aggressive_debator(llm)
    _apply(state, aggressive)
    assert state["risk_debate_state"]["aggressive_risk_level"] == "LOW"
    _apply(state, aggressive)
    assert state["risk_debate_state"]["aggressive_risk_level"] == "MEDIUM"


@pytest.mark.unit
def test_portfolio_manager_receives_the_latest_risk_stance_summary():
    from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
    from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating

    class _PMLLM:
        def __init__(self):
            self.prompts = []

        def with_structured_output(self, _schema):
            return self

        def invoke(self, prompt):
            self.prompts.append(prompt)
            return PortfolioDecision(
                rating=PortfolioRating.HOLD,
                executive_summary="Hold for now.",
                investment_thesis="Balanced risk views.",
            )

    state = _state()
    state["investment_plan"] = "Buy plan"
    state["risk_debate_state"].update(
        {
            "aggressive_risk_level": "LOW",
            "conservative_risk_level": "HIGH",
            "neutral_risk_level": "MEDIUM",
        }
    )
    llm = _PMLLM()
    create_portfolio_manager(llm)(state)
    prompt = llm.prompts[0]
    assert "Aggressive: LOW" in prompt
    assert "Conservative: HIGH" in prompt
    assert "Neutral: MEDIUM" in prompt


@pytest.mark.unit
def test_portfolio_manager_output_preserves_risk_level_fields():
    """Regression: Portfolio Manager used to build its returned
    risk_debate_state by listing every key explicitly, silently dropping the
    three risk_level fields (and anything else added later) from the final
    saved state/report."""
    from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
    from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating

    class _PMLLM:
        def with_structured_output(self, _schema):
            return self

        def invoke(self, prompt):
            return PortfolioDecision(
                rating=PortfolioRating.HOLD, executive_summary="x", investment_thesis="y"
            )

    state = _state()
    state["investment_plan"] = "Buy plan"
    state["risk_debate_state"].update(
        {
            "aggressive_risk_level": "LOW",
            "conservative_risk_level": "HIGH",
            "neutral_risk_level": "MEDIUM",
        }
    )
    result = create_portfolio_manager(_PMLLM())(state)
    new_risk_state = result["risk_debate_state"]
    assert new_risk_state["aggressive_risk_level"] == "LOW"
    assert new_risk_state["conservative_risk_level"] == "HIGH"
    assert new_risk_state["neutral_risk_level"] == "MEDIUM"
    assert new_risk_state["judge_decision"]  # still set correctly


@pytest.mark.unit
def test_falls_back_to_freetext_when_structured_output_unsupported():
    from types import SimpleNamespace

    class _PlainLLM:
        def invoke(self, prompt):
            return SimpleNamespace(content="plain prose argument")

    state = _state()
    _apply(state, create_aggressive_debator(_PlainLLM()))
    debate = state["risk_debate_state"]
    assert "plain prose argument" in debate["current_aggressive_response"]
    assert debate["aggressive_risk_level"] == ""  # no signal available, not invented
