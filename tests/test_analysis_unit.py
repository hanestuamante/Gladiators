"""Theme A: an entity ref is the unit of analysis, not a grouping key.

``entity.product_listing`` answers "what is one row of this measurement", while
``dim.shop_name`` answers "which column splits the result".  Only the second
needs a physical column.  The catalog used one axis (``answerability``) for both
roles, so a ref could declare itself usable as a dimension while owning no
column to ``GROUP BY``; the validator believed the declaration and the compiler
enforced reality, with no layer comparing the two.
"""
from __future__ import annotations

import pytest

from gladiators.agent.workflow import AgentRuntime
from gladiators.domain.catalog import CATALOG
from gladiators.planner.query_ir import LogicalQueryPlan, OutputField, PlanNode
from gladiators.planner.semantic_parser import DeterministicSemanticParser
from gladiators.planner.validator import validate_plan


@pytest.fixture(scope="module")
def runtime(tmp_path_factory) -> AgentRuntime:
    return AgentRuntime(trace_dir=tmp_path_factory.mktemp("analysis-unit"))


def test_every_grouping_key_owns_a_physical_column():
    # A2: the build-time invariant. A ref that claims it can be grouped by and
    # has no column is the catalog contradicting itself, 28 refs deep.
    offenders = sorted(
        ref for ref, obj in CATALOG.items()
        if obj.analysis_role == "physical_dimension" and not obj.physical
    )
    assert offenders == []


def test_analysis_units_are_marked_and_countable():
    assert CATALOG["entity.product_listing"].analysis_role == "analysis_unit"
    assert CATALOG["entity.shop"].analysis_role == "analysis_unit"
    # Having a column is what makes a unit groupable; being a unit is what makes
    # it countable. The two are independent.
    assert CATALOG["entity.shop"].physical
    assert not CATALOG["entity.product_listing"].physical
    assert CATALOG["entity.shop"].counting_key == "shop_id"
    assert CATALOG["entity.product_listing"].counting_key == "product_listing_key"


def _plan_grouping_by(ref: str) -> LogicalQueryPlan:
    schema = (
        OutputField(name="unit", type="string", semantic_ref=ref),
        OutputField(name="price", type="number", semantic_ref="measure.price"),
    )
    return LogicalQueryPlan(
        plan_id="test:non-physical-grouping:1.0",
        time_scope=("2026-07-03",),
        output_node="n2",
        requested_output_shape=schema,
        nodes=(
            PlanNode(
                node_id="n1", op="Scan", source="products_clean.csv",
                refs=("measure.price",), input_grain="listing_snapshot",
                output_grain="listing_snapshot", expected_schema=schema,
                expected_cardinality="<=3341",
            ),
            PlanNode(
                node_id="n2", op="Aggregate", inputs=("n1",), refs=("measure.price",),
                group_by=(ref,), aggregation="median",
                input_grain="listing_snapshot", output_grain="group",
                expected_schema=schema, expected_cardinality="<=3341",
            ),
        ),
    )


def test_validator_rejects_grouping_by_a_ref_without_a_column():
    # A3: this plan used to pass validation and then raise CompilationError,
    # which left the request without any looked-up rule_id at all.
    verdict = validate_plan(_plan_grouping_by("entity.product_listing"))
    assert not verdict.valid
    assert "non_physical_grouping" in {issue.code for issue in verdict.issues}


def test_validator_still_allows_grouping_by_a_unit_that_has_a_column():
    codes = {issue.code for issue in validate_plan(_plan_grouping_by("entity.shop")).issues}
    assert "non_physical_grouping" not in codes


@pytest.mark.parametrize("question", [
    "Giá trung vị của listing tại Việt Nam ngày 03/07 là bao nhiêu?",
    "Cửa hàng nào có nhiều sản phẩm nhất tại Indonesia?",
])
def test_parser_never_groups_by_a_unit_without_a_column(question):
    # A5: generalises the entity.shop-only ``counted_unit`` patch. Two rules for
    # one concept drift apart; this is the concept stated once.
    parsed = DeterministicSemanticParser().parse(question, "vi", "vn")
    ungroupable = [ref for ref in parsed.grouping if not CATALOG[ref].physical]
    assert ungroupable == []


def test_counting_a_shop_is_expressible():
    # A4: the catalog modelled "count distinct instances" for exactly one entity.
    parsed = DeterministicSemanticParser().parse("Có bao nhiêu shop ở Việt Nam?", "vi", "vn")
    assert "derived.shop_count" in {item.ref for item in parsed.requested_measures}


def test_shop_count_question_answers_ten(runtime):
    response = runtime.run("Có bao nhiêu shop ở Việt Nam?")
    assert response.gate.action == "allow"
    assert 10 in {item.value for item in response.evidence}


def test_median_price_of_listings_does_not_crash(runtime):
    # bgk02: the only two outcomes in the whole 20-question set that escaped as
    # an uncaught exception instead of a decision with a rule_id.
    response = runtime.run("Giá trung vị của listing tại Việt Nam ngày 03/07 là bao nhiêu?")
    assert response.gate.rule_id
