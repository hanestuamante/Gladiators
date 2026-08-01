"""Search record/replay — ultimate solution §16 P12.

The load-bearing test is ``test_a_replay_miss_never_falls_back_to_the_network``.
Everything else here is bookkeeping; that one is the difference between a
regression suite and a live integration test that happens to pass.
"""
from __future__ import annotations

import pytest

from gladiators.external.record_replay import (
    CassetteStore,
    RecordingSearchProvider,
    ReplayMiss,
    ReplaySearchProvider,
    cassette_key,
    verify_determinism,
)
from gladiators.external.search_contracts import (
    SearchQuery,
    SearchResponse,
    SearchResultItem,
)
from gladiators.external.search_provider import response_content_hash


class StubProvider:
    provider_id = "fake"

    def __init__(self):
        self.calls = 0

    def search(self, query, *, max_results=5, timeout_s=10.0) -> SearchResponse:
        self.calls += 1
        items = [SearchResultItem(
            rank=1, title=f"kết quả {self.calls}", url="https://example.com/a",
            snippet="nội dung", score=0.9, published_at=None,
        )]
        core = {
            "provider": "fake", "query": query.model_dump(mode="json"),
            "items": [i.model_dump(mode="json") for i in items],
            "retrieved_at": "2026-07-31T00:00:00+00:00",
        }
        return SearchResponse(
            **core, content_hash=response_content_hash(core), cache_path="unpersisted",
        )


class ExplodingProvider:
    provider_id = "exploding"

    def search(self, *a, **k):
        raise AssertionError("replay đã gọi ra mạng")


def query(text: str = "chiến dịch 7.7 shopee", market: str = "vn") -> SearchQuery:
    return SearchQuery(query=text, market=market, purpose="campaign_context",
                       recency_days=7)


@pytest.fixture
def store(tmp_path) -> CassetteStore:
    return CassetteStore(tmp_path / "cassettes")


# --- keys -----------------------------------------------------------------

def test_key_is_content_addressed():
    assert cassette_key(query()) == cassette_key(query())
    assert cassette_key(query("aaa")) != cassette_key(query("bbb"))


def test_market_changes_the_key():
    """The same words asked of VN and ID are two different questions."""
    assert cassette_key(query(market="vn")) != cassette_key(query(market="id"))


def test_recency_window_changes_the_key():
    """It changes the request window, so it changes the answer."""
    a = SearchQuery(query="xyz", market="vn", purpose="campaign_context", recency_days=7)
    b = SearchQuery(query="xyz", market="vn", purpose="campaign_context", recency_days=30)
    assert cassette_key(a) != cassette_key(b)


def test_recording_time_never_enters_the_key(store):
    """A cassette recorded yesterday must still replay today."""
    RecordingSearchProvider(StubProvider(), store).search(query())
    payload = store.read(cassette_key(query()))
    assert "recorded_at" in payload
    assert payload["key"] == cassette_key(query())


# --- recording ------------------------------------------------------------

def test_recording_saves_what_came_back(store):
    provider = RecordingSearchProvider(StubProvider(), store)
    response = provider.search(query())
    assert store.has(cassette_key(query()))
    assert provider.recorded == [cassette_key(query())]
    assert response.items[0].url == "https://example.com/a"


def test_recording_does_not_re_call_for_an_existing_cassette(store):
    inner = StubProvider()
    provider = RecordingSearchProvider(inner, store)
    provider.search(query())
    provider.search(query())
    assert inner.calls == 1


def test_overwrite_forces_a_fresh_call(store):
    inner = StubProvider()
    RecordingSearchProvider(inner, store).search(query())
    RecordingSearchProvider(inner, store, overwrite=True).search(query())
    assert inner.calls == 2


# --- replay ---------------------------------------------------------------

def test_replay_serves_from_the_cassette(store):
    recorded = RecordingSearchProvider(StubProvider(), store).search(query())
    replayed = ReplaySearchProvider(store).search(query())
    assert replayed.content_hash == recorded.content_hash
    assert replayed.items[0].url == recorded.items[0].url


def test_a_replay_miss_never_falls_back_to_the_network(store):
    """A suite that reaches out on a miss stops being a regression test the
    moment anyone adds a case, and the passing run looks identical."""
    provider = ReplaySearchProvider(store)
    with pytest.raises(ReplayMiss) as excinfo:
        provider.search(query("chưa từng ghi"))
    assert excinfo.value.code == "SEARCH_REPLAY_MISS"


def test_replay_provider_holds_no_network_provider(store):
    """Structural, not behavioural: it has nothing to fall back to."""
    provider = ReplaySearchProvider(store)
    assert not hasattr(provider, "inner")


def test_a_corrupt_cassette_is_a_miss_not_a_partial_answer(store):
    RecordingSearchProvider(StubProvider(), store).search(query())
    store.path_for(cassette_key(query())).write_text("{ broken", encoding="utf-8")
    with pytest.raises(ReplayMiss):
        ReplaySearchProvider(store).search(query())


# --- determinism ×3 -------------------------------------------------------

def test_replay_three_times_is_byte_stable(store):
    queries = [query("chiến dịch 7.7"), query("ngày đôi 8.8")]
    recorder = RecordingSearchProvider(StubProvider(), store)
    for item in queries:
        recorder.search(item)

    report = verify_determinism(ReplaySearchProvider(store), queries, runs=3)
    assert report["stable"] is True
    assert report["runs"] == 3
    assert report["queries"] == 2
    assert report["unstable"] == {}


def test_determinism_check_reports_instability_rather_than_hiding_it(store):
    """A drifting provider must surface, not average out."""
    class DriftingProvider(ReplaySearchProvider):
        def __init__(self, store):
            super().__init__(store)
            self._n = 0

        def search(self, q, *, max_results=5, timeout_s=10.0):
            self._n += 1
            base = super().search(q, max_results=max_results, timeout_s=timeout_s)
            return base.model_copy(update={"content_hash": f"{base.content_hash}-{self._n}"})

    RecordingSearchProvider(StubProvider(), store).search(query())
    report = verify_determinism(DriftingProvider(store), [query()], runs=3)
    assert report["stable"] is False
    assert report["unstable"]


# --- negative rehearsal ---------------------------------------------------

def test_negative_rehearsal_provider_outage_does_not_reach_replay(store):
    """Recording is where an outage belongs; replay must be unaffected."""
    class FailingProvider:
        provider_id = "failing"

        def search(self, *a, **k):
            raise RuntimeError("provider down")

    RecordingSearchProvider(StubProvider(), store).search(query())
    with pytest.raises(RuntimeError, match="provider down"):
        RecordingSearchProvider(FailingProvider(), store).search(query("khác"))
    # The previously recorded cassette still replays.
    assert ReplaySearchProvider(store).search(query()).items


def test_store_lists_its_keys(store):
    RecordingSearchProvider(StubProvider(), store).search(query("aaa"))
    RecordingSearchProvider(StubProvider(), store).search(query("bbb"))
    assert len(store.keys()) == 2
