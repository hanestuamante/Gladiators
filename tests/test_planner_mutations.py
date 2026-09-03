import json
from pathlib import Path

import pandas as pd
import pytest

from gladiators.data.repository import ArtifactRepository
from gladiators.planner.analytical import build_analytical_plan
from gladiators.planner.compiler import CompiledQuery, CompilationError, compile_plan
from gladiators.planner.executor import QueryExecutor
from gladiators.planner.query_ir import LogicalQueryPlan, OutputField, PlanBudget, PlanNode, Predicate
from gladiators.planner.validator import validate_plan
from gladiators.planner.semantic_parser import DeterministicSemanticParser
from gladiators.planner.macros import default_macro_registry
from gladiators.agent.workflow import AgentRuntime
from gladiators.domain.relations import RELATIONS
from scripts.build_eval_coverage_matrix import build
from eval.independent.l4_oracle import build_l4_denotation
from eval.independent.oracle import _sha256, build_oracle
from conftest import DATA_DIR


def _codes(plan: LogicalQueryPlan) -> set[str]:
    return {issue.code for issue in validate_plan(plan).issues}


def _replace_node(plan: LogicalQueryPlan, node_id: str, **updates) -> LogicalQueryPlan:
    return plan.model_copy(update={
        "nodes": tuple(
            node.model_copy(update=updates) if node.node_id == node_id else node
            for node in plan.nodes
        ),
    })


def test_validator_mutation_taxonomy_is_executable():
    price = build_analytical_plan("highest_price_listing", "vn")
    unknown_ref = _replace_node(price, "n1", refs=("measure.not_exposed",))
    wrong_filter = _replace_node(
        price, "n2", predicates=(Predicate(
            ref="measure.price", op="contains", parameter="payload", value="x",
        ),),
    )
    top_shop = build_analytical_plan("top_shop_by_listing_count", "vn")
    wrong_join = _replace_node(top_shop, "n3", relation="platform_to_shop_category")
    wrong_grain = _replace_node(top_shop, "n3", input_grain="shop")
    mixed_units = _replace_node(price, "n3", units=("VND", "IDR"))
    causal = _replace_node(price, "n4", invariants=("causal:price",))
    budget = price.model_copy(update={"budget": PlanBudget(max_nodes=1, max_depth=6, max_subplans=4)})
    cycle = _replace_node(price, "n1", inputs=("n4",))

    assert "missing_semantic_object" in _codes(unknown_ref)
    assert "wrong_filter" in _codes(wrong_filter)
    assert "wrong_join_path" in _codes(wrong_join)
    assert "grain_mismatch" in _codes(wrong_grain)
    assert "unit_mismatch" in _codes(mixed_units)
    assert "unsupported_claim" in _codes(causal)
    assert "budget_exceeded" in _codes(budget)
    assert "schema_invalid" in _codes(cycle)


def test_validator_blocks_fanout_aggregate_without_dedupe():
    output = (OutputField(name="listing_count", type="integer", semantic_ref="derived.product_count"),)
    plan = LogicalQueryPlan(
        plan_id="mutation:fanout", time_scope=("2026-07-03",), output_node="n3",
        requested_output_shape=output,
        nodes=(
            PlanNode(
                node_id="n1", op="Scan", source="products_clean.csv",
                refs=("entity.product_listing",), input_grain="listing_snapshot",
                output_grain="listing_snapshot", expected_schema=output,
                expected_cardinality="<=3341",
            ),
            PlanNode(
                node_id="n2", op="Join", inputs=("n1",), relation="in_shop_category",
                dedupe_policy="one_row_per_listing", input_grain="listing_snapshot",
                output_grain="listing_snapshot_x_shelf", expected_schema=output,
                expected_cardinality="<=5000",
            ),
            PlanNode(
                node_id="n3", op="Aggregate", inputs=("n2",), refs=("derived.product_count",),
                aggregation="count", input_grain="listing_snapshot_x_shelf",
                output_grain="country", expected_schema=output, expected_cardinality="1",
            ),
        ),
    )
    assert "fanout_risk" in _codes(plan)


