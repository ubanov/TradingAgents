"""Compact cross-review outcomes shared by the Bull and Bear researchers."""

from __future__ import annotations

import re

from tradingagents.prompts.loader import load_prompt

_OUTCOME_LINE = re.compile(
    r"(?:^|\s)(?:[-*#>]\s*)?(?:\d+[.)]\s*)?"
    r"(ACCEPTED|REJECTED|UNRESOLVED)\b\s*:?[ \t]*(.*)$",
    re.IGNORECASE,
)


def review_guidance(review_round: int) -> str:
    path = (
        "researchers/review_first.txt"
        if review_round == 1
        else "researchers/review_followup.txt"
    )
    return load_prompt(path).strip()


def extract_review_outcomes(response: str) -> list[str]:
    """Return standardized one-line classifications from a review response."""
    outcomes = []
    pending_label = None
    for raw_line in response.splitlines():
        match = _OUTCOME_LINE.search(raw_line)
        if match:
            label, detail = match.groups()
            pending_label = label.upper()
            if detail.strip():
                outcomes.append(f"{pending_label}: {detail.strip()}")
                pending_label = None
            continue
        stripped = raw_line.strip().lstrip("-* ")
        if pending_label and stripped:
            outcomes.append(f"{pending_label}: {stripped}")
            pending_label = None
    return outcomes


def merge_review_outcomes(existing: str, *responses: str) -> str:
    """Append newly classified outcomes while preserving first-seen order."""
    outcomes = [line for line in existing.splitlines() if line.strip()]
    seen = set(outcomes)
    for response in responses:
        for outcome in extract_review_outcomes(response):
            if outcome not in seen:
                outcomes.append(outcome)
                seen.add(outcome)
    return "\n".join(outcomes)
