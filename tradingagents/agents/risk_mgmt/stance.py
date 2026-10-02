"""Shared structured-output flow for the Risk Management reviewers.

Mirrors ``researchers/thesis_flow.py``'s pattern: a structured assessment
rides alongside a rendered markdown block, with a graceful fallback to plain
text when the provider does not support structured output -- the same
degrade path already proven for the Trader, Research Manager, Portfolio
Manager, and Bull/Bear researchers.
"""

from __future__ import annotations

import logging

from tradingagents.agents.fallback_log import warn_fallback
from tradingagents.agents.schemas import RiskStanceAssessment, render_risk_assessment

logger = logging.getLogger(__name__)


def invoke_risk_assessment(structured_llm, plain_llm, prompt, agent_name: str):
    """Return ``(rendered_text, risk_level_or_None, disposition_or_None, assessment_dict_or_None)``.

    On free-text fallback, only ``rendered_text`` is available: the caller
    must not invent a risk_level/disposition/assessment that was never
    produced.
    """
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            if result is None:
                raise ValueError("structured output returned no parsed result")
            if not isinstance(result, RiskStanceAssessment):
                result = RiskStanceAssessment.model_validate(result)
            return (
                render_risk_assessment(result),
                result.risk_level,
                result.disposition.value,
                result.model_dump(mode="json"),
            )
        except Exception as exc:
            warn_fallback(
                logger,
                f"{agent_name}: structured risk assessment unavailable; "
                "continuing with free-text fallback.",
                detail=str(exc),
            )
    return plain_llm.invoke(prompt).content, None, None, None
