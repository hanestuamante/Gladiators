"""Phase 6 E5 offline acceptance fixtures and remaining edge cases."""
from __future__ import annotations

import json
from pathlib import Path

from gladiators.agent.verifier import verify_numeric_claims
from gladiators.agent.wording import check_wording
from gladiators.external.cache import ExternalCache, QuotaGuard
from gladiators.external.injection_guard import sanitize_and_check
from gladiators.external.search_contracts import LiveSearchPlan, SearchResponse
from gladiators.external.search_executor import SearchExecutor
from gladiators.external.search_provider import ProviderError
from gladiators.external.search_provider import response_content_hash, response_core
from gladiators.runtime_factory import create_runtime
from gladiators.external.settings import load_external_settings
from gladiators.external.registry import build_source_registry
import pytest
from scripts.run_phase6_evaluation import run_suite


def _fixture() -> SearchResponse:
    path = "tests/fixtures/external/live_search/ef16_campaign_id.json"
    return SearchResponse.model_validate_json(open(path, encoding="utf-8").read())


W8_TAVILY_FIXTURES = {
    "w8_tavily_id_campaign.json": "37814e418f49f4d5d18d025d14f266ee3c624016711978ee0a4da57e9766faf6",
    "w8_tavily_vn_campaign.json": "210923133bc8f52a0f831b2fd5cd2fd9d36c2847b46f79d3dd47e46ac0a0fb64",
    "w8_tavily_global_event.json": "1c74065ea58ed369e1c92565853a3122a5bed938157cb1ecf5ac2c28f7c949b4",
}


def test_w8_real_tavily_fixtures_are_minimal_safe_and_hash_valid():
    root = Path("tests/fixtures/external/live_search")
    purposes = set()
    markets = set()
    for filename, expected_hash in W8_TAVILY_FIXTURES.items():
        raw = (root / filename).read_text(encoding="utf-8")
        assert "tvly-" not in raw.lower() and "authorization" not in raw.lower()
        response = SearchResponse.model_validate_json(raw)
        assert response.provider == "tavily"
        assert response.content_hash == expected_hash
        assert response_content_hash(response_core(response)) == expected_hash
        assert response.items and all(len(item.snippet) <= 200 for item in response.items)
        assert all(sanitize_and_check(item.title).safe for item in response.items)
        assert all(sanitize_and_check(item.snippet).safe for item in response.items)
        assert all("shopee." not in item.url.lower() for item in response.items)
        purposes.add(response.query.purpose)
        markets.add(response.query.market)
    assert purposes == {"campaign_context", "market_event"}
    assert markets == {"id", "vn", "global"}


def test_external_eval_manifest_covers_ef13_through_ef24():
    suite = json.loads(open("eval/questions_external.json", encoding="utf-8").read())
    assert [case["id"] for case in suite] == [f"EF-{i:02d}" for i in range(13, 25)]


def test_external_eval_manifest_is_executed_offline(tmp_path):
    report = run_suite(Path("eval/questions_external.json"), tmp_path)
    assert report["cases"] == 12
    assert report["passed"] == 12 and report["failed"] == 0
    assert [row["id"] for row in report["rows"]] == [f"EF-{i:02d}" for i in range(13, 25)]


def test_runtime_factory_default_does_not_create_external_pipeline(monkeypatch):
    monkeypatch.delenv("GLADIATORS_ENABLE_LIVE_SEARCH", raising=False)
    runtime = create_runtime(provider="offline")
    assert runtime.enable_live_search is False
    assert runtime.external_pipeline is None


