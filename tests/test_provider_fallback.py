"""FallbackLLMClient: DeepSeek primary, Groq spare."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from gladiators.agent.llm import DeepSeekLLMClient, FallbackLLMClient


class _Primary:
    provider = "deepseek"
    prompt_version = "v1.1.0"

    def __init__(self, fail: Exception | None = None):
        self.fail, self.calls = fail, 0

    def plan_analytical(self, payload):
        self.calls += 1
        if self.fail:
            raise self.fail
        return {"from": "primary"}

    def telemetry(self):
        return {"api_calls": self.calls}


class _Spare:
    provider = "groq"

    def __init__(self):
        self.calls = 0

    def plan_analytical(self, payload):
        self.calls += 1
        return {"from": "spare"}

    def telemetry(self):
        return {"api_calls": self.calls}


def test_primary_result_is_used_and_spare_stays_untouched():
    primary, spare = _Primary(), _Spare()
    client = FallbackLLMClient(primary, spare)
    assert client.plan_analytical({}) == {"from": "primary"}
    assert (primary.calls, spare.calls) == (1, 0)
    assert client.provider == "deepseek+groq"


def test_transport_failure_degrades_to_the_spare():
    primary, spare = _Primary(fail=RuntimeError("DeepSeek request thất bại")), _Spare()
    client = FallbackLLMClient(primary, spare)
    assert client.plan_analytical({}) == {"from": "spare"}
    assert client.fallback_calls["plan_analytical"] == 1
    assert client.telemetry()["fallback"]["api_calls"] == 1


def test_contract_violation_is_not_retried_on_the_spare():
    # A ValidationError means the model answered but broke the schema; the
    # caller's bounded repair loop owns that. Retrying would double the budget.
    class _Broken(_Primary):
        def plan_analytical(self, payload):
            raise ValidationError.from_exception_data("LogicalQueryPlan", [])

    spare = _Spare()
    with pytest.raises(ValidationError):
        FallbackLLMClient(_Broken(), spare).plan_analytical({})
    assert spare.calls == 0


def test_capability_probe_still_reports_missing_methods():
    # open_planner decides what a provider supports with hasattr(); the proxy
    # must not make every attribute look present.
    client = FallbackLLMClient(_Primary(), _Spare())
    assert hasattr(client, "plan_analytical")
    assert not hasattr(client, "critique_plan")


def test_deepseek_client_requires_key_and_explicit_model(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        DeepSeekLLMClient()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    # No silent default model: an unverified name must fail here, not at runtime.
    with pytest.raises(RuntimeError, match="DEEPSEEK_MODEL"):
        DeepSeekLLMClient()
