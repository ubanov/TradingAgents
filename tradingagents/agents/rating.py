"""Shared decision vocabularies and a deterministic heuristic parser.

The same five-tier scale (Buy, Overweight, Hold, Underweight, Sell) is used by:
- The Research Manager (investment plan recommendation)
- The Portfolio Manager (final position decision)
- The signal processor (rating extracted for downstream consumers)
- The memory log (rating tag stored alongside each decision entry)

The Trader's narrower three-tier scale (Buy, Hold, Sell) uses the same
extraction logic (``extract_choice``) with its own label words, so the three
decision-making agents' outputs are parsed consistently instead of each having
its own ad hoc regex (a real inconsistency: the Research Manager's
recommendation and the Trader's action used to be parsed by a much weaker
single-regex matcher in ``cli/headless.py``, while only the Portfolio
Manager's rating got this module's more tolerant multi-tier logic).

Centralising it here avoids drift between those call sites.

``extract_rating``/``extract_choice`` return ``None`` when no decision can be
found, and every caller turns that into ``REVIEW`` (or an equivalent "unparsed"
status) rather than a tradeable position: a decision nobody can read is not a
Hold, and a Hold recorded in its place is quoted back to the next run as a
call that was never made (#1170).
"""

from __future__ import annotations

import re
import unicodedata

# Canonical, ordered 5-tier scale (most bullish to most bearish).
RATINGS_5_TIER: tuple[str, ...] = (
    "Buy", "Overweight", "Hold", "Underweight", "Sell",
)

# Signal emitted when the model's decision has no recognizable rating. It is not
# a tradeable position: it flags output that needs a human/re-run rather than
# silently degrading to Hold. Callers that map the signal onto the 5-tier enum
# (e.g. ``PortfolioRating(signal)``) should guard with ``is_review`` first.
RATING_REVIEW = "REVIEW"

# A line presenting the scale rather than a decision ("Rating Scale: Buy, ...").
_RATING_SCALE_RE = re.compile(r"rating\s*(scale|options|legend)", re.IGNORECASE)


def _label_re(label_words: tuple[str, ...]) -> re.Pattern[str]:
    # Matches "Rating: X" / "Recommendation - X" / "Portfolio Rating -- **X**" --
    # tolerates markdown bold wrappers and any dash or colon a model writes as
    # the separator, and any of the given label words (word boundary, so this
    # also matches "Rating" inside "Portfolio Rating" without a separate rule).
    alternation = "|".join(re.escape(word) for word in label_words)
    dash_class = "[:\\-‐‑‒–—―]"
    return re.compile(
        rf"(?:{alternation})\b[^:\-‐‑‒–—―]*{dash_class}[\s*]*(\w+)",
        re.IGNORECASE,
    )


def extract_choice(
    text: str, choices: tuple[str, ...], label_words: tuple[str, ...]
) -> str | None:
    """Extract one of ``choices`` from free-form prose, or ``None`` if none
    can be reliably identified.

    Three tiers, most to least confident, on the NFKC-normalized text (so
    fullwidth punctuation like ``Rating：Overweight`` is matched the same as
    ASCII):

    1. An explicit label line ("Rating: X", "**Recommendation**: X", ...),
       taking the LAST one written -- a decision states its call after
       discussing the alternatives. A line presenting the scale itself
       ("Rating Scale: Buy, Overweight, ...") is a legend the model echoed,
       not a call, and is skipped.
    2. A line that, once markdown bold and surrounding whitespace are
       stripped, is EXACTLY one of ``choices`` and nothing else -- the common
       free-text-fallback shape where a model states its verdict as a
       standalone heading ("**Hold**") with no explicit label. The LAST such
       line wins, for the same reason as tier 1.
    3. A single occurrence of a choice word anywhere in the text. Several
       distinct occurrences are an argument discussing alternatives, not a
       decision -- picking one of them would report a call nobody made
       (prose that rejects a Buy before concluding Underweight must not read
       as Buy).
    """
    if not text:
        return None
    norm = unicodedata.normalize("NFKC", text)
    choice_set = {c.lower() for c in choices}
    label_re = _label_re(label_words)
    word_re = re.compile(r"\b(" + "|".join(re.escape(c) for c in choices) + r")\b", re.IGNORECASE)

    labelled = None
    standalone = None
    for line in norm.splitlines():
        if _RATING_SCALE_RE.search(line):
            continue
        m = label_re.search(line)
        if m and m.group(1).lower() in choice_set:
            labelled = m.group(1).capitalize()
            continue
        bare = line.strip().strip("*").strip()
        if bare.lower() in choice_set:
            standalone = bare.capitalize()
    if labelled:
        return labelled
    if standalone:
        return standalone

    named = {m.group(1).capitalize() for m in word_re.finditer(norm)}
    return named.pop() if len(named) == 1 else None


def extract_rating(text: str) -> str | None:
    """Extract a 5-tier Research Manager/Portfolio Manager rating from prose,
    or ``None`` if none is present. See ``extract_choice`` for the algorithm.
    """
    return extract_choice(text, RATINGS_5_TIER, label_words=("rating", "recommendation"))


def parse_rating(text: str, default: str = RATING_REVIEW) -> str:
    """Extract a 5-tier rating, or ``REVIEW`` when the decision has none.

    For callers that need a string for every decision, such as the memory log's
    entry tag. The default is the review sentinel, never a tradeable rating.
    """
    rating = extract_rating(text)
    return rating if rating is not None else default


def is_review(signal: str) -> bool:
    """Whether a signal is the non-tradeable REVIEW sentinel (#1170)."""
    return signal == RATING_REVIEW
