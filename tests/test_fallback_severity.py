"""Expected, recoverable structured-output fallback must read as a WARN on
stdout, never as a red stderr block (PowerShell renders any child-process
stderr as a NativeCommandError, training users to ignore red output -- which
is dangerous once a genuine error also looks the same). A true unrecoverable
failure must keep using the existing stderr/failure path unchanged.

See fork README / completion report: "Expected fallbacks must be warnings,
not red errors"."""

from __future__ import annotations

import logging

import pytest

from tradingagents.agents.fallback_log import (
    fallback_count,
    reset_fallback_count,
    warn_fallback,
)
from tradingagents.agents.structured import bind_structured, invoke_structured_or_freetext
from tradingagents.prompts.loader import load_prompt

_logger = logging.getLogger("test_fallback_severity")


@pytest.fixture(autouse=True)
def _reset_counter():
    reset_fallback_count()
    yield
    reset_fallback_count()


# --- 1 & 2: warn_fallback writes stdout only, never stderr -------------------


@pytest.mark.unit
def test_warn_fallback_writes_to_stdout_with_warn_prefix(capsys):
    warn_fallback(_logger, "Bull Researcher: structured review unavailable; continuing with free-text fallback.")
    captured = capsys.readouterr()
    assert "[WARN] Bull Researcher: structured review unavailable" in captured.out
    assert captured.err == ""


@pytest.mark.unit
def test_warn_fallback_detail_does_not_leak_into_stdout(capsys, caplog):
    with caplog.at_level(logging.DEBUG, logger="test_fallback_severity"):
        warn_fallback(_logger, "Research Verifier: structured output unavailable; retrying with JSON fallback.",
                      detail="ValidationError: 3 fields failed")
    captured = capsys.readouterr()
    assert "ValidationError" not in captured.out  # detail stays out of normal output
    assert captured.err == ""
    assert any("ValidationError" in record.message for record in caplog.records)


# --- 3: fallback continues through the fallback path -------------------------


@pytest.mark.unit
def test_bind_structured_fallback_warns_on_stdout_and_continues(capsys):
    class _NoStructuredSupport:
        def with_structured_output(self, schema):
            raise NotImplementedError("not supported")

    result = bind_structured(_NoStructuredSupport(), object, "Trader")
    assert result is None  # continues: caller falls back to free text
    captured = capsys.readouterr()
    assert "[WARN] Trader: structured output unavailable" in captured.out
    assert captured.err == ""


@pytest.mark.unit
def test_invoke_structured_or_freetext_fallback_warns_and_still_returns_a_result(capsys):
    from types import SimpleNamespace

    class _FailingStructuredLLM:
        def invoke(self, prompt):
            raise ValueError("malformed json")

    class _PlainLLM:
        def invoke(self, prompt):
            return SimpleNamespace(content="plain prose result")

    result = invoke_structured_or_freetext(
        _FailingStructuredLLM(), _PlainLLM(), "prompt", lambda r: str(r), "Research Manager"
    )
    assert result == "plain prose result"  # pipeline continues normally
    captured = capsys.readouterr()
    assert "[WARN] Research Manager: structured output unavailable; retrying once" in captured.out
    assert captured.err == ""


@pytest.mark.unit
def test_risk_stance_fallback_warns_on_stdout_and_continues(capsys):
    from types import SimpleNamespace

    from tradingagents.agents.risk_mgmt.stance import invoke_risk_assessment

    class _FailingStructuredLLM:
        def invoke(self, prompt):
            raise ValueError("bad output")

    class _PlainLLM:
        def invoke(self, prompt):
            return SimpleNamespace(content="plain risk argument")

    rendered, risk_level, disposition, assessment = invoke_risk_assessment(
        _FailingStructuredLLM(), _PlainLLM(), "prompt", "Aggressive Analyst"
    )
    assert rendered == "plain risk argument"
    assert risk_level is None and disposition is None and assessment is None
    captured = capsys.readouterr()
    assert "[WARN] Aggressive Analyst: structured risk assessment unavailable" in captured.out
    assert captured.err == ""


@pytest.mark.unit
def test_research_verifier_json_fallback_warns_on_stdout():
    import io
    from contextlib import redirect_stderr, redirect_stdout

    from tradingagents.agents.researchers.research_verifier import _parse_freetext_result

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        result = _parse_freetext_result("not valid json at all")
    assert result.status.value == "WARN"
    assert "[WARN] Research Verifier: JSON fallback could not be validated" in out.getvalue()
    assert err.getvalue() == ""


# --- counting ----------------------------------------------------------------


@pytest.mark.unit
def test_fallback_count_increments_and_resets():
    assert fallback_count() == 0
    warn_fallback(_logger, "one")
    warn_fallback(_logger, "two")
    assert fallback_count() == 2
    reset_fallback_count()
    assert fallback_count() == 0


# --- 4: a genuine unrecoverable failure is unaffected, still raises ---------


@pytest.mark.unit
def test_missing_prompt_file_still_raises_not_a_warning(capsys):
    with pytest.raises(FileNotFoundError):
        load_prompt("risk_mgmt/this_file_does_not_exist.txt")
    captured = capsys.readouterr()
    assert "[WARN]" not in captured.out  # a real failure is not disguised as a warning