def test_external_settings_environment_override_and_validation(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("""
sources:
  live_search:
    enabled: false
    provider: tavily
    mode: cache_only
    max_admission: context_only
    max_queries_per_request: 3
    max_results_per_query: 5
    daily_query_limit: 150
""", encoding="utf-8")
    settings = load_external_settings(config, environ={
        "GLADIATORS_ENABLE_LIVE_SEARCH": "1",
        "GLADIATORS_LIVE_SEARCH_MODE": "record",
        "GLADIATORS_LIVE_SEARCH_DAILY_LIMIT": "9",
    }).live_search
    assert settings.enabled is True and settings.mode == "record"
    assert settings.daily_query_limit == 9
    for invalid in (
        {"GLADIATORS_LIVE_SEARCH_MODE": "invalid"},
        {"GLADIATORS_LIVE_SEARCH_PROVIDER": "serpapi"},
        {"GLADIATORS_LIVE_SEARCH_MAX_RESULTS": "6"},
        {"GLADIATORS_LIVE_SEARCH_MAX_QUERIES": "0"},
    ):
        with pytest.raises(ValueError):
            load_external_settings(config, environ=invalid)
    registry = build_source_registry(settings)
    entry = registry.require_enabled("live_web_search")
    assert entry.allowed_domains == ("api.tavily.com",)
    assert entry.default_tier == "external" and entry.parser_id == "p6_web_extract"
    assert "demo" in entry.license and "license" not in entry.license.lower()


def test_cache_only_runtime_needs_no_tavily_key_and_filters_provider(monkeypatch):
    class NoopLLM:
        provider, model, prompt_version = "groq", "fixture", "v1"

    monkeypatch.setenv("GLADIATORS_ENABLE_LIVE_SEARCH", "1")
    monkeypatch.setenv("GLADIATORS_LIVE_SEARCH_MODE", "cache_only")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr("gladiators.runtime_factory.GroqLLMClient", NoopLLM)
    runtime = create_runtime(provider="groq")
    assert runtime.enable_live_search is True
    assert runtime.external_pipeline.executor.provider is None
    assert runtime.external_pipeline.executor.cache_provider_id == "tavily"


@pytest.mark.parametrize("mode", ["record", "live"])
def test_record_runtime_without_tavily_key_fails_before_network(monkeypatch, mode):
    class NoopLLM:
        provider, model, prompt_version = "groq", "fixture", "v1"

    monkeypatch.setenv("GLADIATORS_ENABLE_LIVE_SEARCH", "1")
    monkeypatch.setenv("GLADIATORS_LIVE_SEARCH_MODE", mode)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr("gladiators.runtime_factory.GroqLLMClient", NoopLLM)
    monkeypatch.setattr("gladiators.runtime_factory.load_dotenv", lambda: None)
    monkeypatch.setattr("gladiators.external.search_provider.load_dotenv", lambda: None)
    with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
        create_runtime(provider="groq")


def test_ef16_normalized_fixture_hash_is_valid(tmp_path):
    response = _fixture()
    stored = ExternalCache(tmp_path / "cache").write(response)
    assert ExternalCache(tmp_path / "cache").read(stored.content_hash) == stored


def test_ef12_implicit_causal_wording_is_blocked():
    for answer in (
        "Giá giảm nhờ chiến dịch 7.7.",
        "Chiến dịch kéo theo giá thấp hơn.",
        "Có campaign, vì vậy giá giảm.",
    ):
        assert any(item["rule"] == "causal_language" for item in check_wording(answer))


def test_ef18_retryable_provider_failure_retries_once_and_does_not_crash(tmp_path):
    response = _fixture()

    class TimeoutProvider:
        provider_id = "fake"

        def __init__(self):
            self.calls = 0

        def search(self, query, **kwargs):
            self.calls += 1
            raise ProviderError("fixture timeout", retryable=True)

    provider = TimeoutProvider()
    outcome = SearchExecutor(
        provider, ExternalCache(tmp_path / "cache"), QuotaGuard(tmp_path / "quota.json", 10),
    ).execute(LiveSearchPlan(plan_id="ef18", queries=(response.query,), mode="record"))
    assert provider.calls == 2
    assert outcome.provider_calls == 2
    assert outcome.responses == ()


def test_ef22_exhausted_quota_never_calls_provider(tmp_path):
    response = _fixture()

    class ForbiddenProvider:
        provider_id = "fake"

        def search(self, query, **kwargs):
            raise AssertionError("provider must not be called")

    quota = QuotaGuard(tmp_path / "quota.json", 1)
    quota.consume()
    outcome = SearchExecutor(
        ForbiddenProvider(), ExternalCache(tmp_path / "cache"), quota,
    ).execute(LiveSearchPlan(plan_id="ef22", queries=(response.query,), mode="record"))
    assert outcome.provider_calls == 0
    assert outcome.ladder_reason == "A15: quota exhausted"


def test_pipeline_quota_preflight_skips_search_planner(tmp_path):
    from gladiators.external.pipeline import ExternalContextPipeline
    from gladiators.external.search_executor import SearchExecutor
    from gladiators.external.web_extract import WebExtractor

    class ForbiddenPlanner:
        def plan(self, *args, **kwargs):
            raise AssertionError("P5 must not run when quota is already exhausted")

    quota = QuotaGuard(tmp_path / "quota.json", 1)
    quota.consume()
    executor = SearchExecutor(
        object(), ExternalCache(tmp_path / "cache"), quota,
    )
    pipeline = ExternalContextPipeline(
        ForbiddenPlanner(), executor, WebExtractor(None), mode="record",
    )
    result = pipeline.run(
        "campaign", purpose="campaign_context", market="id",
        evidence_id=lambda: "ev:test:0001", dataset_version="fixture",
    )
    assert result.plan_id is None and result.provider_calls == 0
    assert result.ladder_reason == "A15: quota exhausted"


def test_ef19_committed_injection_fixture_is_detected():
    fixture = json.loads(open(
        "tests/fixtures/external/live_search/ef19_injection.json", encoding="utf-8",
    ).read())
    result = sanitize_and_check(fixture["snippet"])
    assert "A17_IGNORE_INSTRUCTIONS" in result.hits
    assert "A17_FAKE_CITATION" in result.hits


def test_verifier_pass4_rejects_external_claim_without_inline_source_label():
    # model_construct deliberately bypasses contract validation to exercise the
    # verifier as a second independent line of defence.
    response = _fixture()
    from gladiators.contracts import Evidence
    from gladiators.external.admission import admit_live_record
    from gladiators.external.contracts import SourceSpan
    from gladiators.external.search_contracts import ExtractedWebRecord

    snippet = response.items[0].snippet
    needle = "25 June"
    start = snippet.encode().find(needle.encode())
    record = ExtractedWebRecord(
        raw_content_hash=response.content_hash, search_query=response.query.query,
        result_url=response.items[0].url, result_rank=1, claim_type="campaign_window",
        fields={"start": needle}, spans=(SourceSpan(
            field="start", text=needle, start=start, end=start + len(needle),
        ),), parser_id="p6_web_extract", schema_version="1.0",
    )
    admitted = admit_live_record(
        record, response, mapping_status="needs_review",
        observed_at=response.retrieved_at, license="public-facts-with-attribution",
    )
    evidence = Evidence(
        evidence_id="ev:ef16:0001", source_tier="external",
        metric="context.campaign_window", value=needle,
        source_locator=admitted.provenance.source_locator,
        dataset_version="fixture", provenance=admitted.provenance,
    )
    verdict = verify_numeric_claims(f"Bối cảnh {needle} [ev:ef16:0001].", [evidence])
    assert verdict["passed"] is False
    assert {gap["reason"] for gap in verdict["source_label_gaps"]} == {
        "missing_inline_source_or_retrieved_at", "missing_needs_review_label",
    }
