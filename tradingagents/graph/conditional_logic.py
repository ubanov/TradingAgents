from tradingagents.agents.researchers.verification import MAX_REPAIR_ROUNDS
from tradingagents.agents.state import AgentState


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    def should_continue_debate(self, state: AgentState) -> str:
        """Route independent theses, then paired cross-review rounds."""
        debate = state["investment_debate_state"]
        if not debate.get("bull_initial"):
            return "Bull Researcher"
        if not debate.get("bear_initial"):
            return "Bear Researcher"
        if debate.get("debate_round", 0) >= self.max_debate_rounds:
            return "Research Verifier"
        if not debate.get("pending_bull_rebuttal"):
            return "Bull Researcher"
        else:
            return "Bear Researcher"

    def should_continue_verification(self, state: AgentState) -> str:
        """Allow one repair round after a first-pass verification failure."""
        debate = state["investment_debate_state"]
        if (
            debate.get("verification_status") == "FAIL"
            and debate.get("repair_rounds", 0) < MAX_REPAIR_ROUNDS
        ):
            return "Bull Repair"
        return "Research Manager"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        if (
            state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds
        ):  # 3 rounds of back-and-forth between 3 agents
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
