"""ExecutionPlan envelope — ultimate solution §8.2.

The envelope exists because raising ``subplan_count`` to fake multi-part answers
produces plans that validate and cannot run. These tests hold the two invariants
that make the envelope safe: subplans are always atomic, and every part is
computed against one pinned context snapshot.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from gladiators.planner.atoms import make_atom
from gladiators.planner.execution_plan import (
    AtomicExecutionPlan,
    CompositeOutputContract,
    DecomposedExecutionPlan,
    DeferredPredicate,
    ExecutionContextSnapshot,
    ExecutionOutputField,
    IssueParam,
    JoinOnRelationSpec,
    PlannedSubplanSpec,
    PlanningFailure,
    PlanningIssue,
    ScopePartition,
    SectionSpec,
    SideBySideSpec,
    UnionScopeSpec,
    composition_arity,
)
from gladiators.planner.query_ir import LogicalQueryPlan, OutputField, PlanNode
from gladiators.planner.topic_router import TopicRouter

FIELD = ExecutionOutputField(name="price", semantic_ref="measure.price",
                             dtype="number", unit="local_currency",
                             currency_code="VND", aggregatable_across_scope=False)


def snapshot(dataset_version: str = "ds-1") -> ExecutionContextSnapshot:
    return ExecutionContextSnapshot(
        dataset_version=dataset_version, catalog_hash="cat", alias_index_hash="ali",
        relation_hash="rel", invariant_hash="inv", capability_hash="cap",
        topic_hash="top", config_hash="cfg", topic_gate_version="topic-gate.v1",
        decomposition_gate_version="decomp-gate.v1",
    )


def logical_plan(plan_id: str = "p1", subplan_count: int = 1) -> LogicalQueryPlan:
    output = (OutputField(name="price", type="number", semantic_ref="measure.price"),)
    return LogicalQueryPlan(
        plan_id=plan_id, time_scope=("2026-07-03",), output_node="n1",
        requested_output_shape=output, subplan_count=subplan_count,
        nodes=(PlanNode(
            node_id="n1", op="Scan", source="products_clean.csv",
            refs=("measure.price",), input_grain="listing_snapshot",
            output_grain="listing_snapshot", expected_schema=output,
            expected_cardinality="<=3341",
        ),),
    )


def routing():
    return TopicRouter().route("Giá trung bình tại Việt Nam", None)


def subplan(subplan_id: str, *, dataset_version: str = "ds-1",
            subplan_count: int = 1, atom_ids=("mea-1",)) -> PlannedSubplanSpec:
    return PlannedSubplanSpec(
        subplan_id=subplan_id, request=None, covered_atom_ids=tuple(atom_ids),
        subrequest_digest_hash=f"d-{subplan_id}", routing=routing(),
        context_hash=f"c-{subplan_id}", topic_gate_version="topic-gate.v1",
        dataset_version=dataset_version,
        plan=logical_plan(subplan_id, subplan_count), plan_hash=f"h-{subplan_id}",
        output_fields=(FIELD,),
    )


def contract(presentation="sections") -> CompositeOutputContract:
    return CompositeOutputContract(
        presentation=presentation, output_shape_kind="comparison",
        output_grain="country", expected_cardinality="2",
        fields=(FIELD,) if presentation == "single_frame" else (),
    )


def side_by_side(ids=("s1", "s2")) -> SideBySideSpec:
    return SideBySideSpec(
        sections=tuple(
            SectionSpec(section_id=f"sec{i}", title_key=f"t{i}", subplan_id=sid, order=i)
            for i, sid in enumerate(ids)
        ),
        output_contract=contract(),
    )


def decomposed(**overrides) -> DecomposedExecutionPlan:
    base = dict(
        execution_plan_id="ep-1", request_hash="rh", digest_hash="dh",
        capability_id="cap-1", context_snapshot=snapshot(),
        request_atoms=(make_atom("measure", semantic_ref="measure.price"),),
        output_shape_kind="comparison", root_routing=routing(),
        decomposition_proposal_hash="ph",
        subplans=(subplan("s1"), subplan("s2")), composition=side_by_side(),
    )
    base.update(overrides)
    return DecomposedExecutionPlan(**base)


# --- subplans are always atomic -------------------------------------------

def test_a_subplan_may_not_itself_be_decomposed():
    """No nesting: a composition hiding inside another has no validator."""
    with pytest.raises(ValidationError, match="atomic"):
        subplan("s1", subplan_count=2)


def test_atomic_plan_rejects_a_multi_subplan_logical_plan():
    with pytest.raises(ValidationError, match="subplan_count"):
        AtomicExecutionPlan(
            execution_plan_id="ep", request_hash="r", digest_hash="d",
            capability_id="c", context_snapshot=snapshot(), request_atom_ids=("a",),
            output_shape_kind="scalar", output_fields=(FIELD,),
            planning_source="synthesizer", plan=logical_plan(subplan_count=3),
        )


def test_atomic_plan_requires_output_fields():
    with pytest.raises(ValidationError, match="output_fields"):
        AtomicExecutionPlan(
            execution_plan_id="ep", request_hash="r", digest_hash="d",
            capability_id="c", context_snapshot=snapshot(), request_atom_ids=("a",),
            output_shape_kind="scalar", output_fields=(),
            planning_source="synthesizer", plan=logical_plan(),
        )


def test_decomposer_built_plan_must_carry_its_routing_provenance():
    """Without it there is no record of which catalogue slice it could see."""
    with pytest.raises(ValidationError, match="routing"):
        AtomicExecutionPlan(
            execution_plan_id="ep", request_hash="r", digest_hash="d",
            capability_id="c", context_snapshot=snapshot(), request_atom_ids=("a",),
            output_shape_kind="scalar", output_fields=(FIELD,),
            planning_source="decomposer", plan=logical_plan(),
        )


def test_macro_sourced_plan_does_not_need_routing():
    plan = AtomicExecutionPlan(
        execution_plan_id="ep", request_hash="r", digest_hash="d",
        capability_id="c", context_snapshot=snapshot(), request_atom_ids=("a",),
        output_shape_kind="scalar", output_fields=(FIELD,),
        planning_source="macro", plan=logical_plan(),
    )
    assert plan.routing is None


# --- one pinned context ---------------------------------------------------

def test_subplans_must_share_the_pinned_dataset_version():
    """A composed answer assembled across versions is wrong invisibly."""
    with pytest.raises(ValidationError, match="dataset version"):
        decomposed(subplans=(subplan("s1"), subplan("s2", dataset_version="ds-2")))


def test_duplicate_subplan_ids_are_rejected():
    with pytest.raises(ValidationError, match="trùng"):
        decomposed(subplans=(subplan("s1"), subplan("s1")))


def test_composition_may_not_reference_an_absent_subplan():
    with pytest.raises(ValidationError, match="không tồn tại"):
        decomposed(composition=side_by_side(("s1", "s9")))


def test_arity_is_bounded_to_two_through_four():
    with pytest.raises(ValidationError):
        decomposed(subplans=(subplan("s1"),))
    with pytest.raises(ValidationError):
        decomposed(subplans=tuple(subplan(f"s{i}") for i in range(5)))


def test_context_snapshot_seals_its_own_hash():
    assert snapshot().execution_context_hash == snapshot().execution_context_hash
    assert snapshot("ds-1").execution_context_hash != snapshot("ds-2").execution_context_hash


# --- composition contracts ------------------------------------------------

def test_single_frame_output_must_declare_its_fields():
    """A shared schema for sections would have to be invented, and an invented
    schema is a claim about data nobody produced."""
    with pytest.raises(ValidationError, match="single_frame"):
        CompositeOutputContract(
            presentation="single_frame", output_shape_kind="table",
            output_grain="country", expected_cardinality="2", fields=(),
        )


def test_union_scope_partitions_must_be_disjoint():
    """Overlapping partitions double-count silently."""
    with pytest.raises(ValidationError, match="chồng lấn"):
        UnionScopeSpec(
            scope_ref="dim.country", dedupe_policy_id="one_row_per_listing",
            partitions=(
                ScopePartition(subplan_id="s1", scope_values=("vn", "id")),
                ScopePartition(subplan_id="s2", scope_values=("id",)),
            ),
            output_contract=contract(),
        )


def test_post_union_aggregate_is_off_by_default():
    """Aggregating after a scope union is how two markets get averaged into one
    number with no unit."""
    spec = UnionScopeSpec(
        scope_ref="dim.country", dedupe_policy_id="one_row_per_listing",
        partitions=(
            ScopePartition(subplan_id="s1", scope_values=("vn",)),
            ScopePartition(subplan_id="s2", scope_values=("id",)),
        ),
        output_contract=contract(),
    )
    assert spec.allow_post_union_aggregate is False


def test_deferred_predicate_value_count_is_bounded():
    """An unbounded IN list is how a producer's result set becomes a query plan."""
    with pytest.raises(ValidationError):
        DeferredPredicate(
            consumer_node_id="n1", ref="entity.product_listing",
            source_subplan_id="s1", source_field_ref="item_id", max_values=100_000,
        )


