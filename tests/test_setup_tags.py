"""Deterministic objective setup-tag taxonomy (fork README: Objective setup tags)."""

from __future__ import annotations

import pytest

from tradingagents.agents.researchers.setup_tags import (
    SETUP_TAG_NAMES,
    UNKNOWN,
    SetupTagInputs,
    build_setup_tags,
    build_setup_tags_for_instrument,
    render_setup_tags,
)


def _inputs(**overrides) -> SetupTagInputs:
    base = {
        "close": 100.0,
        "rsi": 55.0,
        "macd": 1.0,
        "macd_signal": 0.5,
        "macd_hist": -0.2,
        "ema10": 101.0,
        "sma20": 99.0,
        "sma50": 95.0,
        "sma200": 90.0,
        "atr": 2.0,
        "volume": 1000.0,
        "volume_average": 1000.0,
    }
    base.update(overrides)
    return SetupTagInputs(**base)


@pytest.mark.unit
@pytest.mark.parametrize(
    "rsi, expected",
    [
        (10, "RSI_LT_30"),
        (29.99, "RSI_LT_30"),
        (30, "RSI_30_50"),
        (49.99, "RSI_30_50"),
        (50, "RSI_50_65"),
        (64.99, "RSI_50_65"),
        (65, "RSI_65_70"),
        (69.99, "RSI_65_70"),
        (70, "RSI_GT_70"),
        (90, "RSI_GT_70"),
        (None, UNKNOWN),
    ],
)
def test_rsi_bucket_boundaries(rsi, expected):
    tags = build_setup_tags(_inputs(rsi=rsi))
    assert tags["RSI_BUCKET"] == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "macd, expected", [(1.0, "POSITIVE"), (-1.0, "NEGATIVE"), (0.0, "ZERO"), (None, UNKNOWN)]
)
def test_macd_sign(macd, expected):
    assert build_setup_tags(_inputs(macd=macd))["MACD_SIGN"] == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "hist, expected", [(0.3, "POSITIVE"), (-0.3, "NEGATIVE"), (0.0, "ZERO"), (None, UNKNOWN)]
)
def test_macd_histogram_sign(hist, expected):
    assert build_setup_tags(_inputs(macd_hist=hist))["MACD_HISTOGRAM_SIGN"] == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "close, reference, expected",
    [
        (110, 100, "ABOVE"),
        (90, 100, "BELOW"),
        (100.2, 100, "NEAR"),
        (99.8, 100, "NEAR"),
        (None, 100, UNKNOWN),
        (100, None, UNKNOWN),
    ],
)
def test_price_vs_ema10(close, reference, expected):
    tags = build_setup_tags(_inputs(close=close, ema10=reference))
    assert tags["PRICE_VS_EMA10"] == expected


@pytest.mark.unit
def test_price_vs_sma20_and_sma50():
    tags = build_setup_tags(_inputs(close=110, sma20=100, sma50=90))
    assert tags["PRICE_VS_SMA20"] == "ABOVE"
    assert tags["PRICE_VS_SMA50"] == "ABOVE"
    tags = build_setup_tags(_inputs(close=80, sma20=100, sma50=90))
    assert tags["PRICE_VS_SMA20"] == "BELOW"
    assert tags["PRICE_VS_SMA50"] == "BELOW"


@pytest.mark.unit
@pytest.mark.parametrize(
    "sma50, sma200, expected",
    [(110, 100, "ABOVE"), (90, 100, "BELOW"), (100.1, 100, "NEAR"), (None, 100, UNKNOWN)],
)
def test_sma50_vs_sma200(sma50, sma200, expected):
    tags = build_setup_tags(_inputs(sma50=sma50, sma200=sma200))
    assert tags["SMA50_VS_SMA200"] == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "atr, close, expected",
    [
        (0.5, 100, "LT_1"),
        (1.5, 100, "1_TO_2"),
        (2.5, 100, "2_TO_3"),
        (4, 100, "3_TO_5"),
        (6, 100, "GT_5"),
        (None, 100, UNKNOWN),
    ],
)
def test_atr_pct_bucket(atr, close, expected):
    tags = build_setup_tags(_inputs(atr=atr, close=close))
    assert tags["ATR_PCT_BUCKET"] == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "volume, average, expected",
    [
        (700, 1000, "WELL_BELOW"),
        (900, 1000, "BELOW"),
        (1000, 1000, "NEAR"),
        (1050, 1000, "NEAR"),
        (1100, 1000, "ABOVE"),
        (1300, 1000, "WELL_ABOVE"),
        (None, 1000, UNKNOWN),
    ],
)
def test_volume_vs_average(volume, average, expected):
    tags = build_setup_tags(_inputs(volume=volume, volume_average=average))
    assert tags["VOLUME_VS_AVERAGE"] == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "sma50, sma200, expected",
    [(110, 100, "BULLISH"), (90, 100, "BEARISH"), (100, 100, "MIXED"), (None, 100, UNKNOWN)],
)
def test_trend_structure(sma50, sma200, expected):
    tags = build_setup_tags(_inputs(sma50=sma50, sma200=sma200))
    assert tags["TREND_STRUCTURE"] == expected


@pytest.mark.unit
def test_build_setup_tags_covers_the_full_fixed_taxonomy():
    tags = build_setup_tags(_inputs())
    assert set(tags.keys()) == set(SETUP_TAG_NAMES)
    assert all(value != "" for value in tags.values())


@pytest.mark.unit
def test_render_setup_tags_is_deterministic_and_ordered():
    tags = build_setup_tags(_inputs())
    rendered = render_setup_tags(tags)
    lines = rendered.splitlines()
    assert [line.split(":")[0] for line in lines] == list(SETUP_TAG_NAMES)


@pytest.mark.unit
def test_build_setup_tags_for_instrument_fails_open_on_bad_data(monkeypatch):
    def _boom(symbol, curr_date, fill_gaps=False):
        raise ValueError("vendor unavailable")

    monkeypatch.setattr(
        "tradingagents.agents.researchers.setup_tags.load_ohlcv", _boom
    )
    tags = build_setup_tags_for_instrument("NVDA", "2026-09-01")
    assert set(tags.keys()) == set(SETUP_TAG_NAMES)
    assert all(value == UNKNOWN for value in tags.values())
