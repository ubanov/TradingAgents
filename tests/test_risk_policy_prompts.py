"""Static prompt/schema-description checks: the wording that used to cause
adversarial, role-defending, invent-your-own-numbers behavior in Risk
Management (and portfolio-sizing assumptions elsewhere) must be gone, and the
new provenance-restriction wording must be present (see fork README: "Risk as
independent assessment + one cross-review")."""

from __future__ import annotations

import pytest

from tradingagents.agents.schemas import PortfolioDecision, ResearchPlan, TraderProposal
from tradingagents.prompts.loader import load_prompt

_AGGRESSIVE_PROMPTS = ["risk_mgmt/aggressive_initial.txt", "risk_mgmt/aggressive_review.txt"]
_CONSERVATIVE_PROMPTS = ["risk_mgmt/conservative_initial.txt", "risk_mgmt/conservative_review.txt"]
_NEUTRAL_PROMPTS = ["risk_mgmt/neutral_initial.txt", "risk_mgmt/neutral_review.txt"]
_ALL_RISK_PROMPTS = _AGGRESSIVE_PROMPTS + _CONSERVATIVE_PROMPTS + _NEUTRAL_PROMPTS

_ADVERSARIAL_PHRASES = (
    "champion", "challenge the opposing", "best path forward", "outpace market norms",
    "demonstrate why", "underscore why", "counter the arguments", "actively counter",
    "showcase why", "strength of a low-risk strategy over their approaches",
    "best of both worlds", "most reliable outcomes",
)


@pytest.mark.unit
@pytest.mark.parametrize("path", _ALL_RISK_PROMPTS)
def test_risk_prompts_contain_no_adversarial_role_defending_language(path):
    text = load_prompt(path).lower()
    for phrase in _ADVERSARIAL_PHRASES:
        assert phrase not in text, f"{path} still contains adversarial phrase: {phrase!r}"


@pytest.mark.unit
@pytest.mark.parametrize("path", _AGGRESSIVE_PROMPTS)
def test_aggressive_prompt_does_not_instruct_to_prove_aggressive_is_best(path):
    text = load_prompt(path).lower()
    assert "best path forward" not in text
    assert "optimal" not in text


@pytest.mark.unit
def test_aggressive_initial_explicitly_allows_concluding_no():
    text = load_prompt("risk_mgmt/aggressive_initial.txt")
    assert "you may conclude no" in text.lower()
    assert "not required to recommend more risk" in text.lower()


@pytest.mark.unit
@pytest.mark.parametrize("path", _CONSERVATIVE_PROMPTS)
def test_conservative_prompt_does_not_instruct_to_prove_conservative_is_best(path):
    text = load_prompt(path).lower()
    assert "safest path" not in text
    assert "strength of a low-risk strategy" not in text


@pytest.mark.unit
def test_conservative_initial_explicitly_allows_concluding_risk_is_controlled():
    text = load_prompt("risk_mgmt/conservative_initial.txt").lower()
    assert "already controls the risk" in text
    assert "goal in itself" in text  # explicitly disclaims minimizing risk as the goal


@pytest.mark.unit
@pytest.mark.parametrize("path", _NEUTRAL_PROMPTS)
def test_neutral_prompt_does_not_instruct_to_find_a_compromise(path):
    text = load_prompt(path).lower()
    assert "do not aim for" in text and "compromise" in text
    assert "best of both worlds" not in text
    assert "most reliable outcomes" not in text


@pytest.mark.unit
@pytest.mark.parametrize("path", _ALL_RISK_PROMPTS)
def test_risk_prompts_prohibit_new_external_evidence(path):
    text = load_prompt(path).lower()
    assert "frozen evidence" in text
    assert "do not introduce" in text


@pytest.mark.unit
@pytest.mark.parametrize("path", _ALL_RISK_PROMPTS)
def test_risk_prompts_prohibit_invented_sizing_and_thresholds(path):
    text = load_prompt(path).lower()
    assert "new thresholds" in text or "sizing percentage" in text or "replacement level" in text


@pytest.mark.unit
def test_portfolio_manager_prompt_says_risk_is_assessment_not_evidence():
    text = load_prompt("managers/portfolio_manager.txt")
    assert "assessments, not new evidence" in text


@pytest.mark.unit
def test_research_manager_no_longer_assumes_standard_allocation():
    prompt_text = load_prompt("managers/research_manager.txt")
    assert "standard allocation" not in prompt_text
    assert "standard allocation" not in (ResearchPlan.model_fields["strategic_actions"].description or "")


@pytest.mark.unit
def test_trader_does_not_invent_portfolio_sizing_without_portfolio_context():
    user_prompt = load_prompt("trader/user.txt").lower()
    assert "unless the portfolio context" in user_prompt or "only if the portfolio context" in user_prompt
    description = (TraderProposal.model_fields["position_sizing"].description or "").lower()
    assert "portfolio context" in description
    assert "5% of portfolio" not in description


@pytest.mark.unit
def test_portfolio_manager_decision_does_not_invent_sizing_in_its_own_description():
    description = (PortfolioDecision.model_fields["executive_summary"].description or "").lower()
    assert "do not invent" in description
