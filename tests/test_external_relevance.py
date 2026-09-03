"""Phase 6 relevance pre-filter: gate deterministic loại item lạc đề trước P6."""
from __future__ import annotations

from datetime import datetime, timezone

from gladiators.external.cache import ExternalCache, QuotaGuard
from gladiators.external.pipeline import ExternalContextPipeline
from gladiators.external.relevance import is_relevant, query_signal_tokens
from gladiators.external.search_contracts import SearchQuery, SearchResponse, SearchResultItem
from gladiators.external.search_executor import SearchExecutor
from gladiators.external.search_planner import LiveSearchPlanner
from gladiators.external.search_provider import FakeSearchProvider, response_content_hash
from gladiators.external.web_extract import WebExtractor


NOW = datetime(2026, 7, 22, tzinfo=timezone.utc)
QUERY = "Shopee 7.7 campaign Indonesia 2026"


def _q(query: str, market: str) -> SearchQuery:
    return SearchQuery(query=query, market=market, recency_days=60, purpose="campaign_context")


def _item(title: str, snippet: str, rank: int = 1) -> SearchResultItem:
    return SearchResultItem(
        rank=rank, title=title, url=f"https://news.example.org/{rank}", snippet=snippet, score=0.5,
    )


# ---- unit: giữ hit thật ----

def test_keeps_genuine_market_matched_result():
    vn = _q("Vietnam online shopping campaign July 2026 dates", "vn")
    item = _item(
        "Vietnam Grand Sale 2026 to run nationwide in July",
        "The first Vietnam Grand Sale in 2026 will take place from July 1-31.",
    )
    assert is_relevant(vn, item)  # trùng "vietnam" + "july"


def test_keeps_result_sharing_only_campaign_anchor():
    # Bug đã tránh: hit chỉ trùng anchor "7.7" (không nhắc market trong snippet) vẫn giữ.
    idq = _q(QUERY, "id")
    item = _item("7.7 Great Mid Year Sale", "Campaign runs from 25 June to 7 July 2026.")
    assert is_relevant(idq, item)


# ---- unit: loại rác ----

def test_drops_zero_overlap_garbage():
    vn = _q("Vietnam 7.7 ecommerce shopping campaign 2026 dates", "vn")
    for title in (
        "Envision Horizons Analysis of Amazon Prime Day 2026",
        "Vietjet unveils 10-day super sale with half-price flights",
        "New Ecommerce Tools: June 24, 2026 - Practical Ecommerce",
    ):
        assert not is_relevant(vn, _item(title, title))


def test_generic_commerce_words_alone_do_not_rescue_garbage():
    # "ecommerce"/"shopping"/"2026" là stopword — không đủ để coi là liên quan.
    vn = _q("Vietnam online shopping campaign 2026", "vn")
    assert not is_relevant(vn, _item("Global ecommerce shopping trends 2026", "online shopping grew"))


def test_fail_open_when_query_has_no_discriminative_signal():
    # Query rỗng nghĩa (chỉ stopword) → không đủ cơ sở để loại → giữ, để P6 quyết.
    thin = _q("shopping ecommerce 2026 sale", "global")
    assert query_signal_tokens(thin) == set()
    assert is_relevant(thin, _item("Anything at all", "unrelated text"))


# ---- pipeline: prefilter đếm đúng và không tốn P6 cho rác ----

class _FixtureP5P6:
    provider, model, prompt_version = "fake", "fixture", "p5-p6-v1"

    def __init__(self):
        self.extract_calls = 0

    def plan_live_search(self, payload):
        return {
            "plan_id": "relevance-fixture", "mode": payload["mode"],
            "queries": [{
                "query": QUERY, "market": payload["market"], "recency_days": 60,
                "purpose": payload["purpose"],
            }],
        }

    def extract_web(self, payload):
        self.extract_calls += 1
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


def _two_item_response() -> SearchResponse:
    query = _q(QUERY, "id")
    relevant = _item("7.7 Great Mid Year Sale", "Campaign runs from 25 June to 7 July 2026.", rank=1)
    garbage = _item("Vietjet cheap flights to Bali", "Cheap weekend flights and baggage deals.", rank=2)
    core = {
        "provider": "fake", "query": query.model_dump(mode="json"),
        "items": [relevant.model_dump(mode="json"), garbage.model_dump(mode="json")],
        "retrieved_at": NOW.isoformat(),
    }
    return SearchResponse(**core, content_hash=response_content_hash(core), cache_path="unpersisted")


def test_pipeline_prefilters_garbage_and_spares_p6(tmp_path):
    llm = _FixtureP5P6()
    adapter = FakeSearchProvider({QUERY: _two_item_response()})
    pipeline = ExternalContextPipeline(
        LiveSearchPlanner(llm),
        SearchExecutor(adapter, ExternalCache(tmp_path / "cache"), QuotaGuard(tmp_path / "quota.json", 10)),
        WebExtractor(llm), mode="record",
    )
    seq = {"n": 0}

    def _evidence_id() -> str:
        seq["n"] += 1
        return f"ev:test:{seq['n']:04d}"

    outcome = pipeline.run(
        "Lịch 7.7 ở Indonesia diễn ra khi nào?", purpose="campaign_context", market="id",
        evidence_id=_evidence_id, dataset_version="v-test",
    )
    assert outcome.prefiltered_count == 1     # item rác bị loại trước P6
    assert llm.extract_calls == 1             # P6 chỉ chạy cho item hợp lệ, không cho rác
    assert len(outcome.evidence) == 1
