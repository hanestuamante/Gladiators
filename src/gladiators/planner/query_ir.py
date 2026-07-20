"""LogicalQueryPlan IR v1.0 — V2 mục 7.6."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Op = Literal[
    "Scan", "ResolveValue", "Filter", "Join", "Dedupe", "Aggregate",
    "DeriveMetric", "TemporalCompare", "Rank", "Similarity", "Project", "Union",
]
PredicateOp = Literal["eq", "ne", "lt", "lte", "gt", "gte", "in", "contains"]
Aggregation = Literal["count", "sum", "mean", "median", "min", "max", "share"]


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
    predicates: tuple[Predicate, ...] = ()
    relation: str | None = None
    source: Literal[
        "products_clean.csv", "shop_info_clean.csv", "category_list_clean.csv",
        "product_categories_clean.csv", "category_platform_clean.csv",
        "product_snapshot_metrics.csv", "product_transition_metrics.csv",
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
