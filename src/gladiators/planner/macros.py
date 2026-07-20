"""Certified macro registry cho ba intent V1 — V2 mục 7.10."""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass

from .query_ir import LogicalQueryPlan, OutputField, PlanNode, Predicate
from .validator import validate_plan


@dataclass(frozen=True)
class CertifiedMacro:
    name: str
    version: str
    required_slots: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    tool_plan: tuple[str, ...]
    plan_template: LogicalQueryPlan
    evidence_metrics: tuple[str, ...]

    @property
    def plan_hash(self) -> str:
        return hashlib.sha256(self.plan_template.model_dump_json().encode("utf-8")).hexdigest()[:16]

    def accepts_evidence(self, metrics: list[str]) -> bool:
        return Counter(metrics) == Counter(self.evidence_metrics)


class MacroRegistry:
    def __init__(self) -> None:
        self._items: dict[str, CertifiedMacro] = {}

    def register(self, macro: CertifiedMacro) -> None:
        if macro.name in self._items:
            raise ValueError(f"Macro đã tồn tại: {macro.name}")
        verdict = validate_plan(macro.plan_template)
        if not verdict.valid:
            details = "; ".join(f"{x.code}:{x.message}" for x in verdict.issues)
            raise ValueError(f"Macro {macro.name} không qua Plan Validator: {details}")
        self._items[macro.name] = macro

    def get(self, name: str) -> CertifiedMacro | None:
        return self._items.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(self._items)


def _sales_decline() -> CertifiedMacro:
    output = (
        OutputField(name="monthly_sold_delta", type="number", semantic_ref="derived.monthly_sold_delta"),
        OutputField(name="days_since_previous", type="integer"),
    )
    plan = LogicalQueryPlan(
        plan_id="macro:sales_decline:1.0", time_scope=("2026-07-01", "2026-07-02", "2026-07-03"),
        output_node="n3", requested_output_shape=output,
        nodes=(
            PlanNode(node_id="n1", op="ResolveValue", refs=("entity.product_listing",),
                     input_grain="user_value", output_grain="listing",
                     expected_schema=(OutputField(name="product_listing_key", type="string"),), expected_cardinality="1"),
            PlanNode(node_id="n2", op="Scan", inputs=("n1",), source="product_transition_metrics.csv",
                     refs=("derived.monthly_sold_delta",), input_grain="listing", output_grain="transition",
                     expected_schema=output, expected_cardinality="<=2"),
            PlanNode(node_id="n3", op="TemporalCompare", inputs=("n2",), refs=("derived.monthly_sold_delta",),
                     input_grain="transition", output_grain="transition", expected_schema=output,
                     expected_cardinality="1", invariants=("nonnegative:days_since_previous",)),
        ),
    )
    return CertifiedMacro(
        "sales_decline", "1.0", ("entity_text",), ("monthly_sales_proxy",),
        ("resolve_entity", "get_sales_transitions"), plan,
        ("monthly_sold_delta", "days_since_previous"),
    )


def _similar_product() -> CertifiedMacro:
    output = (
        OutputField(name="similarity_score", type="number", semantic_ref="derived.similarity_score"),
    )
    plan = LogicalQueryPlan(
        plan_id="macro:similar_product:1.0", output_node="n2", requested_output_shape=output,
        nodes=(
            PlanNode(node_id="n1", op="ResolveValue", refs=("entity.product_listing",),
                     input_grain="user_value", output_grain="listing",
                     expected_schema=(OutputField(name="product_listing_key", type="string"),), expected_cardinality="1"),
            PlanNode(node_id="n2", op="Similarity", inputs=("n1",), refs=("derived.similarity_score",),
                     input_grain="listing", output_grain="listing_pair", expected_schema=output,
                     expected_cardinality="<=5", invariants=("range:similarity_score:0:1",)),
        ),
    )
    return CertifiedMacro(
        "similar_product", "1.0", ("entity_text",), ("product_titles",),
        ("resolve_entity", "find_similar"), plan, ("similarity_score",) * 5,
    )


def _promotion_effectiveness() -> CertifiedMacro:
    output = (
        OutputField(name="group_metrics", type="number", semantic_ref="derived.descriptive_gap_vs_baseline"),
    )
    plan = LogicalQueryPlan(
        plan_id="macro:promotion_effectiveness:1.0", time_scope=("2026-07-03",),
        output_node="n3", requested_output_shape=output,
        nodes=(
            PlanNode(node_id="n1", op="Scan", source="product_snapshot_metrics.csv",
                     refs=("derived.has_structured_voucher", "measure.monthly_sold"),
                     input_grain="listing_snapshot", output_grain="listing_snapshot",
                     expected_schema=output, expected_cardinality="<=1157"),
            PlanNode(node_id="n2", op="Filter", inputs=("n1",),
                     predicates=(Predicate(ref="dim.country", op="eq", parameter="country", value="<bound>"),),
                     input_grain="listing_snapshot", output_grain="listing_snapshot",
                     expected_schema=output, expected_cardinality="<=682"),
            PlanNode(node_id="n3", op="DeriveMetric", inputs=("n2",), refs=("derived.descriptive_gap_vs_baseline",),
                     input_grain="listing_snapshot", output_grain="voucher_group", expected_schema=output,
                     expected_cardinality="2"),
        ),
    )
    metrics = tuple(
        f"{group}_{metric}"
        for group in ("with_voucher", "without_voucher")
        for metric in ("listing_count", "mean_monthly_sold_proxy", "median_monthly_sold_proxy")
    )
    return CertifiedMacro(
        "promotion_effectiveness", "1.0", ("country",), ("voucher_observation",),
        ("compare_voucher_groups",), plan, metrics,
    )


def default_macro_registry() -> MacroRegistry:
    registry = MacroRegistry()
    for factory in (_sales_decline, _similar_product, _promotion_effectiveness):
        registry.register(factory())
    return registry