def test_validator_blocks_cross_snapshot_revenue_sum():
    plan = build_analytical_plan("highest_revenue_day", "vn")
    mutated = _replace_node(plan, "n3", group_by=())
    assert "temporal_mismatch" in _codes(mutated)


def test_compiler_parameterizes_user_values():
    plan = build_analytical_plan("highest_price_listing", "vn")
    payload = "vn'; DROP TABLE products; --"
    node = next(item for item in plan.nodes if item.node_id == "n2")
    predicates = tuple(
        predicate.model_copy(update={"value": payload})
        if predicate.ref == "dim.country" else predicate
        for predicate in node.predicates
    )
    compiled = compile_plan(_replace_node(plan, "n2", predicates=predicates))
    assert payload not in compiled.sql
    assert payload in compiled.parameters
    assert "?" in compiled.sql


@pytest.mark.parametrize("sql", [
    "DROP VIEW products",
    "COPY products TO '/tmp/leak.csv'",
    "ATTACH 'remote.db' AS remote",
    "SELECT * FROM read_csv_auto('https://example.com/data.csv')",
    "SELECT 1; SELECT 2",
])
def test_executor_rejects_non_compiler_or_external_sql(sql):
    executor = QueryExecutor(ArtifactRepository(DATA_DIR))
    query = CompiledQuery(
        sql=sql, parameters=(), plan_hash="mutation", expected_columns=(), postconditions=(),
    )
    try:
        with pytest.raises(CompilationError):
            executor.execute(query)
    finally:
        executor.close()


def test_coverage_matrix_is_generated_from_executable_registries():
    matrix = build()
    assert matrix["source"]["ir_operators"] == 12
    # 11 sau khi thêm ``shop_observed_at`` (Shop → DateSnapshot trên panel ngày).
    assert matrix["source"]["relation_edges"] == 11
    assert matrix["source"]["catalog_objects"] > 70
    assert matrix["summary"]["phase_4_5_acceptance_ready"] is True
    assert matrix["summary"]["missing"] == 0
    # Năng lực đọc một artifact chưa thu KHÔNG được đếm là đạt, cũng không được
    # đếm là thiếu — nó là một khoảng trống có nguyên nhân khác hẳn. Test khoá
    # đúng chỗ đó: nó phải nằm ở ``not_measured`` và mang lý do đọc được.
    assert matrix["summary"]["not_measured"] == len(matrix["not_measured"]) > 0
    assert all(item["reason"] for item in matrix["not_measured"])
    assert all(not item["satisfied"] for item in matrix["not_measured"])
    assert {item["value"] for item in matrix["requirements"]}.isdisjoint(
        {item["value"] for item in matrix["not_measured"]}
    )
    assert any(
        item["axis"] == "ops" and item["value"] == "Filter" and item["observed"] >= 3
        for item in matrix["requirements"]
    )


def test_mutation_manifest_ids_and_expectations_are_unique():
    cases = json.loads(Path("eval/planner_mutations.json").read_text(encoding="utf-8"))
    assert len(cases) == 21
    assert len({case["id"] for case in cases}) == len(cases)
    assert all(case.get("expected_issue") or case.get("expected_rule") or case.get("expected") for case in cases)


def test_delegated_operator_contract_mutations_are_rejected():
    macros = default_macro_registry()
    sales = macros.get("sales_decline").plan_template
    similar = macros.get("similar_product").plan_template
    bad_resolve = _replace_node(sales, "n1", refs=("measure.price",))
    bad_temporal = sales.model_copy(update={"time_scope": ("2026-07-03",)})
    bad_similarity = _replace_node(similar, "n2", refs=("measure.price",))
    price = build_analytical_plan("highest_price_listing", "vn")
    bad_rank = _replace_node(price, "n3", rank_by=None, limit=None)
    bad_dedupe = _replace_node(price, "n3", op="Dedupe", dedupe_policy=None)

    for plan in (bad_resolve, bad_similarity, bad_rank, bad_dedupe):
        assert "schema_invalid" in _codes(plan)
    assert "temporal_mismatch" in _codes(bad_temporal)


