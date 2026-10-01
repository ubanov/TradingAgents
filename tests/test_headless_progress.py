"""Non-interactive runs expose useful stage and execution progress."""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import cli.headless as cli_headless
import cli.main as cli_main
from cli.headless import (
    _progress_reporter,
    result_document,
    run_batch_analysis,
    timestamped_echo,
)
from cli.stats_handler import StatsCallbackHandler


@pytest.mark.unit
def test_progress_reports_pipeline_stages_once(monkeypatch):
    lines = []
    stats = StatsCallbackHandler()
    monkeypatch.setattr("cli.headless.time.monotonic", lambda: 100.0)
    reporter = _progress_reporter(
        lines.append,
        "[1/1] NVDA",
        {"max_debate_rounds": 2, "max_risk_discuss_rounds": 1},
        stats,
        started=40.0,
        selected_analysts=["market"],
    )
    debate = {
        "bull_initial": "bull",
        "bear_initial": "bear",
        "debate_round": 2,
        "verifier_pass_count": 1,
        "verification_status": "WARN",
        "repair_rounds": 0,
        "judge_decision": "manager",
    }
    risk = {"count": 3, "latest_speaker": "Neutral Analyst", "judge_decision": "pm"}
    chunk = {
        "market_report": "market",
        "investment_debate_state": debate,
        "trader_investment_plan": "trader",
        "risk_debate_state": risk,
    }

    reporter(chunk)
    reporter(chunk)

    output = "\n".join(lines)
    for marker in (
        "market analyst completed",
        "requesting Bull/Bear research debate",
        "Bull initial thesis completed",
        "Bear initial thesis completed",
        "research review 2/2 completed",
        "research verifier pass 1: WARN",
        "research manager completed",
        "requesting trader analysis",
        "trader completed",
        "requesting risk management discussion",
        "risk discussion 3/3: Neutral Analyst",
        "requesting portfolio manager decision",
        "portfolio manager completed",
        "00:01:00",
    ):
        assert marker in output
    assert output.count("research verifier pass 1: WARN") == 1


@pytest.mark.unit
def test_progress_announces_a_manager_integrity_warning(monkeypatch):
    lines = []
    stats = StatsCallbackHandler()
    monkeypatch.setattr("cli.headless.time.monotonic", lambda: 100.0)
    reporter = _progress_reporter(
        lines.append,
        "[1/1] NVDA",
        {"max_debate_rounds": 1, "max_risk_discuss_rounds": 1},
        stats,
        started=100.0,
        selected_analysts=["market"],
    )
    reporter(
        {
            "investment_debate_state": {
                "judge_decision": "manager",
                "manager_integrity_status": "WARN",
                "manager_integrity_findings": [
                    {"category": "NEW_UNSUPPORTED_THRESHOLD", "detail": "x"},
                    {"category": "UNSUPPORTED_SIZING_RULE", "detail": "y"},
                ],
            },
        }
    )
    assert any("manager integrity check: WARN (2 finding(s))" in line for line in lines)


@pytest.mark.unit
def test_progress_announces_each_analyst_request_in_turn(monkeypatch):
    """Each analyst's request line arrives before its completion line."""
    lines = []
    stats = StatsCallbackHandler()
    monkeypatch.setattr("cli.headless.time.monotonic", lambda: 100.0)
    reporter = _progress_reporter(
        lines.append,
        "NVDA",
        {"max_debate_rounds": 1, "max_risk_discuss_rounds": 1},
        stats,
        started=100.0,
        selected_analysts=["market", "news"],
    )
    # Market is the first selected analyst, so its request line is emitted by
    # run_single_analysis at run start, not by the reporter itself.
    reporter({"market_report": "market"})
    assert not any("requesting market analyst analysis" in line for line in lines)
    assert any("NVDA - market analyst completed" in line for line in lines)
    assert any("requesting news analyst analysis" in line for line in lines)
    lines.clear()
    reporter({"news_report": "news"})
    assert any("news analyst completed" in line for line in lines)
    assert any("requesting Bull/Bear research debate" in line for line in lines)


@pytest.mark.unit
def test_timestamped_echo_prefixes_every_line(monkeypatch):
    import datetime as real_datetime

    class _FixedDatetime(real_datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 29, 14, 5, 6)

    monkeypatch.setattr("cli.headless.datetime", _FixedDatetime)
    lines = []
    echo = timestamped_echo(lines.append)
    echo("[1/1] NVDA - starting")
    echo("market analyst completed")
    assert lines == [
        "2026-09-29 14:05:06 [1/1] NVDA - starting",
        "2026-09-29 14:05:06 market analyst completed",
    ]


@pytest.mark.unit
def test_result_document_includes_research_agent_execution_counts(tmp_path):
    state = {
        "investment_debate_state": {
            "bull_initial": "bull",
            "bear_initial": "bear",
            "bull_rebuttal_count": 2,
            "bear_rebuttal_count": 2,
            "verifier_pass_count": 2,
            "verification_status": "PASS",
            "repair_rounds": 1,
            "repaired_agents": ["bull", "bear"],
        },
        "investment_plan": "",
        "trader_investment_plan": "",
        "final_trade_decision": "",
    }
    execution = SimpleNamespace(
        final_state=state,
        ticker="NVDA",
        analysis_date="2026-09-29",
        rating="REVIEW",
        report_path=None,
        duration_seconds=12.5,
        stats={"llm_calls": 10, "tool_calls": 3, "tokens_in": 100, "tokens_out": 20},
    )

    result = result_document(execution, tmp_path)

    assert result["research_execution"] == {
        "bull_initial_calls": 1,
        "bear_initial_calls": 1,
        "bull_review_calls": 2,
        "bear_review_calls": 2,
        "verifier_passes": 2,
        "verification_status": "PASS",
        "repair_rounds": 1,
        "repaired_agents": ["bull", "bear"],
    }


