"""Shared structured-output flow for the Risk Management debators.

Mirrors ``researchers/thesis_flow.py``'s pattern: a small structured signal
(``risk_level``) rides alongside the free-form debate argument, with a
graceful fallback to plain text when the provider does not support
structured output -- the same degrade path already proven for the Trader,
Research Manager, and Portfolio Manager.
"""

from __future__ import annotations

import logging

from tradingagents.agents.schemas import RiskStanceAssessment, render_risk_argument

logger = logging.getLogger(__name__)


def invoke_risk_stance(structured_llm, plain_llm, prompt, agent_name: str):
    """Return ``(argument_text, risk_level_or_None)``."""
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            if result is None:
                raise ValueError("structured output returned no parsed result")
            if not isinstance(result, RiskStanceAssessment):
                result = RiskStanceAssessment.model_validate(result)
            return render_risk_argument(result), result.risk_level
        except Exception as exc:
            logger.warning(
                "%s: structured risk-stance call failed (%s); falling back to free text",
                agent_name, exc,
            )
    return plain_llm.invoke(prompt).content, None