def test_promotion_observations_cannot_be_aggregated_across_snapshots():
    output = (OutputField(name="count", type="integer", semantic_ref="derived.product_count"),)
    plan = LogicalQueryPlan(
        plan_id="mutation:promotion_across_time",
        time_scope=("2026-07-01", "2026-07-02", "2026-07-03"),
        output_node="n3", requested_output_shape=output,
        nodes=(
            PlanNode(node_id="n1", op="Scan", source="products_clean.csv",
                     refs=("entity.product_listing",), input_grain="listing_snapshot",
                     output_grain="listing_snapshot", expected_schema=output,
                     expected_cardinality="<=3341"),
            PlanNode(node_id="n2", op="Join", inputs=("n1",),
                     relation="observed_promotion_id", input_grain="listing_snapshot",
                     output_grain="listing_snapshot", expected_schema=output,
                     expected_cardinality="<=3341"),
            PlanNode(node_id="n3", op="Aggregate", inputs=("n2",),
                     refs=("derived.product_count",), aggregation="count",
                     input_grain="listing_snapshot", output_grain="country",
                     expected_schema=output, expected_cardinality="1"),
        ),
    )
    assert "temporal_mismatch" in _codes(plan)


def test_independent_oracle_matches_frozen_gold_and_imports_no_production_code():
    source = Path("eval/independent/oracle.py").read_text(encoding="utf-8")
    assert "from gladiators" not in source and "import gladiators" not in source
    frozen = json.loads(Path("eval/independent/golden_v2.json").read_text(encoding="utf-8"))
    assert build_oracle(DATA_DIR) == frozen


def test_independent_oracle_hash_is_newline_canonical(tmp_path):
    lf = tmp_path / "same.csv"
    lf.write_bytes(b"a,b\n1,2\n")
    first = _sha256((lf,))
    lf.write_bytes(b"a,b\r\n1,2\r\n")
    assert _sha256((lf,)) == first


@pytest.mark.parametrize(
    "case",
    json.loads(Path("eval/semantic_linking.json").read_text(encoding="utf-8")),
    ids=lambda case: case["id"],
)
def test_semantic_linking_cases_resolve_only_expected_catalog_objects(case):
    request = DeterministicSemanticParser().parse(case["question"], "vi", case["country"])
    measures = {item.ref for item in request.requested_measures if item.ref}
    dimensions = {item.ref for item in request.requested_dimensions if item.ref}
    assert measures == set(case["expected_measures"])
    assert dimensions == set(case["expected_dimensions"])


def _execute(plan: LogicalQueryPlan):
    executor = QueryExecutor(ArtifactRepository(DATA_DIR))
    try:
        return executor.execute(compile_plan(plan)).frame
    finally:
        executor.close()


@pytest.mark.parametrize("country", ["vn", "id"])
def test_dedupe_operator_compiles_and_executes(country):
    output = (
        OutputField(name="product_name", type="string", semantic_ref="dim.product_name"),
        OutputField(name="price", type="number", semantic_ref="measure.price"),
    )
    plan = LogicalQueryPlan(
        plan_id=f"operator:dedupe:{country}", time_scope=("2026-07-03",), output_node="n4",
        requested_output_shape=output,
        nodes=(
            PlanNode(node_id="n1", op="Scan", source="products_clean.csv",
                     refs=("entity.product_listing", "dim.product_name", "measure.price"),
                     input_grain="listing_snapshot", output_grain="listing_snapshot",
                     expected_schema=output, expected_cardinality="<=3341"),
            PlanNode(node_id="n2", op="Filter", inputs=("n1",), predicates=(
                Predicate(ref="dim.country", op="eq", parameter="country", value=country),
            ), input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="<=2046"),
            PlanNode(node_id="n3", op="Dedupe", inputs=("n2",),
                     dedupe_policy="one_snapshot_per_listing", input_grain="listing_snapshot",
                     output_grain="listing", expected_schema=output, expected_cardinality="<=682"),
            PlanNode(node_id="n4", op="Project", inputs=("n3",),
                     refs=("dim.product_name", "measure.price"), input_grain="listing",
                     output_grain="listing", expected_schema=output, expected_cardinality="<=682"),
        ),
    )
    frame = _execute(plan)
    assert not frame.empty and tuple(frame.columns) == ("product_name", "price")
    products = ArtifactRepository(DATA_DIR).products
    expected = products.loc[products.country_code == country].product_listing_key.nunique()
    assert len(frame) == expected


