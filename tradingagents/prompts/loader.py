"""Small helpers for loading packaged prompt text."""

from __future__ import annotations

import logging
from functools import lru_cache
from importlib import resources

logger = logging.getLogger(__name__)

_PROMPT_PACKAGE = "tradingagents.prompts"
_GLOBAL_POLICY = "global_policy.txt"


class _MissingPlaceholderDict(dict):
    """``.format_map`` support dict: a template placeholder with no supplied
    value renders as a visible marker instead of raising ``KeyError``.

    Prompt ``.txt`` files are read fresh from disk on every call (no process
    restart needed), while the Python code supplying kwargs is only loaded
    once at process start. A long-running batch process (hours) whose prompt
    file gains a new placeholder mid-run -- e.g. a code change landing on disk
    while the process already has the OLD node function in memory -- would
    otherwise crash with a bare ``KeyError`` immediately before Portfolio
    Manager, discarding a completed multi-hour run (the
    ``risk_stance_summary`` incident). Degrading to a loud, visible marker
    instead keeps the run alive and makes the mismatch impossible to miss in
    the rendered prompt.
    """

    def __missing__(self, key):
        logger.warning(
            "Prompt placeholder %r has no supplied value; rendering a visible "
            "marker instead of raising (prompt/code version mismatch?).",
            key,
        )
        return f"[MISSING:{key}]"


def load_prompt(path: str) -> str:
    """Load a built-in prompt file as UTF-8 text."""
    try:
        return resources.files(_PROMPT_PACKAGE).joinpath(path).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Built-in prompt file is missing: {path}") from exc


@lru_cache(maxsize=1)
def load_global_policy() -> str:
    """Load the shared policy applied to every LLM agent prompt."""
    return load_prompt(_GLOBAL_POLICY)


def with_global_policy(role_prompt: str) -> str:
    """Prepend the shared global policy to one role-specific prompt."""
    return f"{load_global_policy().rstrip()}\n\n{role_prompt.lstrip()}"


def render_agent_prompt(path: str, **values: object) -> str:
    """Load a role prompt, prepend the global policy, and interpolate values.

    Uses ``format_map`` with a missing-placeholder-tolerant dict rather than
    ``.format(**values)`` directly: see ``_MissingPlaceholderDict``.
    """
    return with_global_policy(load_prompt(path)).format_map(_MissingPlaceholderDict(values))
