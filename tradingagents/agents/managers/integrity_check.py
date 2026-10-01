"""Deterministic, LLM-free integrity check for the Research Manager's output.

The Research Verifier already checks the Bull/Bear research before the
Research Manager sees it, but the manager is itself a free-text-capable LLM
call: nothing stopped it from reintroducing a numeric threshold, sizing rule,
or price level that was never in the verified evidence (observed in real
runs -- a manager inventing a MACD-histogram threshold, a volume threshold, an
allocation percentage, or a yield trigger that no analyst report, verified
thesis, or deterministic calculation ever produced). This module closes that
gap with one cheap, deterministic pass over the manager's rendered output,
run after the Research Manager and before the Trader. No LLM call is made
here, by design (see fork README: "Research Manager integrity check").

The check is intentionally narrow and conservative: false positives (a real,
sourced number wrongly flagged) are worse than false negatives (a low-value
new number that slips through). It:

1. Collects every number already traceable to analyst evidence, a verified
   Bull/Bear trade plan, or a deterministic calculation into one pool.
2. Scans the manager's text for numbers that sit next to operational-trigger
   language ("exceeds", "above", "reduce ... by", etc.) and flags any that
   are not in that pool.
3. Flags a withdrawn trade-plan level resurfacing verbatim.
4. Flags conviction described as a forecast probability.

It does not attempt to parse or verify arbitrary natural-language arithmetic;
see ``ManagerFindingCategory`` for the full, fixed set of checks.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Numeric extraction
# ---------------------------------------------------------------------------

# A number token: optional currency symbol, digits (with optional thousands
# commas and a decimal part), optional %/K/M/B/T suffix. Deliberately simple --
# this is for "does a number like this appear anywhere in the known-good
# evidence", not a general-purpose numeric parser.
_NUMBER_RE = re.compile(
    r"[$€£]?(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+\.\d+|\d+)\s?(%|[KMBTkmbt])?(?![a-zA-Z0-9])"
)

_SUFFIX_MULTIPLIER = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}


def extract_numbers(text: str) -> list[float]:
    """Every number-like token in ``text``, normalised (K/M/B/T expanded)."""
    numbers = []
    for match in _NUMBER_RE.finditer(text or ""):
        raw, suffix = match.group(1), match.group(2)
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if suffix and suffix.lower() in _SUFFIX_MULTIPLIER:
            value *= _SUFFIX_MULTIPLIER[suffix.lower()]
        numbers.append(value)
    return numbers


def _numbers_match(value: float, pool: list[float]) -> bool:
    """Whether ``value`` is traceable to a number already in ``pool``.

    A small tolerance absorbs rounding/formatting differences (the manager
    writing "189.50" for a sourced "189.5"), not genuine new values.
    """
    return any(abs(value - known) <= max(0.01, abs(known) * 0.01) for known in pool)


# ---------------------------------------------------------------------------
# Known-good number pool
# ---------------------------------------------------------------------------


def build_known_number_pool(debate: dict, *reports: str) -> list[float]:
    """Numbers traceable to analyst evidence, verified theses, or deterministic
    calculations -- the only numbers a manager-stated threshold may reuse.
    """
    pool: list[float] = []
    for report in reports:
        pool.extend(extract_numbers(report or ""))

    for side in ("bull", "bear"):
        thesis = debate.get(f"{side}_thesis") or {}
        entry = thesis.get("entry") or {}
        for value in (entry.get("price"), entry.get("low"), entry.get("high"),
                      thesis.get("take_profit"), thesis.get("stop_loss")):
            if value is not None:
                pool.append(float(value))

        metrics = debate.get(f"{side}_trade_metrics") or {}
        for value in metrics.values():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                pool.append(float(value))

    return pool


# ---------------------------------------------------------------------------
# Finding categories and result
# ---------------------------------------------------------------------------


class ManagerCheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"


class ManagerFindingCategory(str, Enum):
    NEW_UNSUPPORTED_THRESHOLD = "NEW_UNSUPPORTED_THRESHOLD"
    NEW_UNSUPPORTED_LEVEL = "NEW_UNSUPPORTED_LEVEL"
    UNSUPPORTED_SIZING_RULE = "UNSUPPORTED_SIZING_RULE"
    ARITHMETIC_ERROR = "ARITHMETIC_ERROR"
    CONVICTION_AS_PROBABILITY = "CONVICTION_AS_PROBABILITY"
    WITHDRAWN_VALUE_REUSED = "WITHDRAWN_VALUE_REUSED"
    INTERNAL_INCONSISTENCY = "INTERNAL_INCONSISTENCY"


@dataclass(frozen=True)
class ManagerFinding:
    category: str
    detail: str


@dataclass(frozen=True)
class ManagerIntegrityResult:
    status: str
    findings: list[ManagerFinding] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"status": self.status, "findings": [asdict(f) for f in self.findings]}


# ---------------------------------------------------------------------------
# Sentence-level scanning
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;\n])\s+")

# Operational-trigger language: a number next to one of these is a candidate
# decision rule, not narrative prose. Proximity (same sentence) is the whole
# test -- deliberately not full NLP, per the "false positives are worse"
# principle: a correctly-sourced number near one of these words still passes,
# since the number itself is checked against the evidence pool below.
_THRESHOLD_TRIGGERS = (
    "exceed", "exceeds", "exceeding",
    "above", "below", "over ", "under ",
    "at least", "at most", "more than", "less than", "greater than", "fewer than",
    "reduce", "increase", "cut ", "trim ",
)

_SIZING_WORDS = (
    "allocat", "exposure", "position siz", "portfolio weight",
    "of portfolio", "of the portfolio", "of capital",
)

_LEVEL_WORDS = (
    "entry", "target", "stop", "take profit", "take-profit",
    "invalidation", "trigger level", "price level",
)

_PROBABILITY_WORDS = ("probability", "chance of", "% chance", "likelihood", "odds of")


def _split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT_RE.split(text or "") if s.strip()]


def _excerpt(sentence: str, limit: int = 160) -> str:
    sentence = sentence.strip()
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


def _classify_threshold(sentence_lower: str) -> ManagerFindingCategory:
    if "%" in sentence_lower and any(word in sentence_lower for word in _SIZING_WORDS):
        return ManagerFindingCategory.UNSUPPORTED_SIZING_RULE
    if any(word in sentence_lower for word in _LEVEL_WORDS):
        return ManagerFindingCategory.NEW_UNSUPPORTED_LEVEL
    return ManagerFindingCategory.NEW_UNSUPPORTED_THRESHOLD


def _find_unsupported_thresholds(text: str, pool: list[float]) -> list[ManagerFinding]:
    findings = []
    for sentence in _split_sentences(text):
        lower = sentence.lower()
        if not any(trigger in lower for trigger in _THRESHOLD_TRIGGERS):
            continue
        for value in extract_numbers(sentence):
            if _numbers_match(value, pool):
                continue
            category = _classify_threshold(lower)
            findings.append(ManagerFinding(category.value, _excerpt(sentence)))
    return findings


def _find_conviction_as_probability(text: str) -> list[ManagerFinding]:
    findings = []
    for sentence in _split_sentences(text):
        lower = sentence.lower()
        if "conviction" in lower and any(word in lower for word in _PROBABILITY_WORDS):
            findings.append(
                ManagerFinding(
                    ManagerFindingCategory.CONVICTION_AS_PROBABILITY.value, _excerpt(sentence)
                )
            )
    return findings


def _find_withdrawn_values_reused(text: str, withdrawn_values: list[float]) -> list[ManagerFinding]:
    """``withdrawn_values`` covers both a true WITHDRAW and a value a REVISE
    genuinely replaced (see ``thesis_flow._retired_value_for``) -- either way,
    it must never resurface as if it were still an active, verified level.
    """
    if not withdrawn_values:
        return []
    findings = []
    for sentence in _split_sentences(text):
        numbers = extract_numbers(sentence)
        for withdrawn in withdrawn_values:
            if any(abs(n - withdrawn) <= max(0.01, abs(withdrawn) * 0.001) for n in numbers):
                findings.append(
                    ManagerFinding(
                        ManagerFindingCategory.WITHDRAWN_VALUE_REUSED.value,
                        f"{_excerpt(sentence)} (level {withdrawn} was withdrawn during review)",
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def render_integrity_notice_for_trader(status: str, findings: list[dict]) -> str:
    """A notice for the Trader's prompt when the manager's output carried
    unsupported quantitative claims -- never silently rewritten (meaning could
    change), always explicitly flagged as unsupported instead.
    """
    if status != ManagerCheckStatus.WARN.value or not findings:
        return ""
    lines = [
        "The following claims in the investment plan above could not be traced to the "
        "supplied evidence, a verified research level, or a deterministic calculation. "
        "Treat them as UNSUPPORTED: do not act on these specific thresholds as if they "
        "were verified input.",
    ]
    lines += [f"- [{finding['category']}] {finding['detail']}" for finding in findings]
    return "\n".join(lines)


def render_manager_integrity_report(status: str, findings: list[dict]) -> str:
    """Compact report-section rendering: a one-line status on PASS, the
    status plus each finding's category and excerpt on WARN."""
    if not status:
        return ""
    lines = [f"Status: {status}"]
    if findings:
        lines += [""] + [f"- {f['category']}: {f['detail']}" for f in findings]
    return "\n".join(lines)


def check_manager_integrity(
    manager_output_text: str,
    debate: dict,
    *reports: str,
) -> ManagerIntegrityResult:
    """Run every deterministic check against the Research Manager's rendered
    output and return one PASS/WARN result. Never raises; never calls an LLM.
    """
    text = manager_output_text or ""
    pool = build_known_number_pool(debate, *reports)

    findings: list[ManagerFinding] = []
    findings += _find_unsupported_thresholds(text, pool)
    findings += _find_conviction_as_probability(text)
    findings += _find_withdrawn_values_reused(text, debate.get("withdrawn_values") or [])

    status = ManagerCheckStatus.WARN if findings else ManagerCheckStatus.PASS
    return ManagerIntegrityResult(status=status.value, findings=findings)