@pytest.mark.parametrize("country,metric", [
    ("vn", "derived.estimated_recent_revenue"),
    ("id", "derived.estimated_recent_revenue"),
    ("vn", "derived.has_structured_voucher"),
])
def test_derive_metric_operator_executes_materialized_registry_metric(country, metric):
    name = metric.split(".")[-1]
    output = (OutputField(name=name, type="number", semantic_ref=metric),)
    plan = LogicalQueryPlan(
        plan_id=f"operator:derive:{country}:{name}", time_scope=("2026-07-03",), output_node="n4",
        requested_output_shape=output,
        nodes=(
            PlanNode(node_id="n1", op="Scan", source="product_snapshot_metrics.csv", refs=(metric,),
                     input_grain="listing_snapshot", output_grain="listing_snapshot",
                     expected_schema=output, expected_cardinality="<=3341"),
            PlanNode(node_id="n2", op="Filter", inputs=("n1",), predicates=(
                Predicate(ref="dim.country", op="eq", parameter="country", value=country),
                Predicate(ref="dim.date", op="eq", parameter="date", value="2026-07-03"),
            ), input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="<=682"),
            PlanNode(node_id="n3", op="DeriveMetric", inputs=("n2",), refs=(metric,),
                     input_grain="listing_snapshot", output_grain="listing_snapshot",
                     expected_schema=output, expected_cardinality="<=682"),
            PlanNode(node_id="n4", op="Project", inputs=("n3",), refs=(metric,),
                     input_grain="listing_snapshot", output_grain="listing_snapshot",
                     expected_schema=output, expected_cardinality="<=682"),
        ),
    )
    assert not _execute(plan).empty


@pytest.mark.parametrize("country,metric", [
    ("vn", "derived.monthly_sold_delta"),
    ("id", "derived.price_change"),
    ("vn", "derived.rating_change"),
])
def test_temporal_compare_operator_executes_transition_metrics(country, metric):
    name = metric.split(".")[-1]
    output = (OutputField(name=name, type="number", semantic_ref=metric),)
    plan = LogicalQueryPlan(
        plan_id=f"operator:temporal:{country}:{name}",
        time_scope=("2026-07-02", "2026-07-03"), output_node="n4",
        requested_output_shape=output,
        nodes=(
            PlanNode(node_id="n1", op="Scan", source="product_transition_metrics.csv", refs=(metric,),
                     input_grain="transition", output_grain="transition",
                     expected_schema=output, expected_cardinality="<=2184"),
            PlanNode(node_id="n2", op="Filter", inputs=("n1",), predicates=(
                Predicate(ref="dim.country", op="eq", parameter="country", value=country),
            ), input_grain="transition", output_grain="transition",
                expected_schema=output, expected_cardinality="<=1500"),
            PlanNode(node_id="n3", op="TemporalCompare", inputs=("n2",), refs=(metric,),
                     input_grain="transition", output_grain="transition",
                     expected_schema=output, expected_cardinality="<=1500"),
            PlanNode(node_id="n4", op="Project", inputs=("n3",), refs=(metric,),
                     input_grain="transition", output_grain="transition",
                     expected_schema=output, expected_cardinality="<=1500"),
        ),
    )
    assert tuple(_execute(plan).columns) == (name,)


