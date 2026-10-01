"""Shared structured-output flow for the Bull/Bear initial thesis and reviews.

Both researchers follow the same two-schema pattern (see fork README:
"Structured trade hypotheses", "Review data restrictions"):

- Initial phase: one ``InitialResearchThesis`` call, rendered to the markdown
  prose the rest of the system already treats the debate history as.
- Review phase: one ``ResearchReviewOutcome`` call per round, applied to the
  side's tracked trade-plan levels via KEEP/REVISE/WITHDRAW.

Structured output is optional and falls back to free text exactly like the
Trader/Portfolio Manager/Research Manager (``agents/structured.py``): a
provider or test double without ``with_structured_output`` degrades to plain
``llm.invoke(prompt).content`` with no thesis/review dict, so the trade-plan
tracking and deterministic metrics below simply do not populate for that
side rather than breaking the debate.
"""

from __future__ import annotations

import logging

from tradingagents.agents.researchers.trade_metrics import (
    compute_trade_metrics,
    entry_reference as _entry_reference,
)
from tradingagents.agents.schemas import (
    InitialResearchThesis,
    ResearchReviewOutcome,
    render_initial_thesis,
    render_review_outcome,
)

logger = logging.getLogger(__name__)


def invoke_initial_thesis(structured_llm, plain_llm, prompt, agent_name: str):
    """Return ``(rendered_markdown, thesis_dict_or_None)``."""
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            if result is None:
                raise ValueError("structured output returned no parsed result")
            if not isinstance(result, InitialResearchThesis):
                result = InitialResearchThesis.model_validate(result)
            return render_initial_thesis(result), result.model_dump(mode="json")
        except Exception as exc:
            logger.warning(
                "%s: structured initial-thesis call failed (%s); falling back to free text",
                agent_name, exc,
            )
    return plain_llm.invoke(prompt).content, None


def invoke_review(structured_llm, plain_llm, prompt, agent_name: str):
    """Return ``(rendered_markdown, review_dict_or_None)``."""
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            if result is None:
                raise ValueError("structured output returned no parsed result")
            if not isinstance(result, ResearchReviewOutcome):
                result = ResearchReviewOutcome.model_validate(result)
            return render_review_outcome(result), result.model_dump(mode="json")
        except Exception as exc:
            logger.warning(
                "%s: structured review call failed (%s); falling back to free text",
                agent_name, exc,
            )
    return plain_llm.invoke(prompt).content, None


def _entry_field(action: str, old_entry: dict, new_value) -> dict:
    if action == "WITHDRAW":
        return {"type": old_entry.get("type", "point"), "price": None, "low": None, "high": None}
    if action == "REVISE" and new_value is not None:
        return {"type": "point", "price": new_value, "low": None, "high": None}
    return dict(old_entry)


def _scalar_field(action: str, old_value, new_value):
    if action == "WITHDRAW":
        return None
    if action == "REVISE" and new_value is not None:
        return new_value
    return old_value


def _retired_value_for(action: str, old_value, new_value) -> float | None:
    """The value that stops being active provenance after this change, or
    ``None`` if nothing was retired.

    WITHDRAW always retires the old value (if there was one). REVISE retires
    it only when the new value genuinely differs -- a REVISE that merely
    restates the same number isn't really replacing anything, and treating it
    as retired would flag the still-current number as reused the next time it
    appears. KEEP never retires. This is the one invariant both normal review
    rounds and repair rely on: a value that was REVISED or WITHDRAWN must
    never later be treated as active verified provenance (see
    ``managers/integrity_check.py``, WITHDRAWN_VALUE_REUSED).
    """
    if old_value is None:
        return None
    if action == "WITHDRAW":
        return old_value
    if action == "REVISE" and new_value is not None and new_value != old_value:
        return old_value
    return None


def apply_trade_plan_changes(thesis: dict, review: dict) -> tuple[dict, list[float]]:
    """Apply a review's KEEP/REVISE/WITHDRAW actions to a tracked thesis dict.

    Operates on the plain-dict state representation (not the pydantic model)
    so it works the same whether the thesis was set this round or an earlier
    one (a normal review or a repair -- see ``researchers/research_repair.py``,
    which applies this identically). From the first review onward, entry is
    tracked as a flattened point reference (its range midpoint, if the
    initial thesis was a range) since a review only ever revises a single
    number in practice.

    Returns ``(updated_thesis, newly_retired_values)``: the second element is
    the actual pre-change value of any field just WITHDRAWN or genuinely
    REVISED (not the review's self-reported ``old``, which may not match) --
    stored in debate state as ``withdrawn_values`` (the name predates REVISE
    also retiring a value; broadened rather than renamed to keep the diff
    small, see fork README).
    """
    updated = dict(thesis)
    retired: list[float] = []
    changes = review.get("trade_plan_changes") or {}

    entry_change = changes.get("entry") or {}
    old_entry = thesis.get("entry") or {}
    old_entry_ref = _entry_reference(old_entry.get("price"), old_entry.get("low"), old_entry.get("high"))
    retired_entry = _retired_value_for(
        entry_change.get("action", "KEEP"), old_entry_ref, entry_change.get("new")
    )
    if retired_entry is not None:
        retired.append(retired_entry)
    updated["entry"] = _entry_field(
        entry_change.get("action", "KEEP"), old_entry, entry_change.get("new")
    )

    tp_change = changes.get("take_profit") or {}
    retired_tp = _retired_value_for(
        tp_change.get("action", "KEEP"), thesis.get("take_profit"), tp_change.get("new")
    )
    if retired_tp is not None:
        retired.append(retired_tp)
    updated["take_profit"] = _scalar_field(
        tp_change.get("action", "KEEP"), thesis.get("take_profit"), tp_change.get("new")
    )

    sl_change = changes.get("stop_loss") or {}
    retired_sl = _retired_value_for(
        sl_change.get("action", "KEEP"), thesis.get("stop_loss"), sl_change.get("new")
    )
    if retired_sl is not None:
        retired.append(retired_sl)
    updated["stop_loss"] = _scalar_field(
        sl_change.get("action", "KEEP"), thesis.get("stop_loss"), sl_change.get("new")
    )

    return updated, retired


def recompute_trade_metrics(thesis: dict, atr: float | None) -> dict:
    """Deterministic trade metrics for a tracked thesis dict, as a plain dict."""
    entry = thesis.get("entry") or {}
    metrics = compute_trade_metrics(
        entry_price=entry.get("price") if entry.get("type") == "point" else None,
        entry_low=entry.get("low") if entry.get("type") == "range" else None,
        entry_high=entry.get("high") if entry.get("type") == "range" else None,
        take_profit=thesis.get("take_profit"),
        stop_loss=thesis.get("stop_loss"),
        atr=atr,
    )
    return {
        "entry_reference": metrics.entry_reference,
        "risk": metrics.risk,
        "reward": metrics.reward,
        "risk_pct": metrics.risk_pct,
        "reward_pct": metrics.reward_pct,
        "reward_risk": metrics.reward_risk,
        "stop_atr": metrics.stop_atr,
        "target_atr": metrics.target_atr,
    }
