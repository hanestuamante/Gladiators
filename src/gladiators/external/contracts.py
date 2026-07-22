from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Tier = Literal["reference", "external"]
MappingState = Literal[
    "unmapped", "candidate", "needs_review", "auto_confirmed",
    "manual_confirmed", "rejected", "superseded",
]
Admission = Literal["supporting", "context_only", "excluded"]


class SourceLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["url", "file", "api", "internal"]
    value: str = Field(min_length=1)

    @field_validator("value")
    @classmethod
    def validate_url(cls, value: str, info):
        if info.data.get("kind") == "url" and not value.startswith(("https://", "http://")):
            raise ValueError("URL locator phải bắt đầu bằng http:// hoặc https://")
        return value


class ExternalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_locator: SourceLocator
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    license: str | None = None
    payload: dict[str, Any]


class SourceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(min_length=1)
    text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered_offsets(self) -> "SourceSpan":
        if self.end <= self.start:
            raise ValueError("SourceSpan.end phải lớn hơn start.")
        return self


class SourceRegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1)
    kind: Literal["api", "scrape", "file"]
    default_tier: Tier
    allowed_domains: tuple[str, ...] = ()
    parser_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    trust_level: Literal["official", "public_aggregator", "community"]
    ttl_hours: float | None = Field(default=None, gt=0)
    rate_limit_per_min: int | None = Field(default=None, ge=1)
    review_policy: Literal["dr1_signoff_once", "per_batch_review"]
    owner: str = Field(min_length=1)
    license: str = Field(min_length=1)
    license_url: str | None = None
    allowed_use: tuple[str, ...] = ()
    legal_signoff_at: datetime | None = None
    legal_signoff_expires_at: datetime | None = None
    enabled: bool = False


class AdmissionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    outcome: Admission
    rule_id: str = Field(min_length=1)
    caveats: tuple[str, ...] = ()
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExternalProvenance(BaseModel):
    """Mandatory provenance envelope for every non-btc_dataset Evidence."""

    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1)
    source_tier: Tier
    source_locator: SourceLocator
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_at: datetime
    retrieved_at: datetime
    unit: str | None = None
    currency: Literal["VND", "IDR"] | None = None
    mapping_status: MappingState
    admission: Admission
    license: str = Field(min_length=1)
    caveats: tuple[str, ...] = ()
    # Live-search fields stay optional on the common envelope so Pydantic does
    # not erase subtype provenance when Evidence is serialized through the API.
    provider: Literal["tavily", "serpapi", "fake"] | None = None
    search_query: str | None = Field(default=None, min_length=3, max_length=200)
    result_rank: int | None = Field(default=None, ge=1)
    source_spans: tuple[SourceSpan, ...] = ()
