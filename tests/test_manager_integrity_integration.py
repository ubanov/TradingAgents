"""Research Manager node wiring for the deterministic post-manager integrity
check: runs after every manager call (structured or free-text fallback),
stores PASS/WARN + findings in debate state, never calls an LLM itself."""

from __future__ import annotations

import pytest

from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.schemas import PortfolioRating, ResearchPlan
from tradingagents.graph.propagation import Propagator


def _state(**report_overrides):
    state = Propagator().create_initial_state("NVDA", "2026-09-01")
    state.update(
        {
            "instrument_context": "INSTRUMENT",
            "market_report": "RSI is 65.3.",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
        }
    )
    state.update(report_overrides)
    return state


class _StructuredManagerLLM:
    def __init__(self, plan: ResearchPlan):
        self.plan = plan
        self.prompts = []

    def with_structured_output(self, _schema):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.plan


@pytest.mark.unit
def test_structured_manager_output_passes_when_claims_are_supported():
    plan = ResearchPlan(
        recommendation=PortfolioRating.BUY,
        rationale="RSI exceeds 65.3, confirming momentum.",
        strategic_actions="Enter now.",
    )
    state = _state()
    result = create_research_manager(_StructuredManagerLLM(plan))(state)
    debate = result["investment_debate_state"]
    assert debate["manager_integrity_status"] == "PASS"
    assert debate["manager_integrity_findings"] == []


@pytest.mark.unit
def test_structured_manager_output_warns_on_an_invented_threshold():
    plan = ResearchPlan(
        recommendation=PortfolioRating.BUY,
        rationale="Solid setup.",
        strategic_actions="Only act once the MACD histogram exceeds +0.5.",
    )
    state = _state()
    result = create_research_manager(_StructuredManagerLLM(plan))(state)
    debate = result["investment_debate_state"]
    assert debate["manager_integrity_status"] == "WARN"
    assert len(debate["manager_integrity_findings"]) == 1
    assert debate["manager_integrity_findings"][0]["category"] == "NEW_UNSUPPORTED_THRESHOLD"


@pytest.mark.unit
def test_check_still_runs_conservatively_when_manager_falls_back_to_free_text():
    from types import SimpleNamespace

    class _PlainLLM:
        def invoke(self, prompt):
            return SimpleNamespace(
                content="**Recommendation**: Buy\n\n**Rationale**: Reduce exposure by 25% now.\n\n"
                "**Strategic Actions**: Trim the position."
            )

    state = _state()
    result = create_research_manager(_PlainLLM())(state)
    debate = result["investment_debate_state"]
    assert debate["manager_integrity_status"] == "WARN"
    assert debate["manager_integrity_findings"][0]["category"] == "UNSUPPORTED_SIZING_RULE"


@pytest.mark.unit
def test_pass_status_produces_no_findings_with_plain_vanilla_output():
    from types import SimpleNamespace

    class _PlainLLM:
        def invoke(self, prompt):
            return SimpleNamespace(
                content="**Recommendation**: Hold\n\n**Rationale**: Evidence is balanced.\n\n"
                "**Strategic Actions**: Maintain the position."
            )

    state = _state()
    result = create_research_manager(_PlainLLM())(state)
    debate = result["investment_debate_state"]
    assert debate["manager_integrity_status"] == "PASS"
    assert debate["manager_integrity_findings"] == []