@pytest.mark.unit
def test_result_document_parses_unlabelled_standalone_ratings_and_actions(tmp_path):
    """Regression: a real batch run had SPY's Portfolio Manager text begin
    with '**Hold**' (no 'Rating:' label) and NVDA's begin with
    '**Overweight**' -- both used to come back unparsed even though the
    Trader's labelled '**Action**: Buy' parsed fine, exposing an
    inconsistency between the two parsers."""
    from tradingagents.agents.rating import parse_rating

    final_decision = "**Hold**\n\n**Executive Summary**: No change warranted this week."
    state = {
        "investment_debate_state": {},
        "investment_plan": "**Overweight**\n\nGradually add on dips.",
        "trader_investment_plan": "**Action**: Buy\n\nEnter now.",
        "final_trade_decision": final_decision,
    }
    execution = SimpleNamespace(
        final_state=state,
        ticker="SPY",
        analysis_date="2026-09-29",
        rating=parse_rating(final_decision),
        report_path=None,
        duration_seconds=1.0,
        stats={"llm_calls": 1, "tool_calls": 0, "tokens_in": 1, "tokens_out": 1},
    )

    result = result_document(execution, tmp_path)

    assert result["rating"] == "Hold"
    assert result["rating_parse_status"] == "parsed"
    assert result["portfolio_manager_rating"] == "Hold"
    assert result["research_recommendation"] == "Overweight"
    assert result["action"] == "Buy"
    # Three genuinely separate concepts -- none overwrote another.
    assert result["research_recommendation"] != result["rating"]
    assert result["action"] != result["rating"]


@pytest.mark.unit
def test_run_batch_analysis_isolates_a_failing_ticker_from_the_rest(monkeypatch, tmp_path):
    """One ticker failing (or being unsafe as a path component) must not abort
    the batch or prevent the summary from being written for the others."""

    def fake_run_single_analysis(*, ticker, **kwargs):
        if ticker == "BADTICKER":
            raise RuntimeError("boom")
        return {
            "ticker": ticker,
            "stats": {"llm_calls": 1, "tool_calls": 0, "tokens_in": 10, "tokens_out": 5},
            "research_execution": {
                "verification_status": "PASS", "verifier_passes": 1, "repair_rounds": 0,
            },
            "run_duration_seconds": 1.0,
            "status": "ok",
        }

    monkeypatch.setattr(cli_headless, "run_single_analysis", fake_run_single_analysis)

    results, markdown_path, json_path = run_batch_analysis(
        tickers=["AAPL", "../escape", "BADTICKER", "MSFT"],
        analysis_date="2026-09-29",
        analysts=["market"],
        depth_name="medium",
        depth_value=2,
        language="English",
        output_dir=tmp_path,
        progress=lambda line: None,
    )

    assert [r["ticker"] for r in results] == ["AAPL", "../escape", "BADTICKER", "MSFT"]
    statuses = {r["ticker"]: r["status"] for r in results}
    assert statuses["AAPL"] == "ok"
    assert statuses["MSFT"] == "ok"
    assert statuses["../escape"] == "error"
    assert statuses["BADTICKER"] == "error"
    assert markdown_path.exists()
    assert json_path.exists()


@pytest.mark.unit
def test_batch_prints_aggregate_execution_summary(monkeypatch, tmp_path):
    successful = {
        "ticker": "NVDA",
        "status": "ok",
        "run_duration_seconds": 65,
        "stats": {
            "llm_calls": 12,
            "tool_calls": 4,
            "tokens_in": 1000,
            "tokens_out": 200,
        },
        "research_execution": {
            "bull_initial_calls": 1,
            "bear_initial_calls": 1,
            "bull_review_calls": 2,
            "bear_review_calls": 2,
            "verifier_passes": 1,
            "repair_rounds": 0,
        },
    }

    def fake_batch(**kwargs):
        kwargs["progress"]("[1/1] NVDA - market analyst completed")
        return [successful], tmp_path / "summary.md", tmp_path / "summary.json"

    monkeypatch.setattr(cli_main, "run_batch_analysis", fake_batch)
    result = CliRunner().invoke(
        cli_main.app,
        [
            "batch",
            "--tickers",
            "NVDA",
            "--date",
            "2026-09-29",
            "--analysts",
            "market,news",
            "--depth",
            "medium",
            "--language",
            "Spanish",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "market analyst completed" in result.output
    # Batch output is line-buffered plain text: every line carries the
    # wall-clock timestamp prefix the user asked for.
    assert re.search(
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[1/1\] NVDA - market analyst completed$",
        result.output,
        re.MULTILINE,
    )
    assert "elapsed 00:01:05" in result.output
    assert "tokens 1000 in/200 out" in result.output
    assert "Bull reviews 2" in result.output
    assert "Verifier 1" in result.output