@pytest.mark.parametrize("left_country,right_country,ref", [
    ("vn", "id", "dim.product_name"),
    ("id", "vn", "dim.product_name"),
    ("vn", "id", "dim.brand"),
])
def test_union_operator_executes_two_scoped_branches(left_country, right_country, ref):
    name = ref.split(".")[-1]
    output = (OutputField(name=name, type="string", semantic_ref=ref),)
    nodes = []
    for prefix, country in (("l", left_country), ("r", right_country)):
        nodes.extend((
            PlanNode(node_id=f"{prefix}1", op="Scan", source="products_clean.csv", refs=(ref,),
                     input_grain="listing_snapshot", output_grain="listing_snapshot",
                     expected_schema=output, expected_cardinality="<=3341"),
            PlanNode(node_id=f"{prefix}2", op="Filter", inputs=(f"{prefix}1",), predicates=(
                Predicate(ref="dim.country", op="eq", parameter="country", value=country),
                Predicate(ref="dim.date", op="eq", parameter="date", value="2026-07-03"),
            ), input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="<=682"),
            PlanNode(node_id=f"{prefix}3", op="Project", inputs=(f"{prefix}2",), refs=(ref,),
                     input_grain="listing_snapshot", output_grain="listing_snapshot",
                     expected_schema=output, expected_cardinality="<=682"),
        ))
    nodes.append(PlanNode(
        node_id="u1", op="Union", inputs=("l3", "r3"), input_grain="listing_snapshot",
        output_grain="listing_snapshot", expected_schema=output, expected_cardinality="<=1364",
    ))
    plan = LogicalQueryPlan(
        plan_id=f"operator:union:{name}", time_scope=("2026-07-03",), output_node="u1",
        requested_output_shape=output, nodes=tuple(nodes),
    )
    frame = _execute(plan)
    assert not frame.empty and tuple(frame.columns) == (name,)


