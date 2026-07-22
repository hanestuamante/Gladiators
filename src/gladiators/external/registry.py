"""Executable source registry for the approved Phase 6 demo capability."""
from __future__ import annotations

from .contracts import SourceRegistryEntry
from .settings import LiveSearchSettings


class SourceRegistry:
    def __init__(self, entries: tuple[SourceRegistryEntry, ...]):
        if len({entry.source_id for entry in entries}) != len(entries):
            raise ValueError("Source registry chứa source_id trùng.")
        self._entries = {entry.source_id: entry for entry in entries}

    def get(self, source_id: str) -> SourceRegistryEntry | None:
        return self._entries.get(source_id)

    def require_enabled(self, source_id: str) -> SourceRegistryEntry:
        entry = self.get(source_id)
        if entry is None or not entry.enabled:
            raise RuntimeError(f"Source `{source_id}` chưa được bật.")
        return entry


def build_source_registry(settings: LiveSearchSettings) -> SourceRegistry:
    return SourceRegistry((SourceRegistryEntry(
        source_id="live_web_search", kind="api", default_tier="external",
        allowed_domains=("api.tavily.com",), parser_id="p6_web_extract",
        schema_version="2.0", trust_level="public_aggregator", ttl_hours=24,
        rate_limit_per_min=30, review_policy="per_batch_review", owner="Gladiators demo team",
        license=settings.demo_provenance_label,
        license_url="https://docs.tavily.com/documentation/api-reference/endpoint/search",
        allowed_use=("campaign_context", "market_event", "product_external_info"),
        enabled=settings.enabled,
    ),))
