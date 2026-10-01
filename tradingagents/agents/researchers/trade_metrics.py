"""Deterministic, code-computed trade-plan metrics for the research debate.

The LLM commits to entry/take-profit/stop-loss levels; every number derived
from them (risk, reward, ATR distances) is computed here in plain arithmetic
so it cannot drift from what the model typed -- the same principle already
applied to arithmetic-claim verification (see ``researchers/arithmetic.py``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradeMetrics:
    entry_reference: float | None = None
    risk: float | None = None
    reward: float | None = None
    risk_pct: float | None = None
    reward_pct: float | None = None
    reward_risk: float | None = None
    stop_atr: float | None = None
    target_atr: float | None = None


def entry_reference(
    entry_price: float | None, entry_low: float | None, entry_high: float | None
) -> float | None:
    """The single reference entry used for derived calculations.

    A point entry is used directly. A range entry uses the midpoint of
    low/high -- the documented default rule for entry-range handling (see
    fork README) -- and a one-sided range falls back to whichever bound is
    present rather than silently picking one.
    """
    if entry_price is not None:
        return entry_price
    if entry_low is not None and entry_high is not None:
        return (entry_low + entry_high) / 2
    return entry_low if entry_low is not None else entry_high


def compute_trade_metrics(
    *,
    entry_price: float | None = None,
    entry_low: float | None = None,
    entry_high: float | None = None,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    atr: float | None = None,
) -> TradeMetrics:
    """Compute deterministic trade metrics.

    Any missing or zero input yields ``None`` fields rather than raising --
    a thesis with no stop-loss still gets an entry reference and whatever
    else is computable, instead of losing the whole metrics block.
    """
    entry = entry_reference(entry_price, entry_low, entry_high)
    if entry is None or entry == 0:
        return TradeMetrics(entry_reference=entry)

    risk = abs(entry - stop_loss) if stop_loss is not None else None
    reward = abs(take_profit - entry) if take_profit is not None else None

    risk_pct = (risk / abs(entry) * 100) if risk is not None else None
    reward_pct = (reward / abs(entry) * 100) if reward is not None else None
    reward_risk = reward / risk if reward is not None and risk not in (None, 0) else None
    stop_atr = risk / atr if risk is not None and atr not in (None, 0) else None
    target_atr = reward / atr if reward is not None and atr not in (None, 0) else None

    return TradeMetrics(
        entry_reference=entry,
        risk=risk,
        reward=reward,
        risk_pct=risk_pct,
        reward_pct=reward_pct,
        reward_risk=reward_risk,
        stop_atr=stop_atr,
        target_atr=target_atr,
    )


def trade_metrics_from_dict(data: dict | None) -> TradeMetrics:
    """Rehydrate a ``TradeMetrics`` from the plain dict stored in debate state."""
    data = data or {}
    return TradeMetrics(
        entry_reference=data.get("entry_reference"),
        risk=data.get("risk"),
        reward=data.get("reward"),
        risk_pct=data.get("risk_pct"),
        reward_pct=data.get("reward_pct"),
        reward_risk=data.get("reward_risk"),
        stop_atr=data.get("stop_atr"),
        target_atr=data.get("target_atr"),
    )


def render_trade_metrics(metrics: TradeMetrics) -> str:
    def fmt(value: float | None, suffix: str = "") -> str:
        return f"{value:.2f}{suffix}" if value is not None else "N/A"

    return "\n".join(
        [
            f"Entry (reference): {fmt(metrics.entry_reference)}",
            f"Risk: {fmt(metrics.risk)} ({fmt(metrics.risk_pct, '%')})",
            f"Reward: {fmt(metrics.reward)} ({fmt(metrics.reward_pct, '%')})",
            f"Reward/Risk: {fmt(metrics.reward_risk)}",
            f"Stop distance (ATR multiples): {fmt(metrics.stop_atr)}",
            f"Target distance (ATR multiples): {fmt(metrics.target_atr)}",
        ]
    )
