"""Non-interactive single and sequential batch execution helpers."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.display import ANALYST_ORDER
from cli.models import AnalystType
from cli.prompts import detect_asset_type, filter_analysts_for_asset_type, normalize_ticker_symbol
from cli.run import _build_run_config, execute_analysis
from tradingagents.agents.rating import RATINGS_5_TIER, is_review
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import _validate_trade_date

DEPTH_SELECTIONS = {"shallow": 1, "medium": 3, "deep": 5}
_ACTIONS = ("Buy", "Hold", "Sell")


def parse_depth(value: str) -> tuple[str, int]:
    name = value.strip().lower()
    if name not in DEPTH_SELECTIONS:
        choices = ", ".join(DEPTH_SELECTIONS)
        raise ValueError(f"unknown depth {value!r}; choose one of: {choices}")
    return name, DEPTH_SELECTIONS[name]


def parse_analysts(value: str) -> list[str]:
    requested = [item.strip().lower() for item in value.split(",") if item.strip()]
    invalid = sorted(set(requested) - set(ANALYST_ORDER))
    if invalid:
        raise ValueError(
            f"unknown analyst(s): {', '.join(invalid)}; "
            f"choose from: {', '.join(ANALYST_ORDER)}"
        )
    if not requested:
        raise ValueError("at least one analyst must be selected")
    return [name for name in ANALYST_ORDER if name in requested]


def parse_tickers(value: str | None, tickers_file: Path | None = None) -> list[str]:
    raw = [item.strip() for item in (value or "").split(",") if item.strip()]
    if tickers_file is not None:
        raw.extend(
            line.strip()
            for line in tickers_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    if not raw:
        raise ValueError("provide at least one ticker with --tickers or --tickers-file")

    tickers = []
    seen = set()
    for item in raw:
        ticker = normalize_ticker_symbol(item)
        safe_ticker_component(ticker)
        if ticker not in seen:
            tickers.append(ticker)
            seen.add(ticker)
    return tickers


def build_headless_config(depth_value: int, language: str, results_dir: Path) -> dict:
    if not language.strip():
        raise ValueError("language must not be empty")
    selections = {
        "research_depth": depth_value,
        "quick_think_llm": DEFAULT_CONFIG["quick_think_llm"],
        "deep_think_llm": DEFAULT_CONFIG["deep_think_llm"],
        "backend_url": DEFAULT_CONFIG["backend_url"],
        "llm_provider": DEFAULT_CONFIG["llm_provider"],
        "google_thinking_level": DEFAULT_CONFIG.get("google_thinking_level"),
        "openai_reasoning_effort": DEFAULT_CONFIG.get("openai_reasoning_effort"),
        "anthropic_effort": DEFAULT_CONFIG.get("anthropic_effort"),
        "output_language": language.strip(),
    }
    config = _build_run_config(selections, checkpoint=None)
    config["results_dir"] = str(results_dir)
    return config


def _analysts_for_ticker(analysts: list[str], ticker: str) -> tuple[list[str], str]:
    asset_type = detect_asset_type(ticker)
    selected = filter_analysts_for_asset_type(
        [AnalystType(name) for name in analysts], asset_type
    )
    if not selected:
        raise ValueError(f"no selected analysts support {ticker}")
    return [analyst.value for analyst in selected], asset_type.value


def _field(text: str, label: str) -> str | None:
    match = re.search(
        rf"^\s*\**{re.escape(label)}\**\s*:\s*(.+?)\s*$",
        text or "",
        re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        return None
    return match.group(1).strip().strip("*") or None


def _choice_field(text: str, label: str, choices: tuple[str, ...]) -> str | None:
    value = _field(text, label)
    if value is None:
        return None
    return next((choice for choice in choices if value.lower() == choice.lower()), None)


def _number_field(text: str, label: str) -> float | None:
    value = _field(text, label)
    if value is None or value.lower() == "not provided":
        return None
    cleaned = value.replace(",", "").removeprefix("$").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def result_document(execution, report_root: Path) -> dict[str, Any]:
    state = execution.final_state
    final_decision = state.get("final_trade_decision", "")
    trader_plan = state.get("trader_investment_plan", "")
    research_plan = state.get("investment_plan", "")
    rating = None if is_review(execution.rating) else execution.rating
    report_path = (
        execution.report_path.relative_to(report_root).as_posix()
        if execution.report_path is not None
        else None
    )
    return {
        "ticker": execution.ticker,
        "analysis_date": execution.analysis_date,
        "status": "ok",
        "rating": rating,
        "rating_parse_status": "parsed" if rating is not None else "unparsed",
        "action": _choice_field(trader_plan, "Action", _ACTIONS),
        "entry_price": _number_field(trader_plan, "Entry Price"),
        "stop_loss": _number_field(trader_plan, "Stop Loss"),
        "summary": _field(final_decision, "Executive Summary"),
        "research_recommendation": _choice_field(
            research_plan, "Recommendation", RATINGS_5_TIER
        ),
        "portfolio_manager_rating": rating,
        "raw_final_decision": final_decision or None,
        "report_path": report_path,
        "run_duration_seconds": round(execution.duration_seconds, 3),
        "stats": execution.stats,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def run_single_analysis(
    *,
    ticker: str,
    analysis_date: str,
    analysts: list[str],
    depth_value: int,
    language: str,
    output_dir: Path,
    report_root: Path | None = None,
) -> dict[str, Any]:
    ticker = normalize_ticker_symbol(ticker)
    safe_ticker_component(ticker)
    analysis_date = _validate_trade_date(analysis_date)
    selected_analysts, asset_type = _analysts_for_ticker(analysts, ticker)
    output_dir = output_dir.resolve()
    root = (report_root or output_dir).resolve()
    config = build_headless_config(depth_value, language, root)
    execution = execute_analysis(
        ticker=ticker,
        analysis_date=analysis_date,
        selected_analysts=selected_analysts,
        asset_type=asset_type,
        config=config,
        output_dir=output_dir,
    )
    result = result_document(execution, root)
    _write_json(output_dir / "result.json", result)
    return result


def _error_result(ticker: str, analysis_date: str, error: Exception, duration: float) -> dict:
    return {
        "ticker": ticker,
        "analysis_date": analysis_date,
        "status": "error",
        "rating": None,
        "rating_parse_status": "not_run",
        "action": None,
        "entry_price": None,
        "stop_loss": None,
        "summary": None,
        "research_recommendation": None,
        "portfolio_manager_rating": None,
        "raw_final_decision": None,
        "report_path": None,
        "run_duration_seconds": round(duration, 3),
        "stats": None,
        "error": str(error),
    }


def _format_duration(seconds: float) -> str:
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def write_batch_summary(
    output_dir: Path,
    *,
    analysis_date: str,
    depth: str,
    analysts: list[str],
    language: str,
    results: list[dict],
) -> tuple[Path, Path]:
    successful = sum(result["status"] == "ok" for result in results)
    metadata = {
        "analysis_date": analysis_date,
        "depth": depth,
        "analysts": analysts,
        "language": language,
        "tickers": [result["ticker"] for result in results],
        "successful": successful,
        "failed": len(results) - successful,
        "results": results,
    }
    json_path = output_dir / "summary.json"
    _write_json(json_path, metadata)

    lines = [
        "# TradingAgents Batch Summary",
        "",
        "| Ticker | Status | Rating | Action | Entry | Stop | Report |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for result in results:
        ok = result["status"] == "ok"
        link = (
            f"[report]({result['report_path']})"
            if ok and result.get("report_path")
            else f"[error]({safe_ticker_component(result['ticker'])}/result.json)"
        )
        lines.append(
            "| {ticker} | {status} | {rating} | {action} | {entry} | {stop} | {link} |".format(
                ticker=result["ticker"],
                status="OK" if ok else "ERROR",
                rating=result.get("rating") or "-",
                action=result.get("action") or "-",
                entry=result.get("entry_price") if result.get("entry_price") is not None else "-",
                stop=result.get("stop_loss") if result.get("stop_loss") is not None else "-",
                link=link,
            )
        )
    failures = [result for result in results if result["status"] == "error"]
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- **{result['ticker']}**: {result['error']}" for result in failures)
    markdown_path = output_dir / "summary.md"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return markdown_path, json_path


def run_batch_analysis(
    *,
    tickers: list[str],
    analysis_date: str,
    analysts: list[str],
    depth_name: str,
    depth_value: int,
    language: str,
    output_dir: Path,
    progress: Callable[[str], None],
) -> tuple[list[dict], Path, Path]:
    analysis_date = _validate_trade_date(analysis_date)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for index, ticker in enumerate(tickers, start=1):
        ticker_dir = output_dir / safe_ticker_component(ticker)
        progress(f"[{index}/{len(tickers)}] {ticker} - starting")
        started = time.monotonic()
        try:
            result = run_single_analysis(
                ticker=ticker,
                analysis_date=analysis_date,
                analysts=analysts,
                depth_value=depth_value,
                language=language,
                output_dir=ticker_dir,
                report_root=output_dir,
            )
            progress(
                f"[{index}/{len(tickers)}] {ticker} - completed in "
                f"{_format_duration(result['run_duration_seconds'])}"
            )
        except Exception as exc:
            result = _error_result(
                ticker, analysis_date, exc, time.monotonic() - started
            )
            _write_json(ticker_dir / "result.json", result)
            progress(f"[{index}/{len(tickers)}] {ticker} - FAILED: {exc}")
        results.append(result)

    markdown_path, json_path = write_batch_summary(
        output_dir,
        analysis_date=analysis_date,
        depth=depth_name,
        analysts=analysts,
        language=language,
        results=results,
    )
    return results, markdown_path, json_path
