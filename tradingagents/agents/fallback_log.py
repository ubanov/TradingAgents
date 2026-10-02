"""Expected, recoverable degradation reporting -- WARN severity, stdout.

Nothing in this project calls ``logging.basicConfig`` or attaches a handler,
so a bare ``logger.warning(...)`` falls through to Python's
``logging.lastResort`` -- a ``StreamHandler(sys.stderr)`` at WARNING level.
When TradingAgents runs under PowerShell, any stderr output from the process
is rendered as a red ``NativeCommandError`` block, even though a structured-
output call falling back to free text is a routine, already-handled path, not
a failure. That trains users to associate red output with "ignore it" --
exactly when a genuine error needs to stand out.

``warn_fallback()`` is the one place every structured-output-fallback call
site reports through: one concise ``[WARN]`` line on stdout (what degraded,
what fallback is used), never a traceback or raw Pydantic error dump. The
full exception detail is still available via the normal ``logging`` module at
DEBUG level -- below ``lastResort``'s WARNING threshold, so it produces no
stderr output by default, but is still there for anyone who configures a
DEBUG handler (no new logging framework needed).

A genuine unrecoverable failure (missing prompt file, graph aborting, a
report that cannot be persisted) must keep using ``logger.error`` or an
exception -- this module is only for a path that already has a working
fallback.
"""

from __future__ import annotations

import logging

_fallback_count = 0


def warn_fallback(logger: logging.Logger, summary: str, detail: str = "") -> None:
    """Print one concise ``[WARN]`` line to stdout; log full detail at DEBUG.

    ``summary`` should say what degraded and what fallback is now in effect,
    e.g. "Bull Researcher: structured review unavailable; continuing with
    free-text fallback." ``detail`` is the raw exception text or similar,
    kept out of normal output but still reachable via DEBUG logging.
    """
    global _fallback_count
    _fallback_count += 1
    print(f"[WARN] {summary}", flush=True)
    if detail:
        logger.debug("%s -- detail: %s", summary, detail)


def fallback_count() -> int:
    """Recoverable fallback warnings reported since the last reset."""
    return _fallback_count


def reset_fallback_count() -> None:
    """Zero the counter -- called once per ticker so batch runs report a
    per-ticker count, not a running total across the whole batch."""
    global _fallback_count
    _fallback_count = 0
