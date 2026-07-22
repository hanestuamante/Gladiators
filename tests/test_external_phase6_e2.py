"""Phase 6 E2: provider boundary, immutable cache and quota guard."""
from __future__ import annotations

import json
import socket
from datetime import date, datetime, timezone

import pytest

from gladiators.external.cache import CacheIntegrityError, ExternalCache, QuotaGuard
from gladiators.external.search_contracts import SearchQuery, SearchResponse, SearchResultItem
from gladiators.external.search_provider import (
    FakeSearchProvider, TavilyProvider, response_content_hash,
)


def _query(text="Shopee 7.7 campaign 2026") -> SearchQuery:
    return SearchQuery(
        query=text, market="id", recency_days=60, purpose="campaign_context",
    )


def _response(query: SearchQuery | None = None) -> SearchResponse:
    query = query or _query()
    core = {
        "provider": "fake", "query": query.model_dump(mode="json"),
        "items": [SearchResultItem(
            rank=1, title="7.7 Great Mid Year Sale",
            url="https://example.com/news/77", snippet="Campaign runs from 25 June to 7 July.",
            score=0.9, published_at=date(2026, 6, 25),
        ).model_dump(mode="json")],
        "retrieved_at": datetime(2026, 7, 22, tzinfo=timezone.utc).isoformat(),
    }
    return SearchResponse(
        **core, content_hash=response_content_hash(core), cache_path="unpersisted",
    )


def test_tavily_provider_requires_secret_and_does_not_enable_itself(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr("gladiators.external.search_provider.load_dotenv", lambda: None)
    with pytest.raises(RuntimeError, match="Thiếu TAVILY_API_KEY"):
        TavilyProvider()


def test_fake_provider_is_typed_and_bounded():
    query = _query()
    fixture = _response(query)
    provider = FakeSearchProvider({query.query: fixture})
    result = provider.search(query, max_results=1)
    assert result == fixture
    assert provider.calls == [query.query]


def test_cache_roundtrip_is_content_addressed_and_socket_free(tmp_path, monkeypatch):
    cache = ExternalCache(tmp_path / "external_cache")
    stored = cache.write(_response())
    assert stored.cache_path.endswith(f"{stored.content_hash}.json")
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("cache_only không được mở socket")
    ))
    replay = cache.read(stored.content_hash)
    assert replay == stored
    manifest = json.loads((cache.root / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["entries"]) == 1


def test_cache_rejects_wrong_hash_and_detects_tampering(tmp_path):
    cache = ExternalCache(tmp_path / "external_cache")
    response = _response()
    with pytest.raises(CacheIntegrityError, match="không khớp"):
        cache.write(response.model_copy(update={"content_hash": "b" * 64}))

    stored = cache.write(response)
    path = cache._path(stored.content_hash)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["items"][0]["snippet"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CacheIntegrityError, match="verification"):
        cache.read(stored.content_hash)


def test_cache_write_is_idempotent(tmp_path):
    cache = ExternalCache(tmp_path / "external_cache")
    first = cache.write(_response())
    second = cache.write(_response())
    assert first == second
    assert len(cache._manifest().entries) == 1


def test_quota_guard_resets_by_day_and_blocks_over_limit(tmp_path):
    guard = QuotaGuard(tmp_path / "quota.json", daily_limit=3)
    day1, day2 = date(2026, 7, 22), date(2026, 7, 23)
    assert guard.used(day1) == 0
    assert guard.consume(2, day1) == 2
    assert guard.exhausted(2, day1) is True
    with pytest.raises(RuntimeError, match="quota exhausted"):
        guard.consume(2, day1)
    assert guard.used(day2) == 0
    assert guard.consume(1, day2) == 1