def test_composition_arity_counts_distinct_subplans():
    join = JoinOnRelationSpec(
        left_subplan_id="s1", right_subplan_id="s2", relation_id="belongs_to",
        join_key_refs=("entity.shop",), join_type="left",
        null_policy="preserve_left", output_contract=contract("single_frame"),
    )
    assert composition_arity(join) == 2
    assert composition_arity(side_by_side(("s1", "s2", "s3"))) == 3


# --- issues ---------------------------------------------------------------

def test_issue_id_ignores_localized_message():
    """Branching on message text breaks the moment anything is translated."""
    a = PlanningIssue(category="composition", code="UNIT_MISMATCH", message_key="one")
    b = PlanningIssue(category="composition", code="UNIT_MISMATCH", message_key="two")
    assert a.issue_id == b.issue_id


def test_issue_id_reflects_structure():
    a = PlanningIssue(category="composition", code="UNIT_MISMATCH", message_key="k",
                      params=(IssueParam(name="ref", value="measure.price"),))
    b = PlanningIssue(category="composition", code="UNIT_MISMATCH", message_key="k",
                      params=(IssueParam(name="ref", value="measure.rating"),))
    assert a.issue_id != b.issue_id


def test_primary_issue_is_chosen_by_priority_not_arrival_order():
    coverage = PlanningIssue(category="decomposition", code="ATOM_COVERAGE_MISMATCH",
                             message_key="k")
    schema = PlanningIssue(category="composition", code="OUTPUT_SCHEMA_MISMATCH",
                           message_key="k")
    forward = PlanningFailure.from_issues("DECOMPOSITION_INVALID", (schema, coverage))
    reverse = PlanningFailure.from_issues("DECOMPOSITION_INVALID", (coverage, schema))
    assert forward.primary_issue_id == reverse.primary_issue_id == coverage.issue_id


def test_failure_requires_at_least_one_issue():
    with pytest.raises(ValueError):
        PlanningFailure.from_issues("PLAN_INVALID", ())


def test_valid_decomposed_plan_round_trips():
    plan = decomposed()
    assert plan.kind == "decomposed"
    assert len(plan.subplans) == 2
    assert plan.partial_policy == "all_or_nothing"
