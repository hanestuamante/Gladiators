"""Typed contracts for Phase 6 live-search path; no network implementation."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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
    fields: dict[str, str | int | float | bool | None]
    spans: tuple[SourceSpan, ...] = Field(min_length=1)


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