def test_resolve_and_similarity_delegated_operators_execute_via_certified_macro(tmp_path):
    runtime = AgentRuntime(trace_dir=tmp_path)
    keys = runtime.repo.products.drop_duplicates("product_listing_key").product_listing_key.astype(str).tolist()
    for key in (keys[0], keys[len(keys) // 2], keys[-1]):
        response = runtime.run(f'Tìm sản phẩm tương tự "{key}"')
        assert response.gate.action == "allow"
        assert [call.name for call in response.tool_calls] == ["resolve_entity", "find_similar"]
        assert len(response.evidence) == 5


def test_operator_acceptance_manifest_has_three_positive_cases_per_target_operator():
    cases = json.loads(Path("eval/operator_acceptance.json").read_text(encoding="utf-8"))
    counts = {}
    for case in cases:
        for op in case["coverage"]["ops"]:
            counts[op] = counts.get(op, 0) + 1
    for op in ("ResolveValue", "Dedupe", "DeriveMetric", "TemporalCompare", "Similarity", "Union"):
        assert counts[op] >= 3


@pytest.mark.parametrize("country", ["vn", "id"])
@pytest.mark.parametrize("relation_name,source,output_ref", [
    ("observed_at", "products_clean.csv", "dim.date"),
    ("in_platform_category", "products_clean.csv", "dim.platform_category_name"),
    ("in_shop_category", "product_categories_clean.csv", "dim.shop_category_name"),
    ("has_brand", "products_clean.csv", "dim.brand"),
    ("observed_promotion_id", "products_clean.csv", "measure.discount_percent"),
    ("observed_structured_voucher", "products_clean.csv", "measure.voucher_discount"),
    ("has_content", "products_clean.csv", "measure.images_count"),
    ("has_display_variation", "products_clean.csv", "dim.display_variation"),
])
def test_relation_adapters_compile_and_execute(country, relation_name, source, output_ref):
    relation = RELATIONS[relation_name]
    field_name = output_ref.split(".")[-1]
    output_type = "date" if output_ref == "dim.date" else "number" if output_ref.startswith("measure.") else "string"
    output = (OutputField(name=field_name, type=output_type, semantic_ref=output_ref),)
    plan = LogicalQueryPlan(
        plan_id=f"relation:{relation_name}:{country}", time_scope=("2026-07-03",), output_node="n4",
        requested_output_shape=output,
        nodes=(
            PlanNode(node_id="n1", op="Scan", source=source, refs=(output_ref,),
                     input_grain=relation.input_grain, output_grain=relation.input_grain,
                     expected_schema=output, expected_cardinality="<=5000"),
            PlanNode(node_id="n2", op="Filter", inputs=("n1",), predicates=(
                Predicate(ref="dim.country", op="eq", parameter="country", value=country),
                Predicate(ref="dim.date", op="eq", parameter="date", value="2026-07-03"),
            ), input_grain=relation.input_grain, output_grain=relation.input_grain,
                expected_schema=output, expected_cardinality="<=2000"),
            PlanNode(node_id="n3", op="Join", inputs=("n2",), relation=relation_name,
                     dedupe_policy=relation.dedupe_strategy, input_grain=relation.input_grain,
                     output_grain=relation.output_grain, expected_schema=output,
                     expected_cardinality="<=5000"),
            PlanNode(node_id="n4", op="Project", inputs=("n3",), refs=(output_ref,),
                     input_grain=relation.output_grain, output_grain=relation.output_grain,
                     expected_schema=output, expected_cardinality="<=5000"),
        ),
    )
    frame = _execute(plan)
    assert not frame.empty and tuple(frame.columns) == (field_name,)
    if relation_name in {"in_platform_category", "in_shop_category"}:
        assert frame[field_name].notna().any()


def test_relation_validator_rejects_correct_edge_on_wrong_left_artifact():
    relation = RELATIONS["in_platform_category"]
    output = (OutputField(name="category", type="string", semantic_ref="dim.platform_category_name"),)
    plan = LogicalQueryPlan(
        plan_id="relation:wrong_source", time_scope=("2026-07-03",), output_node="n2",
        requested_output_shape=output,
        nodes=(
            PlanNode(node_id="n1", op="Scan", source="shop_info_clean.csv",
                     refs=("dim.platform_category_name",), input_grain=relation.input_grain,
                     output_grain=relation.input_grain, expected_schema=output,
                     expected_cardinality="20"),
            PlanNode(node_id="n2", op="Join", inputs=("n1",), relation=relation.name,
                     input_grain=relation.input_grain, output_grain=relation.output_grain,
                     expected_schema=output, expected_cardinality="20"),
        ),
    )
    assert "wrong_join_path" in _codes(plan)


@pytest.mark.parametrize("country", ["vn", "id"])
def test_has_sales_metric_relation_joins_listing_to_governed_snapshots(country):
    output = (OutputField(
        name="estimated_recent_revenue", type="number",
        semantic_ref="derived.estimated_recent_revenue",
    ),)
    plan = LogicalQueryPlan(
        plan_id=f"relation:has_sales_metric:{country}",
        time_scope=("2026-07-01", "2026-07-02", "2026-07-03"), output_node="n5",
        requested_output_shape=output,
        nodes=(
            PlanNode(node_id="n1", op="Scan", source="products_clean.csv",
                     refs=("entity.product_listing",), input_grain="listing_snapshot",
                     output_grain="listing_snapshot", expected_schema=output,
                     expected_cardinality="<=3341"),
            PlanNode(node_id="n2", op="Filter", inputs=("n1",), predicates=(
                Predicate(ref="dim.country", op="eq", parameter="country", value=country),
                Predicate(ref="dim.date", op="eq", parameter="date", value="2026-07-03"),
            ), input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="<=682"),
            PlanNode(node_id="n3", op="Dedupe", inputs=("n2",),
                     dedupe_policy="one_row_per_listing", input_grain="listing_snapshot",
                     output_grain="listing", expected_schema=output, expected_cardinality="<=682"),
            PlanNode(node_id="n4", op="Join", inputs=("n3",), relation="has_sales_metric",
                     dedupe_policy="metric_grain_required", input_grain="listing",
                     output_grain="listing_snapshot_or_transition", expected_schema=output,
                     expected_cardinality="<=2046"),
            PlanNode(node_id="n5", op="Project", inputs=("n4",),
                     refs=("derived.estimated_recent_revenue",),
                     input_grain="listing_snapshot_or_transition",
                     output_grain="listing_snapshot_or_transition", expected_schema=output,
                     expected_cardinality="<=2046"),
        ),
    )
    frame = _execute(plan)
    assert not frame.empty
    assert frame.estimated_recent_revenue.notna().any()


def test_relation_acceptance_manifest_has_two_cases_per_implemented_edge():
    cases = json.loads(Path("eval/relation_acceptance.json").read_text(encoding="utf-8"))
    counts = {}
    for case in cases:
        counts[case["relation"]] = counts.get(case["relation"], 0) + 1
    for relation in (
        "observed_at", "in_platform_category", "in_shop_category", "has_brand",
        "observed_promotion_id", "observed_structured_voucher", "has_content",
        "has_display_variation", "has_sales_metric",
    ):
        assert counts[relation] >= 2


def _empty_brand_plan(country: str, metric: str) -> LogicalQueryPlan:
    metric_name = metric.split(".")[-1]
    output = (
        OutputField(name="brand", type="string", semantic_ref="dim.brand"),
        OutputField(name=metric_name, type="number", semantic_ref=metric),
    )
    return LogicalQueryPlan(
        plan_id=f"open:empty_brand:{country}:{metric_name}",
        time_scope=("2026-07-03",), output_node="n3", requested_output_shape=output,
        nodes=(
            PlanNode(node_id="n1", op="Scan", source="products_clean.csv",
                     refs=("dim.brand", metric), input_grain="listing_snapshot",
                     output_grain="listing_snapshot", expected_schema=output,
                     expected_cardinality="<=3341"),
            PlanNode(node_id="n2", op="Filter", inputs=("n1",), predicates=(
                Predicate(ref="dim.country", op="eq", parameter="country", value=country),
                Predicate(ref="dim.date", op="eq", parameter="date", value="2026-07-03"),
                Predicate(ref="dim.brand", op="eq", parameter="brand", value="__brand_does_not_exist__"),
            ), input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="0"),
            PlanNode(node_id="n3", op="Project", inputs=("n2",), refs=("dim.brand", metric),
                     input_grain="listing_snapshot", output_grain="listing_snapshot",
                     expected_schema=output, expected_cardinality="0"),
        ),
    )


@pytest.mark.parametrize(
    "case",
    json.loads(Path("eval/empty_result_acceptance.json").read_text(encoding="utf-8")),
    ids=lambda case: case["id"],
)
def test_an_unverified_empty_result_is_refused_not_allowed(case, tmp_path):
    metric = "measure.price" if "Price" in case["question"] else "measure.rating"
    plan = _empty_brand_plan(case["country"], metric)

    class EmptyPlanner:
        provider, model, prompt_version = "test", "empty", "p8-empty"

        def plan_analytical(self, payload):
            return plan.model_dump(mode="json")

    response = AgentRuntime(trace_dir=tmp_path, llm_client=EmptyPlanner()).run(case["question"])
    # ĐỔI CONTRACT CÓ CHỦ ĐÍCH (SolutionSpec2808 §2.10, W1.8): literal
    # "__brand_does_not_exist__" không tồn tại trong value index, nên số 0 này
    # KHÔNG chứng minh được bộ lọc đã chạy đúng giá trị — nó chính là hình lỗi
    # brand='bibica' (dữ liệu ghi 'Bibica', đáp án 96) mà W1 sinh ra để chặn.
    # Zero-row VỚI literal đã verified vẫn là allow — xem
    # tests/test_value_binding.py::test_a_verified_zero_row_is_still_a_result.
    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A-EMPTY-RESULT-UNVERIFIED"
    assert response.evidence == []
    fired = response.planning["empty_result"]["handler_fired"]
    assert fired == {"zero_row_relaxed": False, "filter_literal": True}


def _l4_brand_plan(country: str, measures: list[str]) -> LogicalQueryPlan:
    output = (OutputField(name="brand", type="string", semantic_ref="dim.brand"),) + tuple(
        OutputField(name=ref.split(".")[-1], type="number", semantic_ref=ref) for ref in measures
    )
    sentinel_predicates = tuple(
        Predicate(ref=ref, op="lt", parameter=f"{ref.split('.')[-1]}_sentinel", value=999999999)
        for ref in measures if ref in {"measure.price", "measure.price_original"}
    )
    return LogicalQueryPlan(
        plan_id=f"open:l4:{country}:" + "_".join(ref.split(".")[-1] for ref in measures),
        time_scope=("2026-07-03",), output_node="n3", requested_output_shape=output,
        nodes=(
            PlanNode(node_id="n1", op="Scan", source="products_clean.csv",
                     refs=("dim.brand", *measures), input_grain="listing_snapshot",
                     output_grain="listing_snapshot", expected_schema=output,
                     expected_cardinality="<=3341"),
            PlanNode(node_id="n2", op="Filter", inputs=("n1",), predicates=(
                Predicate(ref="dim.country", op="eq", parameter="country", value=country),
                Predicate(ref="dim.date", op="eq", parameter="date", value="2026-07-03"),
                *sentinel_predicates,
            ), input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="<=682"),
            PlanNode(node_id="n3", op="Aggregate", inputs=("n2",), refs=tuple(measures),
                     group_by=("dim.brand",), aggregation="max",
                     input_grain="listing_snapshot", output_grain="brand",
                     expected_schema=output, expected_cardinality="<=100"),
        ),
    )


def test_validator_requires_price_sentinel_filter_before_l4_aggregate():
    plan = _l4_brand_plan("vn", ["measure.price", "measure.rating"])
    nodes = tuple(
        node.model_copy(update={
            "predicates": tuple(p for p in node.predicates if p.ref != "measure.price")
        }) if node.op == "Filter" else node
        for node in plan.nodes
    )
    result = validate_plan(plan.model_copy(update={"nodes": nodes}))
    assert result.valid is False
    assert any(
        issue.code == "wrong_filter" and "sentinel" in issue.message
        for issue in result.issues
    )


# ĐỔI CONTRACT CÓ CHỦ ĐÍCH — W14 (SolutionSpec2808 §15). Đo trên dữ liệu thật:
# ``MAX(price_original)`` theo brand ở Indonesia trả 9 999 999 cho HAI brand —
# một giá trị giữ chỗ mà quy tắc chất lượng dữ liệu chưa ai duyệt. Trước W14 ca
# này khẳng định ``allow``, tức khẳng định một bảng có hai ô giữ chỗ nằm giữa
# các giá trị thật là một câu trả lời. Không có lớp nào phía sau bắt được: tie
# detector chỉ sống trên đường Rank.
VALUE_CLASS_BLOCKED_L4 = {"l4c04"}


@pytest.mark.parametrize(
    "case",
    json.loads(Path("eval/l4_acceptance.json").read_text(encoding="utf-8")),
    ids=lambda case: f"oracle-{case['id']}",
)
def test_independent_l4_oracle_matches_validated_fixture_plan(case):
    plan = _l4_brand_plan(case["country"], case["measures"])
    repository = ArtifactRepository(DATA_DIR)
    executor = QueryExecutor(repository)
    try:
        actual = executor.execute(compile_plan(plan)).frame
    finally:
        executor.close()
    expected = build_l4_denotation(case)
    actual_rows = [
        {
            column: None if pd.isna(value) else value.item() if hasattr(value, "item") else value
            for column, value in zip(actual.columns, row)
        }
        for row in actual.itertuples(index=False, name=None)
    ]
    assert sorted(actual_rows, key=lambda row: str(row["brand"])) == sorted(
        expected, key=lambda row: str(row["brand"])
    )


@pytest.mark.parametrize(
    "case",
    json.loads(Path("eval/l4_acceptance.json").read_text(encoding="utf-8")),
    ids=lambda case: case["id"],
)

def test_composite_l4_runs_two_blinded_agreeing_planners(case, tmp_path):
    plan = _l4_brand_plan(case["country"], case["measures"])

    class AgreeingL4Planner:
        provider, model, prompt_version = "test", "l4", "p10-l4"

        def plan_analytical(self, payload):
            return plan.model_dump(mode="json")

        def plan_analytical_alternate(self, payload):
            assert "candidates" not in payload and "validator_feedback" in payload
            return plan.model_dump(mode="json")

    response = AgentRuntime(
        trace_dir=tmp_path, llm_client=AgreeingL4Planner(), enable_nversion=True,
    ).run(case["question"])
    # Cơ chế L4 (hai planner bịt mắt, không bất đồng) phải đúng cho MỌI ca —
    # kể cả ca bị chặn ở lớp sau, nếu không "cơ chế chạy" và "cơ chế không bao
    # giờ tới lượt" là hai bảng số giống hệt nhau.
    assert response.planning["complexity_level"] == "L4"
    assert response.planning["escalation_mode"] == "nversion"
    assert response.planning["nversion"]["plan_disagreement"] is False
    assert set(case["measures"]).issubset({
        field.semantic_ref for field in plan.requested_output_shape
    })
    if case["id"] in VALUE_CLASS_BLOCKED_L4:
        assert response.gate.action == "abstain"
        assert response.gate.rule_id == "A19-VALUE-CLASS"
        return
    assert response.gate.action == "allow"
    assert response.evidence and response.verification["passed"] is True
