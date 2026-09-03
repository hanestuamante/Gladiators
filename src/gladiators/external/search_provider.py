"""Bounded provider adapters for Phase 6 live search.

Adapters only return typed responses. They do not cache, extract, map or admit
records; those trust boundaries live in separate deterministic modules.
"""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Protocol

from dotenv import load_dotenv
import certifi

from .search_contracts import SearchQuery, SearchResponse, SearchResultItem


class ProviderError(RuntimeError):
    def __init__(
        self, message: str, *, retryable: bool, quota_exhausted: bool = False,
        retry_after_s: float | None = None, category: str = "provider_failure",
    ):
        super().__init__(message)
        self.retryable = retryable
        self.quota_exhausted = quota_exhausted
        self.retry_after_s = retry_after_s
        self.category = category


class SearchProvider(Protocol):
    provider_id: str

    def search(
        self, query: SearchQuery, *, max_results: int = 5, timeout_s: float = 10.0,
    ) -> SearchResponse: ...


def _canonical(value):
    if isinstance(value, datetime):
        value = value.isoformat()
    elif isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value.endswith("+00:00"):
        return value[:-6] + "Z"
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def response_content_hash(payload: dict) -> str:
    encoded = json.dumps(
        _canonical(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def response_core(response: SearchResponse) -> dict:
    return response.model_dump(mode="json", exclude={"content_hash", "cache_path"})


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirect disabled", headers, fp)


def _verified_opener():
    """Use an explicit maintained CA bundle while preserving full TLS verification."""
    context = ssl.create_default_context(cafile=certifi.where())
    return urllib.request.build_opener(
        _NoRedirect(), urllib.request.HTTPSHandler(context=context),
    )


class TavilyProvider:
    # HTTP request shape checked against Tavily's official Search API reference
    # on 2026-07-23; mock-contract tests lock the bounded subset used here.
    provider_id = "tavily"
    _URL = "https://api.tavily.com/search"

    def __init__(
        self, api_key: str | None = None, *, opener=None,
        clock: Callable[[], datetime] | None = None,
    ):
        load_dotenv()
        self._api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self._api_key:
            raise RuntimeError("Thiếu TAVILY_API_KEY; live search vẫn OFF.")
        self._opener = opener or _verified_opener()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _now_utc(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)

    @staticmethod
    def _published(value) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    def search(
        self, query: SearchQuery, *, max_results: int = 5, timeout_s: float = 10.0,
    ) -> SearchResponse:
        max_results = max(1, min(int(max_results), 5))
        body = {
            "query": query.query, "search_depth": "basic", "max_results": max_results,
            "topic": "news" if query.purpose in {"campaign_context", "market_event"} else "general",
            "include_answer": False, "include_raw_content": False, "include_images": False,
        }
        if query.recency_days:
            body["start_date"] = (
                self._now_utc().date() - timedelta(days=query.recency_days)
            ).isoformat()
        request = urllib.request.Request(
            self._URL, data=json.dumps(body).encode(), method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json", "Accept": "application/json",
            },
        )
        try:
            with self._opener.open(request, timeout=timeout_s) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ProviderError("Tavily response vượt 2MB.", retryable=False)
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            quota_exhausted = exc.code in {432, 433}
            retry_after = None
            if exc.code == 429:
                try:
                    retry_after = max(0.0, float(exc.headers.get("Retry-After", "0")))
                except (TypeError, ValueError):
                    retry_after = None
            raise ProviderError(
                f"Tavily HTTP {exc.code}", retryable=retryable,
                quota_exhausted=quota_exhausted, retry_after_s=retry_after,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderError(f"Tavily network failure: {type(exc).__name__}", retryable=True) from exc
        try:
            payload = json.loads(raw)
            raw_items = payload.get("results", [])
            if not isinstance(raw_items, list):
                raise TypeError("results must be a list")
            items_list: list[SearchResultItem] = []
            for item in raw_items[:max_results]:
                if not isinstance(item, dict) or not str(item.get("url", "")).startswith("https://"):
                    continue
                items_list.append(SearchResultItem(
                    rank=len(items_list) + 1, title=str(item.get("title") or "")[:500],
                    url=str(item["url"]), snippet=str(item.get("content") or "")[:4000],
                    score=item.get("score"), published_at=self._published(item.get("published_date")),
                ))
            items = tuple(items_list)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError(
                "Tavily response không đúng schema.", retryable=False,
                category="invalid_response",
            ) from exc
        core = {
            "provider": self.provider_id, "query": query.model_dump(mode="json"),
            "items": [item.model_dump(mode="json") for item in items],
            "retrieved_at": self._now_utc().isoformat(),
        }
        return SearchResponse(
            **core, content_hash=response_content_hash(core), cache_path="unpersisted",
        )


class FakeSearchProvider:
    provider_id = "fake"

    def __init__(self, responses: dict[str, SearchResponse]):
        self.responses = responses
        self.calls: list[str] = []

    def search(
        self, query: SearchQuery, *, max_results: int = 5, timeout_s: float = 10.0,
    ) -> SearchResponse:
        del timeout_s
        self.calls.append(query.query)
        if query.query not in self.responses:
            raise ProviderError("Fake provider không có fixture cho query.", retryable=False)
        response = self.responses[query.query]
        if len(response.items) <= max_results:
            return response
        core = response_core(response)
        core["items"] = core["items"][:max_results]
        return SearchResponse(
            **core, content_hash=response_content_hash(core), cache_path="unpersisted",
        )
