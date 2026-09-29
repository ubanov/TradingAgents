from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    report_or_absent,
)
from tradingagents.prompts.loader import render_agent_prompt

from .review_outcomes import merge_review_outcomes, review_guidance


def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")
        is_initial = not investment_debate_state.get("bear_initial")
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
                "researchers/bear_initial.txt", **prompt_values
            )
        else:
            review_round = investment_debate_state.get("debate_round", 0) + 1
            prompt = render_agent_prompt(
                "researchers/bear.txt",
                **prompt_values,
                review_round=review_round,
                own_previous_response=investment_debate_state.get(
                    "current_bear_response", investment_debate_state.get("bear_initial", "")
                ),
                opponent_previous_response=investment_debate_state.get(
                    "current_bull_response", investment_debate_state.get("bull_initial", "")
                ),
                review_outcomes=investment_debate_state.get("review_outcomes", "")
                or "No classified outcomes from prior rounds.",
                review_guidance=review_guidance(review_round),
            )
        prompt += get_language_instruction()

        response = llm.invoke(prompt)

        if is_initial:
            argument = f"Bear Analyst (Initial): {response.content}"
        else:
            argument = f"Bear Analyst (Review {review_round}): {response.content}"

        new_investment_debate_state = {
            **investment_debate_state,
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "current_response": argument,
            "count": investment_debate_state.get("count", 0) + 1,
        }
        if is_initial:
            new_investment_debate_state["bear_initial"] = argument
            new_investment_debate_state["current_bear_response"] = argument
        else:
            pending_bull_rebuttal = investment_debate_state.get(
                "pending_bull_rebuttal", ""
            )
            completed_round = pending_bull_rebuttal + "\n" + argument
            new_investment_debate_state.update(
                {
                    "rebuttal_history": investment_debate_state.get(
                        "rebuttal_history", ""
                    )
                    + "\n"
                    + completed_round,
                    "review_outcomes": merge_review_outcomes(
                        investment_debate_state.get("review_outcomes", ""),
                        pending_bull_rebuttal,
                        argument,
                    ),
                    "pending_bull_rebuttal": "",
                    "current_bull_response": pending_bull_rebuttal,
                    "current_bear_response": argument,
                    "bear_rebuttal_count": investment_debate_state.get(
                        "bear_rebuttal_count", 0
                    )
                    + 1,
                    "debate_round": investment_debate_state.get("debate_round", 0) + 1,
                }
            )

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
