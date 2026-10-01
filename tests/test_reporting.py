"""Report parity: the shared writer produces the report tree for the CLI and the
programmatic API alike (#1037)."""

from types import SimpleNamespace

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import write_report_tree


def _state():
    return {
        "market_report": "MKT",
        "news_report": "NEWS",
        "investment_debate_state": {
            "judge_decision": "RM PLAN",
            "verification_history": [
                {
                    "status": "WARN",
                    "findings": [
                        {
                            "category": "UNSUPPORTED_CLAIM",
                            "severity": "MEDIUM",
                            "agent": "bull_review_1",
                            "claim": "55-60% probability",
                            "evidence": "No supplied sample",
                            "correction": "",
                            "reason": "Probability is unsupported",
                            "arithmetic": None,
                        }
                    ],
                    "verified_points": [],
                    "repair_required": False,
                    "repair_targets": [],
                    "notes": "",
                }
            ],
        },
        "trader_investment_plan": "TRADE",
        "risk_debate_state": {"judge_decision": "PM DECISION"},
    }


@pytest.mark.unit
def test_write_report_tree_creates_files(tmp_path):
    out = write_report_tree(_state(), "AAPL", tmp_path)
    assert out.name == "complete_report.md"
    assert (tmp_path / "1_analysts" / "market.md").read_text() == "MKT"
    assert (tmp_path / "1_analysts" / "news.md").read_text() == "NEWS"
    assert (tmp_path / "2_research" / "manager.md").read_text() == "RM PLAN"
    verification = (tmp_path / "2_research" / "verification.md").read_text()
    assert "Pass 1: WARN" in verification
    assert "UNSUPPORTED_CLAIM" in verification
    assert (tmp_path / "3_trading" / "trader.md").read_text() == "TRADE"
    assert (tmp_path / "5_portfolio" / "decision.md").read_text() == "PM DECISION"
    complete = out.read_text()
    assert "Trading Analysis Report: AAPL" in complete
    assert "MKT" in complete and "PM DECISION" in complete
    assert "Research Verification" in complete


@pytest.mark.unit
def test_write_report_tree_includes_compact_research_context_when_structured_state_present(
    tmp_path,
):
    state = _state()
    state["investment_debate_state"].update(
        {
            "research_horizon": "5-10 trading sessions",
            "setup_tags": {"RSI_BUCKET": "RSI_50_65"},
            "bull_thesis": {"suggested_risk_unit": "MEDIUM"},
            "bull_conviction_history": [75, 68],
            "bull_trade_metrics": {"entry_reference": 83100.0, "risk": 6180.0},
            "new_data_exceptions": [
                {"side": "bull", "round": 1, "datum": "X", "reason": "Y", "source": "Z"}
            ],
        }
    )
    write_report_tree(state, "AAPL", tmp_path)
    context = (tmp_path / "2_research" / "context.md").read_text()
    assert "5-10 trading sessions" in context
    assert "RSI_BUCKET: RSI_50_65" in context
    assert "75 -> 68" in context
    assert "MEDIUM" in context
    assert "[bull round 1] X" in context
    # Compact: no raw JSON dump of the full structured state in the human report.
    assert "{" not in context


@pytest.mark.unit
def test_write_report_tree_includes_manager_integrity_section_on_warn(tmp_path):
    state = _state()
    state["investment_debate_state"].update(
        {
            "manager_integrity_status": "WARN",
            "manager_integrity_findings": [
                {"category": "NEW_UNSUPPORTED_THRESHOLD", "detail": "MACD histogram > +0.5"}
            ],
        }
    )
    write_report_tree(state, "AAPL", tmp_path)
    integrity = (tmp_path / "2_research" / "manager_integrity.md").read_text()
    assert "Status: WARN" in integrity
    assert "NEW_UNSUPPORTED_THRESHOLD: MACD histogram > +0.5" in integrity


@pytest.mark.unit
def test_write_report_tree_omits_research_context_when_no_structured_state(tmp_path):
    write_report_tree(_state(), "AAPL", tmp_path)
    assert not (tmp_path / "2_research" / "context.md").exists()


@pytest.mark.unit
def test_write_report_tree_with_error_banner_and_custom_filename(tmp_path):
    state = _state()
    del state["risk_debate_state"]["judge_decision"]  # incomplete: PM never ran
    out = write_report_tree(
        state, "GLD", tmp_path,
        error_banner="Failed at stage: portfolio_manager after 02:43:48.",
        output_filename="partial_report.md",
    )
    assert out.name == "partial_report.md"
    assert not (tmp_path / "complete_report.md").exists()
    text = out.read_text()
    assert "INCOMPLETE RUN" in text
    assert "NOT A FINAL RECOMMENDATION" in text
    assert "portfolio_manager after 02:43:48" in text
    # Sections that DID complete are still present.
    assert "MKT" in text
    assert "TRADE" in text


@pytest.mark.unit
def test_write_report_tree_without_error_banner_has_no_incomplete_notice(tmp_path):
    out = write_report_tree(_state(), "AAPL", tmp_path)
    assert "INCOMPLETE RUN" not in out.read_text()


@pytest.mark.unit
def test_save_reports_explicit_path(tmp_path):
    # Unbound: with an explicit save_path, the method doesn't touch self/config.
    out = TradingAgentsGraph.save_reports(None, _state(), "AAPL", save_path=tmp_path)
    assert (tmp_path / "complete_report.md").exists()
    assert out == tmp_path / "complete_report.md"


@pytest.mark.unit
def test_save_reports_defaults_under_results_dir(tmp_path):
    mock_self = SimpleNamespace(config={"results_dir": str(tmp_path)})
    out = TradingAgentsGraph.save_reports(mock_self, _state(), "AAPL")
    assert out.exists()
    assert out.parent.parent.name == "reports"  # results_dir/reports/AAPL_<stamp>/...
    assert out.parent.name.startswith("AAPL_")
