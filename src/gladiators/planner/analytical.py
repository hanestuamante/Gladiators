"""Deterministic low-risk analytical templates cho Phase 4.

Các template này dành cho L0–L2 phổ biến, không gọi LLM. Câu ngoài template sẽ
đi A19-PLAN cho tới khi P7/P8 được triển khai và eval.
"""
from __future__ import annotations

from .query_ir import LogicalQueryPlan, OutputField, PlanNode, Predicate
from .semantic_parser import AnalyticalRequest


class AnalyticalPlanError(ValueError):
    pass


def infer_deterministic_template(request: AnalyticalRequest) -> str | None:
    measures = {item.ref for item in request.requested_measures if item.ref}
    dimensions = {item.ref for item in request.requested_dimensions if item.ref}
    analytical_dimensions = dimensions - {"dim.country", "dim.date"}
    # Every certified ranking template below is a "highest" template: they build
    # a Rank node with direction desc. Matching one for an ascending request
    # inverts the answer silently -- "giá thấp nhất tại VN" returned 3.033.180
    # (the maximum) when the true minimum is 1.000, and the answer sentence still
    # read "Listing có giá cao nhất là...". Fail through to the semantic planner
    # instead; there is no certified lowest-N template to fall back on.
    if request.ranking and request.ranking.direction == "desc":
        if "derived.estimated_recent_revenue" in measures and "dim.date" in dimensions:
            return "highest_revenue_day"
        if "measure.price" in measures and request.requested_grain == "listing":
            return "highest_price_listing"
        if "measure.monthly_sold" in measures and request.requested_grain == "listing":
            return "highest_monthly_sold_listing"
        if "derived.product_count" in measures and "entity.shop" in dimensions:
            return "top_shop_by_listing_count"
    if "derived.product_count" in measures and not analytical_dimensions:
        return "listing_count"
    return None


def build_analytical_plan(kind: str, country: str) -> LogicalQueryPlan:
    builders = {
        "highest_revenue_day": _highest_revenue_day,
        "listing_count": _listing_count,
        "highest_price_listing": _highest_listing,
        "highest_monthly_sold_listing": _highest_listing,
        "top_shop_by_listing_count": _top_shop_by_listing_count,
        "price_change_by_date": _price_change_by_date,
    }
    builder = builders.get(kind)
    if builder is None:
        raise AnalyticalPlanError(f"Chưa có analytical template cho: {kind}")
    return builder(kind, country)


def _price_change_by_date(kind: str, country: str) -> LogicalQueryPlan:
    """Median observed listing price per dataset snapshot; no causal inference."""
    output = (
        OutputField(name="date", type="date", semantic_ref="dim.date"),
        OutputField(name="price", type="number", semantic_ref="measure.price"),
    )
    return LogicalQueryPlan(
        plan_id=f"open:price_change_by_date:{country}:1.0",
        time_scope=("2026-07-01", "2026-07-02", "2026-07-03"),
        output_node="n3", requested_output_shape=output,
        nodes=(
            PlanNode(
                node_id="n1", op="Scan", source="product_snapshot_metrics.csv",
                refs=("dim.date", "measure.price"), input_grain="listing_snapshot",
                output_grain="listing_snapshot", expected_schema=output,
                expected_cardinality="<=3341",
            ),
            PlanNode(
                node_id="n2", op="Filter", inputs=("n1",), predicates=(
                    Predicate(ref="dim.country", op="eq", parameter="country", value=country),
                    Predicate(ref="measure.price", op="gte", parameter="price_floor", value=0),
                    Predicate(ref="measure.price", op="lt", parameter="price_sentinel", value=999999999),
                ), input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="<=2046",
            ),
            PlanNode(
                node_id="n3", op="Aggregate", inputs=("n2",), refs=("measure.price",),
                group_by=("dim.date",), aggregation="median",
                input_grain="listing_snapshot", output_grain="date",
                expected_schema=output, expected_cardinality="3",
                invariants=("unique:date", "nonnegative:price"),
            ),
        ),
    )


def _highest_revenue_day(kind: str, country: str) -> LogicalQueryPlan:
    output = (
        OutputField(name="date", type="date", semantic_ref="dim.date"),
        OutputField(
            name="estimated_recent_revenue", type="number",
            semantic_ref="derived.estimated_recent_revenue",
        ),
    )
    return LogicalQueryPlan(
        plan_id=f"analytical:highest_revenue_day:{country}:1.0",
        time_scope=("2026-07-01", "2026-07-02", "2026-07-03"),
        output_node="n4",
        requested_output_shape=output,
        nodes=(
            PlanNode(
                node_id="n1", op="Scan", source="product_snapshot_metrics.csv",
                refs=("dim.date", "derived.estimated_recent_revenue"),
                input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="<=3341",
            ),
            PlanNode(
                node_id="n2", op="Filter", inputs=("n1",),
                predicates=(Predicate(ref="dim.country", op="eq", parameter="country", value=country),),
                input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="<=2046",
            ),
            PlanNode(
                node_id="n3", op="Aggregate", inputs=("n2",),
                refs=("derived.estimated_recent_revenue",), group_by=("dim.date",), aggregation="sum",
                input_grain="listing_snapshot", output_grain="date",
                expected_schema=output, expected_cardinality="3",
            ),
            PlanNode(
                node_id="n4", op="Rank", inputs=("n3",),
                rank_by="derived.estimated_recent_revenue", descending=True, limit=1,
                input_grain="date", output_grain="date", expected_schema=output,
                expected_cardinality="1",
                invariants=("unique:date", "nonnegative:estimated_recent_revenue"),
            ),
        ),
    )


