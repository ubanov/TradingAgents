from tradingagents.agents.researchers.verification import MAX_REPAIR_ROUNDS
from tradingagents.agents.state import AgentState

# Risk is a fixed two-phase structure -- three independent assessments, then
# exactly one cross-review round -- not a round count scaled by research
# depth (see fork README: "Risk as independent assessment + one cross-
# review"). Three reviewers x two phases = six turns, always.
RISK_ANALYSIS_TOTAL_TURNS = 6


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters.

        ``max_risk_discuss_rounds`` is accepted for backward compatibility
        (config plumbing, CLI depth mapping) but no longer scales the Risk
        phase, which is now a fixed independent-assessment-then-cross-review
        structure regardless of research depth.
        """
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
        """Route independent assessments, then exactly one cross-review round.

        Phase-keyed like ``should_continue_debate``, not a turn counter: each
        reviewer's own completion marker (``{role}_initial`` / ``{role}_review``)
        decides the next node, so a free-text-fallback turn (whose structured
        assessment is empty) still counts as complete.
        """
        risk = state["risk_debate_state"]
        if not risk.get("aggressive_initial"):
            return "Aggressive Analyst"
        if not risk.get("conservative_initial"):
            return "Conservative Analyst"
        if not risk.get("neutral_initial"):
            return "Neutral Analyst"
        if not risk.get("aggressive_review"):
            return "Aggressive Analyst"
        if not risk.get("conservative_review"):
            return "Conservative Analyst"
        if not risk.get("neutral_review"):
            return "Neutral Analyst"
        return "Portfolio Manager"
