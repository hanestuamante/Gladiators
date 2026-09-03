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
            cache.quarantine(response, reason, item)
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
        monotonic=time.monotonic, sleeper=time.sleep, cache_provider_id: str | None = None,
    ):
        self.provider, self.cache, self.quota = provider, cache, quota
        self.max_results, self.timeout_s, self.total_budget_s = max_results, timeout_s, total_budget_s
        self.monotonic, self.sleeper = monotonic, sleeper
        self.cache_provider_id = cache_provider_id

    def preflight_failure(self, mode: str) -> str | None:
        """Avoid P5 cost when live execution is known to be impossible."""
        if mode == "cache_only":
            return None  # The typed query is still needed for exact cache lookup.
        if self.provider is None:
            return "A15: live-search provider unavailable"
        if self.quota.exhausted():
            return "A15: quota exhausted"
        return None

    def execute(self, plan: LiveSearchPlan) -> SearchExecutionOutcome:
        started = self.monotonic()
        responses: list[SearchResponse] = []
        failed: list[str] = []
        quarantined = cache_hits = provider_calls = 0
        provider_quota_exhausted = False
        for query in plan.queries:
            if self.monotonic() - started >= self.total_budget_s:
                failed.append(query.query)
                continue
            if plan.mode == "cache_only":
                provider_id = self.cache_provider_id or getattr(self.provider, "provider_id", None)
                cached = self.cache.find(query, provider_id)
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
                elapsed = self.monotonic() - started
                remaining = self.total_budget_s - elapsed
                if self.quota.exhausted() or remaining <= 0:
                    break
                self.quota.consume()
                provider_calls += 1
                try:
                    response = self.provider.search(
                        query, max_results=self.max_results,
                        timeout_s=min(self.timeout_s, remaining),
                    )
                    if self.monotonic() - started > self.total_budget_s:
                        response = None
                    break
                except ProviderError as exc:
                    provider_quota_exhausted = provider_quota_exhausted or exc.quota_exhausted
                    if exc.category == "invalid_response":
                        self.cache.quarantine_provider_failure(
                            provider=getattr(self.provider, "provider_id", "unknown"),
                            query=query, reason=exc.category,
                        )
                    if not exc.retryable or attempt == 1:
                        break
                    remaining = self.total_budget_s - (self.monotonic() - started)
                    delay = min(exc.retry_after_s or 0.0, max(0.0, remaining))
                    if delay > 0:
                        self.sleeper(delay)
                    if self.monotonic() - started >= self.total_budget_s:
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
            reason = "A15: quota exhausted" if self.quota.exhausted() or provider_quota_exhausted else "A15: no usable external result"
        return SearchExecutionOutcome(
            tuple(responses), tuple(failed), quarantined, cache_hits, provider_calls, reason,
        )
