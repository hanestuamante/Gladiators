"""LogicalQueryPlan IR v1.0 — V2 mục 7.6."""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator, model_serializer

from gladiators.domain.tables import ArtifactName

Op = Literal[
    "Scan", "ResolveValue", "Filter", "Join", "Dedupe", "Aggregate",
    "DeriveMetric", "TemporalCompare", "Rank", "Similarity", "Project", "Union",
]
# W11.1: PredicateOp là alias của chuẩn chung — hai danh sách là hai chỗ lệch.
from .predicate_ops import ExecutablePredicateOp as PredicateOp  # noqa: E402
Aggregation = Literal["count", "sum", "mean", "median", "min", "max", "share"]
# §4.3: one grammar, shared by the model, the planner prompt and the validator
# feedback, so a plan is never rejected against a rule the prompt never stated.
# W30-R3: cận số dòng nhận thêm KÝ HIỆU trên lịch snapshot. Tập ký hiệu là
# ĐÓNG và viết ra ở đây — nới thành một chuỗi tự do sẽ cho LLM planner khai một
# cận không ai phân giải được, tức một cận không tồn tại.
CARDINALITY_SYMBOLS = ("snapshot_rows", "listings", "snapshots")
CARDINALITY_GRAMMAR = r"^(<=)?(\d+|" + "|".join(CARDINALITY_SYMBOLS) + r")$"
_CARDINALITY = re.compile(CARDINALITY_GRAMMAR)

# Words models reach for instead of a bound. "single" has an exact meaning; the
# plural aliases only do once the node states a limit, and are otherwise left
# alone so the field validator rejects them into a bounded repair. Coercing them
# to something like "<=10000" would invent a bound the plan never justified.
_CARDINALITY_EXACT_ALIASES = {"single": "1", "one": "1", "scalar": "1"}
_CARDINALITY_BOUNDED_ALIASES = frozenset({"many", "multiple", "list", "several"})


class Predicate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    op: PredicateOp
    parameter: str
    value: Any


class OutputField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    type: Literal["string", "integer", "number", "boolean", "date"]
    semantic_ref: str | None = None


class EvidenceEmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    metric_ref: str | None = None
    caveat_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def metric_required_when_enabled(self) -> "EvidenceEmission":
        if self.enabled and not self.metric_ref:
            raise ValueError("evidence emission bật nhưng thiếu metric_ref")
        return self


class PlanNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str
    op: Op
    inputs: tuple[str, ...] = ()
    refs: tuple[str, ...] = ()
    # W6.1: hai đầu mút của một node TemporalCompare dạng so-hai-mốc. Additive,
    # mặc định None ⇒ plan cũ (kể cả macro sales_decline dạng pass-through)
    # không đổi một byte — serializer dưới bỏ khoá khi None để 58 plan bị khoá
    # giữ nguyên từng byte dump (bất biến #7).
    time_scope: tuple[str, ...] | None = None
    # Bỏ qua bao nhiêu dòng trước khi cắt `limit`. Additive, mặc định 0 ⇒ mọi
    # plan đã khoá giữ nguyên từng byte dump (bất biến #7) nhờ serializer dưới.
    # Không dịch thành OFFSET trong SQL: phép cắt nằm ở executor vì nó CÒN
    # PHẢI nhìn hai hàng xóm của lát cắt để biết lát có rơi giữa một dãy bằng
    # nhau hay không, và một OFFSET trong SQL lấy đi đúng hàng xóm đó.
    rank_offset: int = Field(default=0, ge=0, le=98)

    @model_serializer(mode="wrap")
    def _drop_unset_time_scope(self, handler):
        payload = handler(self)
        if isinstance(payload, dict):
            if payload.get("time_scope") is None:
                payload.pop("time_scope", None)
            if not payload.get("rank_offset"):
                payload.pop("rank_offset", None)
        return payload
    predicates: tuple[Predicate, ...] = ()
    relation: str | None = None
    # §E1: ``ArtifactName`` là StrEnum nên plan JSON cũ (chuỗi tên file) vẫn
    # parse và vẫn serialize ra đúng chuỗi đó; khác biệt là source giờ phải là
    # một artifact có trong TableRegistry, không phải một chuỗi trùng hình.
    source: Literal[
        ArtifactName.PRODUCTS, ArtifactName.SHOP_INFO, ArtifactName.CATEGORY_LIST,
        ArtifactName.PRODUCT_CATEGORIES, ArtifactName.CATEGORY_PLATFORM,
        ArtifactName.SNAPSHOT_METRICS, ArtifactName.TRANSITION_METRICS,
    ] | None = None
    aggregation: Aggregation | None = None
    group_by: tuple[str, ...] = ()
    rank_by: str | None = None
    descending: bool = True
    limit: int | None = Field(default=None, ge=1, le=10_000)
    input_grain: str
    output_grain: str
    units: tuple[str, ...] = ()
    expected_schema: tuple[OutputField, ...]
    expected_cardinality: str
    # Set only when an alias was resolved, so planning meta can report
    # original/normalized/coerced without a side channel (§4.3).
    original_cardinality: str | None = None
    dedupe_policy: str | None = None
    invariants: tuple[str, ...] = ()
    evidence_emission: EvidenceEmission = Field(default_factory=EvidenceEmission)
    cost_estimate: int = Field(default=1, ge=0)
    risk_estimate: int = Field(default=0, ge=0, le=10)

    @field_validator("node_id")
    @classmethod
    def nonempty_node_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("node_id rỗng")
        return value

    @model_validator(mode="before")
    @classmethod
    def normalize_cardinality(cls, data: Any) -> Any:
        """Resolve the aliases a model reaches for, and only where they are exact.

        ``single`` means one row whatever the node does.  ``many`` only carries a
        bound when the node states a ``limit``; without one it is left untouched
        so :meth:`valid_cardinality` rejects it and the planner gets a structured
        issue to repair.  §4.3 forbids inventing a bound such as ``<=10000``,
        because that turns "I don't know how many" into a contract the executor
        will happily enforce against nothing.
        """
        if not isinstance(data, dict):
            return data
        raw = data.get("expected_cardinality")
        if not isinstance(raw, str):
            return data
        token = raw.strip().lower()
        resolved: str | None = _CARDINALITY_EXACT_ALIASES.get(token)
        if resolved is None and token in _CARDINALITY_BOUNDED_ALIASES:
            limit = data.get("limit")
            if isinstance(limit, int) and limit >= 1:
                resolved = f"<={limit}"
        if resolved is not None and resolved != raw:
            data = {**data, "expected_cardinality": resolved, "original_cardinality": raw}
        return data

    @field_validator("expected_cardinality")
    @classmethod
    def valid_cardinality(cls, value: str) -> str:
        """Output cardinality is enforced; intermediate values remain estimates."""
        normalized = value.strip()
        if not _CARDINALITY.fullmatch(normalized):
            # Message is contract text, not a schema dump: it names the grammar
            # the prompt was given so a repair has something actionable, and it
            # never reaches the UI (workflow maps this to a structured issue).
            raise ValueError(
                f"expected_cardinality phải khớp {CARDINALITY_GRAMMAR} "
                f"(ví dụ '1' hoặc '<=5'); nhận được {value!r}. "
                "Alias số nhiều chỉ hợp lệ khi node khai limit."
            )
        return normalized


class PlanBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_nodes: int = Field(default=12, ge=1, le=100)
    max_depth: int = Field(default=6, ge=1, le=50)
    max_subplans: int = Field(default=4, ge=1, le=20)


class LogicalQueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str
    ir_version: Literal["1.0"] = "1.0"
    nodes: tuple[PlanNode, ...]
    output_node: str
    requested_output_shape: tuple[OutputField, ...]
    budget: PlanBudget = Field(default_factory=PlanBudget)
    time_scope: tuple[str, ...] = ()
    source_tier: Literal["btc_dataset"] = "btc_dataset"
    subplan_count: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def ids_are_unique(self) -> "LogicalQueryPlan":
        ids = [node.node_id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("node_id trùng trong plan")
        return self
