"""Direct unit tests for apply_trade_plan_changes: the KEEP/REVISE/WITHDRAW
provenance invariant shared by normal review rounds and repair.

The invariant: a value that was REVISED or WITHDRAWN must never later be
treated as active verified provenance. KEEP must leave provenance unchanged.
"""

from __future__ import annotations

import pytest

from tradingagents.agents.researchers.thesis_flow import apply_trade_plan_changes


def _thesis(stop_loss=178.0, take_profit=210.0, entry_price=189.5):
    return {
        "entry": {"type": "point", "price": entry_price, "low": None, "high": None},
        "take_profit": take_profit,
        "stop_loss": stop_loss,
    }


def _review(entry=None, take_profit=None, stop_loss=None):
    def _change(spec):
        return spec or {"action": "KEEP"}

    return {
        "trade_plan_changes": {
            "entry": _change(entry),
            "take_profit": _change(take_profit),
            "stop_loss": _change(stop_loss),
        }
    }


@pytest.mark.unit
def test_keep_leaves_the_active_value_and_provenance_unchanged():
    thesis = _thesis()
    updated, retired = apply_trade_plan_changes(thesis, _review())
    assert updated["stop_loss"] == 178.0
    assert updated["take_profit"] == 210.0
    assert updated["entry"]["price"] == 189.5
    assert retired == []


@pytest.mark.unit
def test_withdraw_retires_the_actual_current_value():
    thesis = _thesis(take_profit=210.0)
    updated, retired = apply_trade_plan_changes(
        thesis, _review(take_profit={"action": "WITHDRAW", "old": 999999})
    )
    assert updated["take_profit"] is None
    # The actual thesis value is retired, never the LLM's self-reported "old".
    assert retired == [210.0]


@pytest.mark.unit
def test_revise_retires_the_old_value_and_activates_the_new_one():
    thesis = _thesis(stop_loss=178.0)
    updated, retired = apply_trade_plan_changes(
        thesis, _review(stop_loss={"action": "REVISE", "new": 170.0})
    )
    assert updated["stop_loss"] == 170.0
    assert retired == [178.0]


@pytest.mark.unit
def test_revise_to_the_same_value_retires_nothing():
    """A REVISE that merely restates the current number isn't really a
    change; treating it as retired would wrongly flag the still-current
    value as 'reused' the next time it's cited."""
    thesis = _thesis(stop_loss=178.0)
    updated, retired = apply_trade_plan_changes(
        thesis, _review(stop_loss={"action": "REVISE", "new": 178.0})
    )
    assert updated["stop_loss"] == 178.0
    assert retired == []


@pytest.mark.unit
def test_revised_away_value_is_no_longer_active_even_without_a_later_citation():
    """The invariant holds structurally, not just via the retired list: once
    REVISED, the old value simply isn't present anywhere in the updated
    thesis, so a provenance pool built from it can never contain it."""
    thesis = _thesis(stop_loss=178.0)
    updated, _ = apply_trade_plan_changes(
        thesis, _review(stop_loss={"action": "REVISE", "new": 170.0})
    )
    assert 178.0 not in updated.values()
    assert updated["stop_loss"] == 170.0


@pytest.mark.unit
def test_withdraw_on_an_already_absent_field_retires_nothing():
    thesis = _thesis(take_profit=None)
    updated, retired = apply_trade_plan_changes(
        thesis, _review(take_profit={"action": "WITHDRAW"})
    )
    assert updated["take_profit"] is None
    assert retired == []


@pytest.mark.unit
def test_entry_range_revise_retires_the_midpoint_reference():
    thesis = {
        "entry": {"type": "range", "price": None, "low": 82900, "high": 83300},
        "take_profit": None,
        "stop_loss": None,
    }
    updated, retired = apply_trade_plan_changes(
        thesis, _review(entry={"action": "REVISE", "new": 90000})
    )
    assert updated["entry"] == {"type": "point", "price": 90000, "low": None, "high": None}
    assert retired == [pytest.approx(83100)]


@pytest.mark.unit
def test_multiple_fields_changed_in_one_review_retire_independently():
    thesis = _thesis(entry_price=189.5, take_profit=210.0, stop_loss=178.0)
    updated, retired = apply_trade_plan_changes(
        thesis,
        _review(
            entry={"action": "KEEP"},
            take_profit={"action": "WITHDRAW"},
            stop_loss={"action": "REVISE", "new": 170.0},
        ),
    )
    assert updated["entry"]["price"] == 189.5
    assert updated["take_profit"] is None
    assert updated["stop_loss"] == 170.0
    assert set(retired) == {210.0, 178.0}
