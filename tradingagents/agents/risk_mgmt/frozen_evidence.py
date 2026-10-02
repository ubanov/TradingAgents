"""The frozen evidence set Risk reviewers assess against.

Risk evaluates the Trader's already-researched plan; it does not go back to
the data or redo the research. Everything a Risk reviewer may cite is
collected here, once, at the start of the Risk phase, from material that
already existed before Risk started: analyst reports, the verified Bull/Bear
structured state, the Research Verifier's result, the Research Manager's
output (with its integrity caveat), deterministic setup tags, deterministic
trade metrics, and the Trader's plan. Independent assessments and the single
cross-review round must not introduce anything beyond this set (see fork
README: "Risk as assessment, not evidence generation").
"""

from __future__ import annotations

from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_portfolio_context_from_state,
)
from tradingagents.agents.managers.integrity_check import render_integrity_notice_for_trader
from tradingagents.agents.researchers.setup_tags import render_setup_tags
from tradingagents.agents.researchers.trade_metrics import (
    render_trade_metrics,
    trade_metrics_from_dict,
)
from tradingagents.agents.researchers.verification import render_verification_history


def render_frozen_evidence(state: dict) -> str:
    debate = state.get("investment_debate_state") or {}

    sections = [
        get_instrument_context_from_state(state),
        get_portfolio_context_from_state(state) or "Portfolio context: not supplied.",
        "Analyst Reports:",
        f"Market: {state.get('market_report') or 'not available'}",
        f"Sentiment: {state.get('sentiment_report') or 'not available'}",
        f"News: {state.get('news_report') or 'not available'}",
        f"Fundamentals: {state.get('fundamentals_report') or 'not available'}",
    ]

    sections.append(
        "Research Verification (compact): "
        + render_verification_history(
            debate.get("verification_history", []),
            repaired_agents=debate.get("repaired_agents", []),
            include_details=False,
        )
    )

    manager_plan = state.get("investment_plan") or "not available"
    integrity_notice = render_integrity_notice_for_trader(
        debate.get("manager_integrity_status", ""), debate.get("manager_integrity_findings", [])
    )
    sections.append(f"Research Manager Plan:\n{manager_plan}")
    if integrity_notice:
        sections.append(f"Research Manager integrity caveat:\n{integrity_notice}")

    sections.append(
        "Shared Objective Setup Tags:\n" + render_setup_tags(debate.get("setup_tags") or {})
    )

    data_gaps: list[str] = []
    for side in ("bull", "bear"):
        thesis = debate.get(f"{side}_thesis") or {}
        metrics = trade_metrics_from_dict(debate.get(f"{side}_trade_metrics"))
        sections.append(
            f"{side.title()} Deterministic Trade Metrics (computed in code):\n"
            + render_trade_metrics(metrics)
        )
        data_gaps.extend(f"[{side}] {gap}" for gap in (thesis.get("data_gaps") or []))

    sections.append(
        "Known Data Gaps:\n" + ("\n".join(f"- {gap}" for gap in data_gaps) if data_gaps else "none recorded")
    )

    sections.append(f"Trader's Plan:\n{state.get('trader_investment_plan') or 'not available'}")

    return "\n\n".join(sections)
