"""Bounded, non-LLM execution for validated live-search plans."""
from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlparse

from .cache import ExternalCache, QuotaGuard
from .injection_guard import sanitize_and_check
from .search_contracts import LiveSearchPlan, SearchResponse, SearchResultItem
from .search_provider import ProviderError, SearchProvider, response_content_hash

DENIED_DOMAINS = ("shopee.vn", "shopee.co.id", "shopeemobile.com")


@dataclass(frozen=True)
class SearchExecutionOutcome:
    responses: tuple[SearchResponse, ...]
    failed_queries: tuple[str, ...]
    quarantined_count: int
    cache_hits: int
    provider_calls: int
    ladder_reason: str | None


def _denied(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == domain or host.endswith("." + domain) for domain in DENIED_DOMAINS)


def _sanitize(response: SearchResponse, cache: ExternalCache) -> tuple[SearchResponse, int]:
    items: list[SearchResultItem] = []
    quarantined = 0
    for item in response.items:
        title = sanitize_and_check(item.title, max_chars=500)
        snippet = sanitize_and_check(item.snippet, max_chars=4000)
        hits = (*title.hits, *snippet.hits)
        if _denied(item.url) or hits:
            quarantined += 1
            reason = "DENIED_DOMAIN" if _denied(item.url) else ",".join(hits)
            cache.quarantine(response, reason)
            continue
        items.append(item.model_copy(update={"title": title.text, "snippet": snippet.text}))
    core = response.model_dump(mode="json", exclude={"content_hash", "cache_path"})
    core["items"] = [item.model_dump(mode="json") for item in items]
    return SearchResponse(
        **core, content_hash=response_content_hash(core), cache_path="unpersisted",
    ), quarantined


class SearchExecutor:
    def __init__(
        self, provider: SearchProvider | None, cache: ExternalCache, quota: QuotaGuard,
        *, max_results: int = 5, timeout_s: float = 10.0, total_budget_s: float = 25.0,
    ):
        self.provider, self.cache, self.quota = provider, cache, quota
        self.max_results, self.timeout_s, self.total_budget_s = max_results, timeout_s, total_budget_s

    def execute(self, plan: LiveSearchPlan) -> SearchExecutionOutcome:
        started = time.monotonic()
        responses: list[SearchResponse] = []
        failed: list[str] = []
        quarantined = cache_hits = provider_calls = 0
        for query in plan.queries:
            if time.monotonic() - started >= self.total_budget_s:
                failed.append(query.query)
                continue
            if plan.mode == "cache_only":
                cached = self.cache.find(query, getattr(self.provider, "provider_id", None))
                if cached is None:
                    failed.append(query.query)
                else:
                    responses.append(cached)
                    cache_hits += 1
                continue
            if self.provider is None or self.quota.exhausted():
                failed.append(query.query)
                continue
            response = None
            for attempt in range(2):
                if self.quota.exhausted():
                    break
                self.quota.consume()
                provider_calls += 1
                try:
                    response = self.provider.search(
                        query, max_results=self.max_results, timeout_s=self.timeout_s,
                    )
                    break
                except ProviderError as exc:
                    if not exc.retryable or attempt == 1:
                        break
            if response is None:
                failed.append(query.query)
                continue
            response, count = _sanitize(response, self.cache)
            quarantined += count
            if not response.items:
                failed.append(query.query)
                continue
            if plan.mode == "record":
                response = self.cache.write(response)
            responses.append(response)
        reason = None
        if not responses:
            reason = "A15: quota exhausted" if self.quota.exhausted() else "A15: no usable external result"
        return SearchExecutionOutcome(
            tuple(responses), tuple(failed), quarantined, cache_hits, provider_calls, reason,
        )
