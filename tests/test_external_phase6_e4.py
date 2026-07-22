"""Phase 6 E4: capability routing, runtime integration and Sources output."""
from __future__ import annotations

from datetime import datetime, timezone

from gladiators.agent.workflow import AgentRuntime
from gladiators.contracts import StructuredRequest
from gladiators.external.cache import ExternalCache, QuotaGuard
from gladiators.external.pipeline import ExternalContextPipeline
from gladiators.external.search_contracts import SearchQuery, SearchResponse, SearchResultItem
from gladiators.external.search_executor import SearchExecutor
from gladiators.external.search_planner import LiveSearchPlanner
from gladiators.external.search_provider import FakeSearchProvider, response_content_hash
from gladiators.external.web_extract import WebExtractor


NOW = datetime(2026, 7, 22, tzinfo=timezone.utc)
QUERY = "Shopee 7.7 campaign Indonesia 2026"


class FixtureP5P6:
    provider, model, prompt_version = "fake", "fixture", "p5-p6-v1"

    def plan_live_search(self, payload):
        return {
            "plan_id": "phase6-e4-fixture", "mode": payload["mode"],
            "queries": [{
                "query": QUERY, "market": payload["market"], "recency_days": 60,
                "purpose": payload["purpose"],
            }],
        }

    def extract_web(self, payload):
        snippet = payload["data"].split("\n", 1)[1].rsplit("\n", 1)[0]
        needle = "25 June to 7 July 2026"
        start = snippet.encode().find(needle.encode())
        return {
            **payload["fixed"], "claim_type": "campaign_window",
            "fields": {"window": needle},
            "spans": [{
                "field": "window", "text": needle, "start": start,
                "end": start + len(needle.encode()),
            }],
        }


def _response() -> SearchResponse:
    query = SearchQuery(
        query=QUERY, market="id", recency_days=60, purpose="campaign_context",
    )
    item = SearchResultItem(
        rank=1, title="7.7 Great Mid Year Sale", url="https://news.example.org/77",
        snippet="Campaign runs from 25 June to 7 July 2026.", score=0.9,
    )
    core = {
        "provider": "fake", "query": query.model_dump(mode="json"),
        "items": [item.model_dump(mode="json")], "retrieved_at": NOW.isoformat(),
    }
    return SearchResponse(
        **core, content_hash=response_content_hash(core), cache_path="unpersisted",
    )


def _pipeline(tmp_path, *, mode="record", provider=True):
    llm = FixtureP5P6()
    response = _response()
    adapter = FakeSearchProvider({QUERY: response}) if provider else None
    return ExternalContextPipeline(
        LiveSearchPlanner(llm),
        SearchExecutor(
            adapter, ExternalCache(tmp_path / "cache"),
            QuotaGuard(tmp_path / "quota.json", 10),
        ),
        WebExtractor(llm), mode=mode,
    )


def test_a16_blocks_cross_market_currency_before_planning(tmp_path):
    response = AgentRuntime(trace_dir=tmp_path).run(
        "So sánh doanh thu VN và ID rồi quy đổi USD bên nào cao hơn?"
    )
    assert response.gate.action == "clarify"
    assert response.gate.rule_id == "A16-CROSS-CURRENCY"
    assert response.tool_calls == []


def test_competitor_price_routes_to_exact_disabled_capability(tmp_path):
    response = AgentRuntime(trace_dir=tmp_path).run("Giá đối thủ ở Indonesia hiện tại là bao nhiêu?")
    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A14-EXT"
    assert "sources.external.enabled" in response.gate.reason


def test_campaign_context_names_live_flag_when_default_off(tmp_path):
    response = AgentRuntime(trace_dir=tmp_path).run("Lịch 7.7 ở Indonesia diễn ra khi nào?")
    assert response.request.intent == "external_context"
    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A14-LIVE"
    assert "sources.live_search.enabled" in response.gate.reason


def test_llm_parser_cannot_override_deterministic_external_route(tmp_path):
    class WrongParser:
        provider, model, prompt_version = "fake", "wrong-parser", "v1"

        def parse_intent(self, text, intent_names):
            return StructuredRequest(
                intent="promotion_effectiveness", country="id",
                slots={"raw_text": text}, language="vi",
            )

    response = AgentRuntime(
        trace_dir=tmp_path, llm_client=WrongParser(), use_llm_parser=True,
    ).run("Lịch 7.7 ở Indonesia diễn ra khi nào?")
    assert response.request.intent == "external_context"
    assert response.gate.rule_id == "A14-LIVE"
    assert "external_route_safety_precedence" in response.llm["parse_adjustments"]


def test_live_context_end_to_end_is_context_only_and_has_sources(tmp_path):
    runtime = AgentRuntime(
        trace_dir=tmp_path / "traces", external_pipeline=_pipeline(tmp_path),
        enable_live_search=True,
    )
    response = runtime.run("Lịch 7.7 ở Indonesia diễn ra khi nào?")
    assert response.gate.action == "allow"
    assert response.tool_calls[0].name == "live_search_context"
    assert response.tool_calls[0].status == "ok"
    assert len(response.evidence) == 1
    item = response.evidence[0]
    assert item.source_tier == "external"
    assert item.provenance is not None
    assert item.provenance.admission == "context_only"
    assert item.provenance.source_spans
    assert "Nguồn\n" in response.answer
    assert "[nguồn: live_web_search, lấy " in response.answer
    assert "chưa xác nhận cùng sản phẩm/thực thể" in response.answer
    assert response.verification["passed"] is True


def test_external_failure_ladder_abstains_without_crashing(tmp_path):
    runtime = AgentRuntime(
        trace_dir=tmp_path / "traces", external_pipeline=_pipeline(tmp_path, mode="cache_only", provider=False),
        enable_live_search=True,
    )
    response = runtime.run("Lịch 7.7 ở Indonesia diễn ra khi nào?")
    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A15-EXTERNAL-UNUSABLE"
    assert response.evidence == []
    assert response.tool_calls[0].status == "empty"


def test_cache_replay_keeps_external_values_and_hashes(tmp_path):
    recorded = _pipeline(tmp_path, mode="record", provider=True)
    replayed = _pipeline(tmp_path, mode="cache_only", provider=False)
    counter = iter(("ev:fixture:0001", "ev:fixture:0002"))
    first = recorded.run(
        "Lịch 7.7 ở Indonesia?", purpose="campaign_context", market="id",
        evidence_id=lambda: next(counter), dataset_version="fixture",
    )
    second = replayed.run(
        "Lịch 7.7 ở Indonesia?", purpose="campaign_context", market="id",
        evidence_id=lambda: next(counter), dataset_version="fixture",
    )
    assert first.evidence[0].value == second.evidence[0].value
    assert first.evidence[0].provenance.content_hash == second.evidence[0].provenance.content_hash
    assert second.cache_hits == 1 and second.provider_calls == 0
