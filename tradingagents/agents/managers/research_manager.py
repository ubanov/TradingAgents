"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.schemas import ResearchPlan, render_research_plan
from tradingagents.agents.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.prompts.loader import render_agent_prompt


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)
        investment_debate_state = state["investment_debate_state"]
        bull_initial = investment_debate_state.get("bull_initial") or investment_debate_state.get(
            "bull_history", ""
        )
        bear_initial = investment_debate_state.get("bear_initial") or investment_debate_state.get(
            "bear_history", ""
        )

        # The prompt states: conflict alone is not a reason to Hold.
        prompt = render_agent_prompt(
            "managers/research_manager.txt",
            instrument_context=instrument_context,
            bull_initial=bull_initial,
            bear_initial=bear_initial,
            review_outcomes=investment_debate_state.get("review_outcomes", "")
            or "No classified review outcomes were produced.",
            final_bull_response=investment_debate_state.get("current_bull_response")
            or bull_initial,
            final_bear_response=investment_debate_state.get("current_bear_response")
            or bear_initial,
            NO_EXTERNAL_TOOLS=NO_EXTERNAL_TOOLS,
        ) + get_language_instruction()

        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_research_plan,
            "Research Manager",
        )

        new_investment_debate_state = {
            **investment_debate_state,
            "judge_decision": investment_plan,
            "current_response": investment_plan,
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
        }

    return research_manager_node