def _listing_count(kind: str, country: str) -> LogicalQueryPlan:
    output = (OutputField(name="listing_count", type="integer", semantic_ref="derived.product_count"),)
    return LogicalQueryPlan(
        plan_id=f"analytical:{kind}:{country}:1.0", time_scope=("2026-07-03",),
        output_node="n3", requested_output_shape=output,
        nodes=(
            PlanNode(
                node_id="n1", op="Scan", source="products_clean.csv",
                refs=("entity.product_listing",), input_grain="listing_snapshot",
                output_grain="listing_snapshot", expected_schema=output, expected_cardinality="<=3341",
            ),
            PlanNode(
                node_id="n2", op="Filter", inputs=("n1",),
                predicates=(
                    Predicate(ref="dim.country", op="eq", parameter="country", value=country),
                    Predicate(ref="dim.date", op="eq", parameter="date", value="2026-07-03"),
                ),
                input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="<=682",
            ),
            PlanNode(
                node_id="n3", op="Aggregate", inputs=("n2",), refs=("derived.product_count",),
                aggregation="count", input_grain="listing_snapshot", output_grain="country_snapshot",
                expected_schema=output, expected_cardinality="1", invariants=("nonnegative:listing_count",),
            ),
        ),
    )


def _highest_listing(kind: str, country: str) -> LogicalQueryPlan:
    metric_ref = "measure.price" if kind == "highest_price_listing" else "measure.monthly_sold"
    metric_name = "price" if kind == "highest_price_listing" else "monthly_sold"
    unit_type = "number"
    output = (
        OutputField(name="product_name", type="string", semantic_ref="dim.product_name"),
        OutputField(name=metric_name, type=unit_type, semantic_ref=metric_ref),
    )
    predicates = [
        Predicate(ref="dim.country", op="eq", parameter="country", value=country),
        Predicate(ref="dim.date", op="eq", parameter="date", value="2026-07-03"),
        Predicate(ref=metric_ref, op="gte", parameter="metric_floor", value=0),
    ]
    if kind == "highest_price_listing":
        predicates.append(Predicate(ref="measure.price", op="lt", parameter="price_sentinel", value=999999999))
    return LogicalQueryPlan(
        plan_id=f"analytical:{kind}:{country}:1.0", time_scope=("2026-07-03",),
        output_node="n4", requested_output_shape=output,
        nodes=(
            PlanNode(
                node_id="n1", op="Scan", source="products_clean.csv",
                refs=("dim.product_name", metric_ref), input_grain="listing_snapshot",
                output_grain="listing_snapshot", expected_schema=output, expected_cardinality="<=3341",
            ),
            PlanNode(
                node_id="n2", op="Filter", inputs=("n1",), predicates=tuple(predicates),
                input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="<=682",
            ),
            PlanNode(
                node_id="n3", op="Rank", inputs=("n2",), rank_by=metric_ref, descending=True, limit=1,
                input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="1",
            ),
            PlanNode(
                node_id="n4", op="Project", inputs=("n3",), refs=("dim.product_name", metric_ref),
                input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="1",
                invariants=(f"nonnegative:{metric_name}",),
            ),
        ),
    )


def _top_shop_by_listing_count(kind: str, country: str) -> LogicalQueryPlan:
    output = (
        OutputField(name="shop_id", type="string", semantic_ref="entity.shop"),
        OutputField(name="shop_name", type="string", semantic_ref="dim.shop_name"),
        OutputField(name="listing_count", type="integer", semantic_ref="derived.product_count"),
    )
    return LogicalQueryPlan(
        plan_id=f"analytical:{kind}:{country}:1.0", time_scope=("2026-07-03",),
        output_node="n5", requested_output_shape=output,
        nodes=(
            PlanNode(
                node_id="n1", op="Scan", source="products_clean.csv",
                refs=("entity.shop", "entity.product_listing"), input_grain="listing_snapshot",
                output_grain="listing_snapshot", expected_schema=output, expected_cardinality="<=3341",
            ),
            PlanNode(
                node_id="n2", op="Filter", inputs=("n1",),
                predicates=(
                    Predicate(ref="dim.country", op="eq", parameter="country", value=country),
                    Predicate(ref="dim.date", op="eq", parameter="date", value="2026-07-03"),
                ),
                input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="<=682",
            ),
            PlanNode(
                node_id="n3", op="Join", inputs=("n2",), relation="belongs_to",
                refs=("entity.shop", "dim.shop_name"), input_grain="listing_snapshot",
                output_grain="listing_snapshot", expected_schema=output, expected_cardinality="<=682",
            ),
            PlanNode(
                node_id="n4", op="Aggregate", inputs=("n3",), refs=("derived.product_count",),
                group_by=("entity.shop", "dim.shop_name"), aggregation="count",
                input_grain="listing_snapshot", output_grain="shop",
                expected_schema=output, expected_cardinality="<=20",
            ),
            PlanNode(
                node_id="n5", op="Rank", inputs=("n4",), rank_by="derived.product_count",
                descending=True, limit=1, input_grain="shop", output_grain="shop",
                expected_schema=output, expected_cardinality="1",
                invariants=("unique:shop_id", "nonnegative:listing_count"),
            ),
        ),
    )
