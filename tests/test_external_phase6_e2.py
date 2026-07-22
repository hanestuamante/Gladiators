"""Phase 6 E2: provider boundary, immutable cache and quota guard."""
from __future__ import annotations

import json
import socket
import ssl
import urllib.error
from datetime import date, datetime, timezone
from email.message import Message

import pytest

from gladiators.external.cache import CacheIntegrityError, ExternalCache, QuotaGuard
from gladiators.external.search_contracts import SearchQuery, SearchResponse, SearchResultItem
from gladiators.external.search_provider import (
    FakeSearchProvider, ProviderError, TavilyProvider, response_content_hash,
)
from gladiators.external.search_executor import SearchExecutor
from gladiators.external.search_contracts import LiveSearchPlan


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


def test_tavily_default_opener_keeps_certificate_and_hostname_verification():
    provider = TavilyProvider(api_key="test-not-real")
    https = next(
        handler for handler in provider._opener.handlers
        if isinstance(handler, __import__("urllib.request").request.HTTPSHandler)
    )
    assert https._context.verify_mode == ssl.CERT_REQUIRED
    assert https._context.check_hostname is True


class _HTTPResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.payload[:limit]


class _CapturingOpener:
    def __init__(self, payload: dict):
        self.payload = payload
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return _HTTPResponse(json.dumps(self.payload).encode())


def test_tavily_http_contract_uses_start_date_and_disables_generated_content():
    opener = _CapturingOpener({"results": [{
        "title": "Campaign", "url": "https://news.example.com/event",
        "content": "Campaign starts 7 July.", "score": 0.9,
    }]})
    provider = TavilyProvider(
        api_key="test-secret-not-real", opener=opener,
        clock=lambda: datetime(2026, 7, 22, tzinfo=timezone.utc),
    )
    result = provider.search(_query(), max_results=99)
    request, timeout = opener.requests[0]
    body = json.loads(request.data)
    assert request.full_url == "https://api.tavily.com/search"
    assert request.get_header("Authorization") == "Bearer test-secret-not-real"
    assert request.get_header("Content-type") == "application/json"
    assert body == {
        "query": "Shopee 7.7 campaign 2026", "search_depth": "basic",
        "max_results": 5, "topic": "news", "include_answer": False,
        "include_raw_content": False, "include_images": False,
        "start_date": "2026-05-23",
    }
    assert "days" not in body
    assert timeout == 10.0
    assert result.provider == "tavily" and len(result.items) == 1


def test_tavily_missing_optional_result_fields_are_safe():
    opener = _CapturingOpener({"results": [
        {"url": "https://news.example.com/empty"},
        {"title": "missing url", "content": "ignored"},
    ]})
    result = TavilyProvider(
        api_key="test", opener=opener,
        clock=lambda: datetime(2026, 7, 22, tzinfo=timezone.utc),
    ).search(_query())
    assert len(result.items) == 1
    assert result.items[0].title == "" and result.items[0].snippet == ""


@pytest.mark.parametrize("status,retryable,quota", [
    (400, False, False), (401, False, False), (403, False, False),
    (429, True, False), (432, False, True),
    (433, False, True), (500, True, False), (302, False, False),
])
def test_tavily_http_error_taxonomy(status, retryable, quota):
    headers = Message()
    if status == 429:
        headers["Retry-After"] = "3"

    class ErrorOpener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(request.full_url, status, "fixture", headers, None)

    provider = TavilyProvider(api_key="test", opener=ErrorOpener())
    with pytest.raises(ProviderError) as captured:
        provider.search(_query())
    assert captured.value.retryable is retryable
    assert captured.value.quota_exhausted is quota
    assert captured.value.retry_after_s == (3.0 if status == 429 else None)


def test_tavily_rejects_response_over_two_megabytes():
    opener = _CapturingOpener({})
    opener.payload = None

    def oversized(request, timeout):
        return _HTTPResponse(b"x" * 2_000_001)

    opener.open = oversized
    with pytest.raises(ProviderError, match="2MB") as captured:
        TavilyProvider(api_key="test", opener=opener).search(_query())
    assert captured.value.retryable is False


def test_tavily_invalid_json_is_non_retryable_and_quarantines_only_metadata(tmp_path):
    query = _query("campaign invalid response")
    opener = _CapturingOpener({})
    opener.open = lambda request, timeout: _HTTPResponse(b"not-json secret body")
    provider = TavilyProvider(
        api_key="test", opener=opener,
        clock=lambda: datetime(2026, 7, 22, tzinfo=timezone.utc),
    )
    cache = ExternalCache(tmp_path / "cache")
    outcome = SearchExecutor(
        provider, cache, QuotaGuard(tmp_path / "quota.json", 10),
    ).execute(LiveSearchPlan(plan_id="invalid-json", queries=(query,), mode="record"))
    records = list((cache.root / "quarantine" / "provider_failures").rglob("*.json"))
    assert outcome.provider_calls == 1 and not outcome.responses
    assert len(records) == 1
    stored = records[0].read_text(encoding="utf-8")
    payload = json.loads(stored)
    assert payload["provider"] == "tavily" and payload["reason"] == "invalid_response"
    assert "query_hash" in payload and "query" not in payload
    assert "secret body" not in stored


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
    assert manifest["entries"][0]["provider"] == "fake"
    assert manifest["entries"][0]["query"] == _query().model_dump(mode="json")


def test_cache_only_does_not_replay_wrong_provider(tmp_path):
    cache = ExternalCache(tmp_path / "external_cache")
    response = cache.write(_response())
    assert response.provider == "fake"
    outcome = SearchExecutor(
        None, cache, QuotaGuard(tmp_path / "quota.json", 10),
        cache_provider_id="tavily",
    ).execute(LiveSearchPlan(plan_id="provider-isolation", queries=(_query(),), mode="cache_only"))
    assert outcome.responses == () and outcome.cache_hits == 0
    assert outcome.provider_calls == 0


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


def test_quarantine_is_append_only_and_records_item_without_content(tmp_path):
    cache = ExternalCache(tmp_path / "external_cache")
    response = _response()
    first = cache.quarantine(response, "A17_ONE", response.items[0])
    second = cache.quarantine(response, "A17_TWO", response.items[0])
    assert first != second and first.exists() and second.exists()
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in (first, second)]
    assert {item["reason"] for item in payloads} == {"A17_ONE", "A17_TWO"}
    assert all("snippet" not in json.dumps(item) for item in payloads)


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
