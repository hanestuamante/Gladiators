"""Typed contracts for Phase 6 live-search path; no network implementation."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import ExternalProvenance, SourceSpan

Purpose = Literal["campaign_context", "market_event", "product_external_info"]


class SearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=3, max_length=200)
    market: Literal["vn", "id", "global"]
    recency_days: int | None = Field(default=None, ge=1, le=730)
    purpose: Purpose


class LiveSearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str = Field(min_length=1)
    queries: tuple[SearchQuery, ...] = Field(min_length=1, max_length=3)
    mode: Literal["cache_only", "record", "live"] = "cache_only"


class SearchResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rank: int = Field(ge=1)
    title: str = Field(max_length=500)
    url: str = Field(pattern=r"^https://")
    snippet: str = Field(max_length=4000)
    score: float | None = Field(default=None, ge=0, le=1)
    published_at: date | None = None


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["tavily", "serpapi", "fake"]
    query: SearchQuery
    items: tuple[SearchResultItem, ...] = Field(max_length=5)
    retrieved_at: datetime
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    cache_path: str = Field(min_length=1)


class ExtractedField(BaseModel):
    """One extracted value bound to the exact cached bytes that support it."""

    model_config = ConfigDict(extra="forbid")
    raw_value: str = Field(min_length=1, max_length=2000)
    normalized_value: str | int | float | bool | None = None
    unit: str | None = Field(default=None, max_length=50)
    spans: tuple[SourceSpan, ...] = Field(min_length=1, max_length=4)


FIELD_ALLOWLISTS: dict[str, frozenset[str]] = {
    "campaign_window": frozenset({"campaign_name", "start", "end", "window"}),
    "theme_day": frozenset({"event_name", "theme_day", "date"}),
    "market_event": frozenset({"event_name", "date", "start", "end", "window"}),
    # Descriptive context only: money/price/discount fields are deliberately absent.
    "product_fact": frozenset({"product_name", "brand", "description", "fact"}),
}
PII_FIELD_NAMES = frozenset({"email", "phone", "username", "address", "token", "api_key"})


class ExtractedWebRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: Literal["live_web_search"] = "live_web_search"
    parser_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    raw_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    search_query: str = Field(min_length=3, max_length=200)
    result_url: str = Field(pattern=r"^https://")
    result_rank: int = Field(ge=1)
    claim_type: Literal["campaign_window", "theme_day", "market_event", "product_fact"]
    fields: dict[str, ExtractedField] = Field(min_length=1, max_length=8)

    @model_validator(mode="before")
    @classmethod
    def migrate_safely_bound_legacy_fields(cls, value: Any) -> Any:
        """Accept the old scalar+top-level-span shape only when spans name a field.

        Actual byte/raw binding is still checked by P6/admission. This migration
        prevents old fixtures from breaking silently while removing the unsafe
        independent span list from the validated record.
        """
        if not isinstance(value, dict) or "spans" not in value:
            return value
        migrated = dict(value)
        legacy_spans = list(migrated.pop("spans") or [])
        fields = migrated.get("fields")
        if isinstance(fields, dict):
            structured: dict[str, Any] = {}
            for name, raw in fields.items():
                matching = [span for span in legacy_spans if (
                    span.get("field") if isinstance(span, dict) else getattr(span, "field", None)
                ) == name]
                structured[name] = {
                    "raw_value": str(raw), "normalized_value": None,
                    "unit": None, "spans": matching,
                }
            migrated["fields"] = structured
        return migrated

    @model_validator(mode="after")
    def fields_are_allowed_for_claim(self) -> "ExtractedWebRecord":
        names = set(self.fields)
        if names & PII_FIELD_NAMES:
            raise ValueError("A17 PII/secret-like field bị cấm.")
        unexpected = names - FIELD_ALLOWLISTS[self.claim_type]
        if unexpected:
            raise ValueError(f"A17 field ngoài allowlist cho {self.claim_type}: {sorted(unexpected)}")
        return self

    def all_spans(self) -> tuple[SourceSpan, ...]:
        return tuple(span for field in self.fields.values() for span in field.spans)

    def normalized_fields(self) -> dict[str, str | int | float | bool | None]:
        return {
            name: field.normalized_value if field.normalized_value is not None else field.raw_value
            for name, field in self.fields.items()
        }


class LiveSearchProvenance(ExternalProvenance):
    model_config = ConfigDict(extra="forbid")
    source_tier: Literal["external"] = "external"
    provider: Literal["tavily", "serpapi", "fake"]
    search_query: str = Field(min_length=3, max_length=200)
    result_rank: int = Field(ge=1)
    source_spans: tuple[SourceSpan, ...] = Field(min_length=1)


class LiveSearchOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str = Field(min_length=1)
    admitted: tuple[str, ...] = ()
    excluded_count: int = Field(default=0, ge=0)
    quarantined_count: int = Field(default=0, ge=0)
    ladder_reason: str | None = None
