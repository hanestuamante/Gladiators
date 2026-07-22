"""Bounded provider adapters for Phase 6 live search.

Adapters only return typed responses. They do not cache, extract, map or admit
records; those trust boundaries live in separate deterministic modules.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from typing import Protocol

from dotenv import load_dotenv

from .search_contracts import SearchQuery, SearchResponse, SearchResultItem


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


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


class TavilyProvider:
    provider_id = "tavily"
    _URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str | None = None):
        load_dotenv()
        self._api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self._api_key:
            raise RuntimeError("Thiếu TAVILY_API_KEY; live search vẫn OFF.")
        self._opener = urllib.request.build_opener(_NoRedirect())

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
        }
        if query.recency_days:
            body["days"] = query.recency_days
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
            raise ProviderError(f"Tavily HTTP {exc.code}", retryable=retryable) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderError(f"Tavily network failure: {type(exc).__name__}", retryable=True) from exc
        try:
            payload = json.loads(raw)
            raw_items = payload.get("results", [])
            items = tuple(
                SearchResultItem(
                    rank=index, title=str(item.get("title", ""))[:500],
                    url=str(item["url"]), snippet=str(item.get("content", ""))[:4000],
                    score=item.get("score"), published_at=self._published(item.get("published_date")),
                )
                for index, item in enumerate(raw_items[:max_results], 1)
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError("Tavily response không đúng schema.", retryable=False) from exc
        core = {
            "provider": self.provider_id, "query": query.model_dump(mode="json"),
            "items": [item.model_dump(mode="json") for item in items],
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
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
