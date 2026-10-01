"""Azure OpenAI client: provider labeling and reasoning-tier parameter gating.

Azure deployments named after a reasoning-tier model (o-series, GPT-5+) reject
``reasoning_effort``/non-default ``temperature`` exactly like native OpenAI
does; the fix mirrors the guard already proven for openai_client.py.
"""

import pytest

from tradingagents.llm_clients.azure_client import AzureOpenAIClient


@pytest.mark.unit
def test_get_provider_name_is_azure_not_azureopenai():
    client = AzureOpenAIClient("gpt-4.1")
    assert client.get_provider_name() == "azure"


@pytest.mark.unit
def test_reasoning_tier_deployment_receives_effort_but_drops_temperature(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_NAME", raising=False)
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-03-01-preview")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    llm = AzureOpenAIClient(
        "gpt-5.4-mini", api_key="test-key", reasoning_effort="low", temperature=0.2
    ).get_llm()
    assert getattr(llm, "reasoning_effort", None) == "low"
    assert llm.temperature is None


@pytest.mark.unit
def test_non_reasoning_deployment_drops_effort_but_keeps_temperature(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_NAME", raising=False)
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-03-01-preview")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    llm = AzureOpenAIClient(
        "gpt-4.1", api_key="test-key", reasoning_effort="low", temperature=0.2
    ).get_llm()
    assert getattr(llm, "reasoning_effort", None) is None
    assert llm.temperature == 0.2
