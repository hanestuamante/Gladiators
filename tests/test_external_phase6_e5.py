"""Phase 6 E5 offline acceptance fixtures and remaining edge cases."""
from __future__ import annotations

import json

from gladiators.agent.verifier import verify_numeric_claims
from gladiators.agent.wording import check_wording
from gladiators.external.cache import ExternalCache, QuotaGuard
from gladiators.external.injection_guard import sanitize_and_check
from gladiators.external.search_contracts import LiveSearchPlan, SearchResponse
from gladiators.external.search_executor import SearchExecutor
from gladiators.external.search_provider import ProviderError
from gladiators.runtime_factory import create_runtime
import pytest


def _fixture() -> SearchResponse:
    path = "tests/fixtures/external/live_search/ef16_campaign_id.json"
    return SearchResponse.model_validate_json(open(path, encoding="utf-8").read())


def test_external_eval_manifest_covers_ef13_through_ef24():
    suite = json.loads(open("eval/questions_external.json", encoding="utf-8").read())
    assert [case["id"] for case in suite] == [f"EF-{i:02d}" for i in range(13, 25)]


def test_runtime_factory_rejects_live_flag_without_source_review(monkeypatch):
    monkeypatch.setenv("GLADIATORS_ENABLE_LIVE_SEARCH", "1")
    monkeypatch.delenv("GLADIATORS_LIVE_SOURCE_REVIEWED", raising=False)
    monkeypatch.delenv("GLADIATORS_LIVE_SEARCH_LICENSE", raising=False)
    with pytest.raises(RuntimeError, match="source/license review"):
        create_runtime(provider="offline")


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
