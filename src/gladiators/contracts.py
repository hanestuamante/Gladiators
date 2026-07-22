from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from gladiators.external.contracts import ExternalProvenance, SourceLocator


class StructuredRequest(BaseModel):
    intent: str
    entity_text: str | None = None
    country: str | None = None
    date_range: list[str] = Field(default_factory=list)
    slots: dict[str, Any] = Field(default_factory=dict)
    analytical: dict[str, Any] | None = None
    language: Literal["vi", "id", "unknown"] = "unknown"

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        if value is None: return None
        normalized = value.strip().lower()
        return {"vietnam": "vn", "viet nam": "vn", "indonesia": "id"}.get(normalized, normalized)


class Candidate(BaseModel):
    listing_key: str
    product_name: str
    lexical_score: float
    semantic_score: float | None = None
    final_score: float


class GateDecision(BaseModel):
    action: Literal["allow", "clarify", "abstain"]
    rule_id: str
    reason: str
    answerable_alternative: str | None = None


class Evidence(BaseModel):
    evidence_id: str
    source_tier: Literal["btc_dataset", "reference", "external"]
    metric: str
    value: int | float | str | bool | None
    unit: str | None = None
    source_locator: SourceLocator
    source_path: str | None = None
    dataset_version: str
    attrs: dict[str, Any] = Field(default_factory=dict)
    provenance: ExternalProvenance | None = None
    parent_evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def provenance_matches_tier(self) -> "Evidence":
        if self.source_tier == "btc_dataset":
            if self.provenance is not None:
                raise ValueError("Evidence btc_dataset không được gắn external provenance.")
            return self
        if self.provenance is None:
            raise ValueError("Evidence reference/external bắt buộc có provenance (A21-PROV).")
        if self.provenance.source_tier != self.source_tier:
            raise ValueError("Evidence.source_tier không khớp provenance.source_tier.")
        return self


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    status: Literal["ok", "empty", "error"] = "ok"
    evidence_ids: list[str] = Field(default_factory=list)
    error: str | None = None


class AgentResponse(BaseModel):
    trace_id: str
    request: StructuredRequest
    gate: GateDecision
    answer: str
    evidence: list[Evidence] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    resolved_listing_key: str | None = None
    verification: dict[str, Any] = Field(default_factory=dict)
    llm: dict[str, Any] = Field(default_factory=dict)
    planning: dict[str, Any] = Field(default_factory=dict)
    degraded: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
