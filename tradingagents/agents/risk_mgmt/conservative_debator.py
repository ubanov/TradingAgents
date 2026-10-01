from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_portfolio_context_from_state,
    opponent_argument_or_opening,
    report_or_absent,
)
from tradingagents.agents.risk_mgmt.stance import invoke_risk_stance
from tradingagents.agents.schemas import RiskStanceAssessment
from tradingagents.agents.structured import bind_structured
from tradingagents.prompts.loader import render_agent_prompt


def create_conservative_debator(llm):
    structured_llm = bind_structured(llm, RiskStanceAssessment, "Conservative Analyst")

    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = opponent_argument_or_opening(
            risk_debate_state.get("current_aggressive_response", ""), "aggressive analyst"
        )
        current_neutral_response = opponent_argument_or_opening(
            risk_debate_state.get("current_neutral_response", ""), "neutral analyst"
        )

        market_research_report = report_or_absent(state["market_report"], "market")
        sentiment_report = report_or_absent(state["sentiment_report"], "sentiment")
        news_report = report_or_absent(state["news_report"], "news")
        fundamentals_report = report_or_absent(state["fundamentals_report"], "fundamentals")
        instrument_context = get_instrument_context_from_state(state)
        portfolio_context = get_portfolio_context_from_state(state)

        trader_decision = state["trader_investment_plan"]

        prompt = render_agent_prompt(
            "risk_mgmt/conservative.txt",
            trader_decision=trader_decision,
            instrument_context=instrument_context,
            portfolio_context=portfolio_context,
            market_research_report=market_research_report,
            sentiment_report=sentiment_report,
            news_report=news_report,
            fundamentals_report=fundamentals_report,
            history=history,
            current_aggressive_response=current_aggressive_response,
            current_neutral_response=current_neutral_response,
        ) + get_language_instruction()

        rendered, risk_level = invoke_risk_stance(
            structured_llm, llm, prompt, "Conservative Analyst"
        )

        argument = f"Conservative Analyst: {rendered}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "aggressive_risk_level": risk_debate_state.get("aggressive_risk_level", ""),
            "conservative_risk_level": risk_level
            or risk_debate_state.get("conservative_risk_level", ""),
            "neutral_risk_level": risk_debate_state.get("neutral_risk_level", ""),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
