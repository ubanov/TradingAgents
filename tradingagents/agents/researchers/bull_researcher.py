from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    report_or_absent,
)
from tradingagents.prompts.loader import render_agent_prompt

from .review_outcomes import review_guidance


def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")
        is_initial = not investment_debate_state.get("bull_initial")
        market_research_report = report_or_absent(state["market_report"], "market")
        sentiment_report = report_or_absent(state["sentiment_report"], "sentiment")
        news_report = report_or_absent(state["news_report"], "news")
        fundamentals_report = report_or_absent(state["fundamentals_report"], "fundamentals")
        instrument_context = get_instrument_context_from_state(state)
        asset_type = state.get("asset_type", "stock")
        target_label = "stock" if asset_type == "stock" else "asset"
        fundamentals_label = (
            "Company fundamentals report"
            if asset_type == "stock"
            else "Asset fundamentals report (may be unavailable for crypto)"
        )

        prompt_values = {
            "target_label": target_label,
            "instrument_context": instrument_context,
            "market_research_report": market_research_report,
            "sentiment_report": sentiment_report,
            "news_report": news_report,
            "fundamentals_label": fundamentals_label,
            "fundamentals_report": fundamentals_report,
        }
        if is_initial:
            prompt = render_agent_prompt(
                "researchers/bull_initial.txt", **prompt_values
            )
        else:
            review_round = investment_debate_state.get("debate_round", 0) + 1
            prompt = render_agent_prompt(
                "researchers/bull.txt",
                **prompt_values,
                review_round=review_round,
                own_previous_response=investment_debate_state.get(
                    "current_bull_response", investment_debate_state.get("bull_initial", "")
                ),
                opponent_previous_response=investment_debate_state.get(
                    "current_bear_response", investment_debate_state.get("bear_initial", "")
                ),
                review_outcomes=investment_debate_state.get("review_outcomes", "")
                or "No classified outcomes from prior rounds.",
                review_guidance=review_guidance(review_round),
            )
        prompt += get_language_instruction()

        response = llm.invoke(prompt)

        if is_initial:
            argument = f"Bull Analyst (Initial): {response.content}"
        else:
            argument = f"Bull Analyst (Review {review_round}): {response.content}"

        new_investment_debate_state = {
            **investment_debate_state,
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "current_response": argument,
            "count": investment_debate_state.get("count", 0) + 1,
        }
        if is_initial:
            new_investment_debate_state["bull_initial"] = argument
            new_investment_debate_state["current_bull_response"] = argument
        else:
            new_investment_debate_state.update(
                {
                    "pending_bull_rebuttal": argument,
                    "bull_rebuttal_count": investment_debate_state.get(
                        "bull_rebuttal_count", 0
                    )
                    + 1,
                }
            )

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
