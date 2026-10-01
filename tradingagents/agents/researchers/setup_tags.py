"""Deterministic objective setup tags shared by the Bull and Bear researchers.

Bull and Bear must start their initial theses from the same objective read of
the market, then are free to interpret it differently (that disagreement is
the point). This module computes a small, fixed v1 taxonomy of tags from raw
OHLCV + indicator values -- no LLM involved -- so the tags can later be
persisted and compared across runs without drifting between the two sides.

Deliberately excludes interpretive/semantic tags (e.g. "BULL_FLAG",
"ACCUMULATION"): those are analysis, not objective facts, and belong in the
researchers' prose, not in this taxonomy.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from stockstats import wrap

from tradingagents.dataflows.vendors.yahoo.ohlcv import load_ohlcv

UNKNOWN = "UNKNOWN"

SETUP_TAG_NAMES: tuple[str, ...] = (
    "RSI_BUCKET",
    "MACD_SIGN",
    "MACD_HISTOGRAM_SIGN",
    "PRICE_VS_EMA10",
    "PRICE_VS_SMA20",
    "PRICE_VS_SMA50",
    "SMA50_VS_SMA200",
    "ATR_PCT_BUCKET",
    "VOLUME_VS_AVERAGE",
    "TREND_STRUCTURE",
)

# "NEAR" tolerance for a price-vs-moving-average comparison: within this
# fraction of the reference value counts as NEAR rather than ABOVE/BELOW.
# Not specified by the original taxonomy; chosen and documented here (and in
# the fork README) rather than left implicit.
_NEAR_TOLERANCE = 0.005  # 0.5%

_UNKNOWN_TAGS: dict[str, str] = dict.fromkeys(SETUP_TAG_NAMES, UNKNOWN)


@dataclass(frozen=True)
class SetupTagInputs:
    """Raw numeric inputs the tag builder buckets. Any field may be ``None``."""

    close: float | None = None
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    ema10: float | None = None
    sma20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    atr: float | None = None
    volume: float | None = None
    volume_average: float | None = None


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and not pd.isna(value)


def _rsi_bucket(rsi) -> str:
    if not _is_number(rsi):
        return UNKNOWN
    if rsi < 30:
        return "RSI_LT_30"
    if rsi < 50:
        return "RSI_30_50"
    if rsi < 65:
        return "RSI_50_65"
    if rsi < 70:
        return "RSI_65_70"
    return "RSI_GT_70"


def _sign_bucket(value) -> str:
    if not _is_number(value):
        return UNKNOWN
    if value > 0:
        return "POSITIVE"
    if value < 0:
        return "NEGATIVE"
    return "ZERO"


def _vs_reference_bucket(value, reference) -> str:
    if not _is_number(value) or not _is_number(reference) or reference == 0:
        return UNKNOWN
    delta = (value - reference) / abs(reference)
    if abs(delta) <= _NEAR_TOLERANCE:
        return "NEAR"
    return "ABOVE" if delta > 0 else "BELOW"


def _atr_pct_bucket(atr, reference) -> str:
    if not _is_number(atr) or not _is_number(reference) or reference == 0:
        return UNKNOWN
    pct = atr / reference * 100
    if pct < 1:
        return "LT_1"
    if pct < 2:
        return "1_TO_2"
    if pct < 3:
        return "2_TO_3"
    if pct < 5:
        return "3_TO_5"
    return "GT_5"


def _volume_bucket(volume, average) -> str:
    if not _is_number(volume) or not _is_number(average) or average == 0:
        return UNKNOWN
    ratio = volume / average
    if ratio < 0.75:
        return "WELL_BELOW"
    if ratio < 0.95:
        return "BELOW"
    if ratio <= 1.05:
        return "NEAR"
    if ratio <= 1.25:
        return "ABOVE"
    return "WELL_ABOVE"


def _trend_structure_bucket(sma50, sma200) -> str:
    if not _is_number(sma50) or not _is_number(sma200):
        return UNKNOWN
    if sma50 > sma200:
        return "BULLISH"
    if sma50 < sma200:
        return "BEARISH"
    return "MIXED"


def build_setup_tags(inputs: SetupTagInputs) -> dict[str, str]:
    """Deterministically bucket raw indicator values into the fixed v1 taxonomy.

    Pure function of ``inputs`` -- no I/O -- so boundary behavior is fully
    unit-testable without live market data.
    """
    return {
        "RSI_BUCKET": _rsi_bucket(inputs.rsi),
        "MACD_SIGN": _sign_bucket(inputs.macd),
        "MACD_HISTOGRAM_SIGN": _sign_bucket(inputs.macd_hist),
        "PRICE_VS_EMA10": _vs_reference_bucket(inputs.close, inputs.ema10),
        "PRICE_VS_SMA20": _vs_reference_bucket(inputs.close, inputs.sma20),
        "PRICE_VS_SMA50": _vs_reference_bucket(inputs.close, inputs.sma50),
        "SMA50_VS_SMA200": _vs_reference_bucket(inputs.sma50, inputs.sma200),
        "ATR_PCT_BUCKET": _atr_pct_bucket(inputs.atr, inputs.close),
        "VOLUME_VS_AVERAGE": _volume_bucket(inputs.volume, inputs.volume_average),
        "TREND_STRUCTURE": _trend_structure_bucket(inputs.sma50, inputs.sma200),
    }


def compute_setup_tag_inputs(
    symbol: str, curr_date: str, volume_window: int = 20
) -> SetupTagInputs:
    """Fetch OHLCV (Yahoo) and compute raw indicator values as of ``curr_date``.

    Raises on any data problem; callers that need a fail-open result should use
    :func:`build_setup_tags_for_instrument` instead. Mirrors the verified
    market snapshot's data path (``dataflows/vendors/yahoo/snapshot.py``), so
    the tags reflect the same ground truth already shown to the analysts.
    """
    data = load_ohlcv(symbol, curr_date, fill_gaps=False)
    if data is None or data.empty:
        raise ValueError(f"No OHLCV data available for {symbol}.")

    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df = df[df["Date"] <= pd.to_datetime(curr_date)].sort_values("Date")
    if df.empty:
        raise ValueError(f"No OHLCV rows on or before {curr_date} for {symbol}.")

    stock_df = wrap(df.copy())

    def latest(col: str) -> float | None:
        try:
            stock_df[col]  # triggers stockstats calculation
            value = stock_df.iloc[-1][col]
            return float(value) if _is_number(value) else None
        except Exception:  # noqa: BLE001 -- one bad indicator shouldn't sink the rest
            return None

    volume_series = df["Volume"].tail(max(1, volume_window))
    volume_average = float(volume_series.mean()) if not volume_series.empty else None

    latest_row = df.iloc[-1]
    close = latest_row.get("Close")
    volume = latest_row.get("Volume")

    return SetupTagInputs(
        close=float(close) if _is_number(close) else None,
        rsi=latest("rsi"),
        macd=latest("macd"),
        macd_signal=latest("macds"),
        macd_hist=latest("macdh"),
        ema10=latest("close_10_ema"),
        sma20=latest("close_20_sma"),
        sma50=latest("close_50_sma"),
        sma200=latest("close_200_sma"),
        atr=latest("atr"),
        volume=float(volume) if _is_number(volume) else None,
        volume_average=volume_average,
    )


def build_setup_tags_for_instrument(symbol: str, curr_date: str) -> dict[str, str]:
    """Best-effort tag computation for a live run.

    Fails open to all-UNKNOWN tags on any data problem (unsupported vendor,
    missing history, rate limit, ...) rather than blocking the research
    debate, matching ``resolve_instrument_identity``'s fail-open convention.
    """
    return build_setup_tags_and_atr_for_instrument(symbol, curr_date)[0]


def build_setup_tags_and_atr_for_instrument(
    symbol: str, curr_date: str
) -> tuple[dict[str, str], float | None]:
    """Best-effort tags plus the raw ATR value, computed from a single fetch.

    The ATR is shared with the deterministic trade-metric calculations so
    both sides' risk/reward figures are computed from the same market read as
    their setup tags. Called once per run, outside any agent node -- see
    ``TradingAgentsGraph.create_run_state`` -- so a bare unit test that builds
    state directly (bypassing the graph) never triggers a network call.
    """
    try:
        inputs = compute_setup_tag_inputs(symbol, curr_date)
    except Exception:  # noqa: BLE001 -- fail open, never block the run
        return dict(_UNKNOWN_TAGS), None
    return build_setup_tags(inputs), inputs.atr


def render_setup_tags(tags: dict[str, str]) -> str:
    """Render the shared tags for prompt inclusion, in the fixed taxonomy order."""
    if not tags:
        return "No setup tags were computed for this run."
    return "\n".join(f"{name}: {tags.get(name, UNKNOWN)}" for name in SETUP_TAG_NAMES)
