from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from gladiators.external.contracts import ExternalProvenance, SourceLocator


class StructuredRequest(BaseModel):
    intent: str
    entity_text: str | None = None
    country: str | None = None
    countries: tuple[str, ...] = ()
    entities: tuple[dict[str, Any], ...] = ()
    date_range: list[str] = Field(default_factory=list)
    slots: dict[str, Any] = Field(default_factory=dict)
    analytical: dict[str, Any] | None = None
    language: Literal["vi", "id", "unknown"] = "unknown"
    route_mode: Literal["internal_only", "external_only", "hybrid", "clarify", "abstain"] = "internal_only"
    external_purpose: Literal["campaign_context", "market_event", "product_external_info"] | None = None
    requested_variables: tuple[str, ...] = ()

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        if value is None: return None
        normalized = value.strip().lower()
        return {"vietnam": "vn", "viet nam": "vn", "indonesia": "id", "indo": "id"}.get(normalized, normalized)

    @field_validator("countries")
    @classmethod
    def normalize_countries(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        aliases = {"vietnam": "vn", "viet nam": "vn", "indonesia": "id", "indo": "id"}
        return tuple(dict.fromkeys(aliases.get(value.strip().lower(), value.strip().lower()) for value in values))

    @model_validator(mode="after")
    def primary_country_matches_countries(self) -> "StructuredRequest":
        if self.countries and self.country != self.countries[0]:
            object.__setattr__(self, "country", self.countries[0])
        elif self.country and not self.countries:
            object.__setattr__(self, "countries", (self.country,))
        return self


class Candidate(BaseModel):
    listing_key: str
    product_name: str
    lexical_score: float
    semantic_score: float | None = None
    final_score: float


class IssueDetail(BaseModel):
    """What kind of problem a gate rule found — ultimate solution §4.5."""

    model_config = ConfigDict(extra="forbid")
    category: Literal[
        "capability", "entity", "grain", "fanout",
        "currency", "alignment", "security", "slot", "route",
        # W20: phạm vi THỜI GIAN — ngày ngoài cửa sổ hoặc rơi vào một lỗ giữa
        # hai đợt thu. Khác "slot" (thiếu thông tin người dùng cấp được) vì
        # không thông tin nào tạo ra một đợt thu chưa từng chạy.
        "scope",
    ]
    code: str
    semantic_refs: tuple[str, ...] = ()


class GateIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str
    phase: int
    priority: int
    action: Literal["clarify", "abstain", "block"]
    reason: str
    answerable_alternative: str | None = None
    detail: IssueDetail
    # §4.5.1: False when no information the user could supply removes the
    # obstacle. A missing country is a fact about the question; a product code
    # that does not exist is a fact about the data, and no rephrasing fixes it.
    fixable: bool = True
    # W22-R3: ô mà issue này hỏi, nếu nó là một clarify.
    clarification_slot: str | None = None


class GateDecision(BaseModel):
    action: Literal["allow", "clarify", "abstain"]
    rule_id: str
    reason: str
    # W22-R3: ô mà câu hỏi lại đang hỏi. Câu hỏi lại sinh TỪ Ô, không phải từ
    # việc chuỗi `reason` tình cờ chứa từ khoá nào — đó là điều làm
    # `clarification_precision` đo được thay vì đoán được.
    clarification_slot: str | None = None
    answerable_alternative: str | None = None
    # §4.5: a phase collects every issue before one is selected, so the trace
    # shows what else was wrong rather than only the first rule that fired.
    issues: tuple[GateIssue, ...] = ()
    selected_issue_id: str | None = None
    evaluated_phases: tuple[int, ...] = ()
    # Spans quoted back from the dataset -- listing names in an ambiguity
    # shortlist, for instance. They are data being echoed so the user can pick,
    # not numeric claims: a product called "... Cleanser 100ml" would otherwise
    # have its "100" scanned as an unsupported number.
    quoted_texts: tuple[str, ...] = ()


class Evidence(BaseModel):
    # W1.4: bất biến hệ thống #4 cưỡng chế bằng model, không dựa vào kỷ luật của
    # caller. Không tuyên bố deep-freeze cho object lồng trong attrs — caller
    # cũng không được giữ rồi mutate dict đã truyền vào.
    model_config = ConfigDict(extra="forbid", frozen=True)

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
    claimable_paths: tuple[str, ...] = ("value",)

    @field_validator("claimable_paths")
    @classmethod
    def validate_claimable_paths(cls, paths: tuple[str, ...]) -> tuple[str, ...]:
        if not paths or any(not path or not all(part.isidentifier() for part in path.split(".")) for path in paths):
            raise ValueError("Evidence.claimable_paths chỉ nhận dot-path định danh và không được rỗng.")
        if len(set(paths)) != len(paths):
            raise ValueError("Evidence.claimable_paths không được trùng.")
        return paths

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


class ResponseClaim(BaseModel):
    """A displayed claim bound to one explicit path in one Evidence object."""

    model_config = ConfigDict(extra="forbid")
    claim_id: str = Field(min_length=1, pattern=r"^cl:[A-Za-z0-9:_-]+$")
    text: str = Field(min_length=1)
    claim_type: Literal["money", "count", "percent", "date", "context", "text"]
    value: str | int | float | bool
    unit: str | None = None
    evidence_id: str = Field(min_length=1)
    evidence_path: str = Field(min_length=1)


class AgentResponse(BaseModel):
    trace_id: str
    request: StructuredRequest
    gate: GateDecision
    answer: str
    evidence: list[Evidence] = Field(default_factory=list)
    claims: tuple[ResponseClaim, ...] = ()
    tool_calls: list[ToolCall] = Field(default_factory=list)
    resolved_listing_key: str | None = None
    verification: dict[str, Any] = Field(default_factory=dict)
    llm: dict[str, Any] = Field(default_factory=dict)
    planning: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    degraded: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
