"""Composition executor — ultimate solution §8.6 / §8.7.

Each operator gets the test for the wrong number it would otherwise produce
quietly: a cross-market average with no unit, a fanned-out join whose total
looks reasonable, a consumer run twice by a retry, a partial frame escaping as
if it were whole.
"""
from __future__ import annotations

import pandas as pd
import pytest

from gladiators.planner.composition import (
    AtomicExecutionResult,
    CompositionError,
    compose,
    extract_deferred_keys,
    materialization_key,
)
from gladiators.planner.execution_plan import (
    CompositeOutputContract,
    DeferredPredicate,
    ExecutionOutputField,
    FilterThenMeasureSpec,
    JoinOnRelationSpec,
    ScopePartition,
    UnionScopeSpec,
)
from tests.test_execution_plan import decomposed, side_by_side, subplan

VND = ExecutionOutputField(name="price", semantic_ref="measure.price", dtype="number",
                           unit="local_currency", currency_code="VND",
                           aggregatable_across_scope=False)
IDR = ExecutionOutputField(name="price", semantic_ref="measure.price", dtype="number",
                           unit="local_currency", currency_code="IDR",
                           aggregatable_across_scope=False)
SHOP = ExecutionOutputField(name="shop_id", semantic_ref="entity.shop", dtype="string",
                            unit="dimension")
COUNT = ExecutionOutputField(name="n", semantic_ref="derived.product_count",
                             dtype="integer", unit="count")


def result(subplan_id, *, rows=2, schema=(VND,), grain="listing_snapshot",
           dataset_version="ds-1", failed=False, frame=None, keys=("item_id",)):
    return AtomicExecutionResult(
        subplan_id=subplan_id,
        frame=pd.DataFrame({"price": [1, 2][:rows]}) if frame is None else frame,
        schema=schema, grain=grain, row_count=rows,
        plan_hash=f"h-{subplan_id}", dataset_version=dataset_version,
        stable_row_key_fields=keys, failed=failed,
    )


def sections_contract():
    return CompositeOutputContract(
        presentation="sections", output_shape_kind="comparison",
        output_grain="country", expected_cardinality="2",
    )


def frame_contract(fields=(VND,)):
    return CompositeOutputContract(
        presentation="single_frame", output_shape_kind="table",
        output_grain="country", expected_cardinality="<=100", fields=fields,
    )


def plan_with(composition, **overrides):
    base = dict(
        subplans=(subplan("s1"), subplan("s2")), composition=composition,
    )
    base.update(overrides)
    return decomposed(**base)


# --- side_by_side: presents, never computes -------------------------------

def test_side_by_side_produces_sections_and_no_frame():
    """Two results shown together are two results. The moment the composer
    relates them it is answering a question nobody asked."""
    plan = plan_with(side_by_side(("s1", "s2")))
    composed = compose(plan, (result("s1"), result("s2")))
    assert composed.presentation == "sections"
    assert composed.composed_frame is None
    assert composed.row_count == 4


def test_side_by_side_namespaces_stable_keys_by_section():
    """Without namespacing, identical row keys in two sections read as one row."""
    plan = plan_with(side_by_side(("s1", "s2")))
    composed = compose(plan, (result("s1"), result("s2")))
    assert all(":" in key for key in composed.stable_row_key_fields)
    assert len(set(composed.stable_row_key_fields)) == 2


def test_side_by_side_tolerates_different_grain_and_unit():
    plan = plan_with(side_by_side(("s1", "s2")))
    composed = compose(plan, (result("s1", schema=(VND,)),
                              result("s2", schema=(COUNT,), grain="country")))
    assert composed.row_count == 4


# --- all_or_nothing -------------------------------------------------------

def test_a_failed_subplan_fails_the_whole_request():
    """A partial answer that does not announce itself is a wrong answer."""
    plan = plan_with(side_by_side(("s1", "s2")))
    with pytest.raises(CompositionError) as excinfo:
        compose(plan, (result("s1"), result("s2", failed=True)))
    assert excinfo.value.code == "COMPOSITION_INVALID"


def test_no_successful_frame_escapes_when_a_sibling_fails():
    plan = plan_with(side_by_side(("s1", "s2")))
    with pytest.raises(CompositionError):
        compose(plan, (result("s1", rows=2), result("s2", failed=True)))


def test_dataset_version_drift_between_subplans_is_terminal():
    plan = plan_with(side_by_side(("s1", "s2")))
    with pytest.raises(CompositionError) as excinfo:
        compose(plan, (result("s1"), result("s2", dataset_version="ds-9")))
    assert excinfo.value.code == "DATASET_VERSION_MISMATCH"


# --- union_scope ----------------------------------------------------------

def union(partitions=(("s1", ("vn",)), ("s2", ("id",))), **kwargs):
    base = dict(
        scope_ref="dim.country", dedupe_policy_id="one_row_per_listing",
        partitions=tuple(ScopePartition(subplan_id=i, scope_values=v) for i, v in partitions),
        output_contract=frame_contract(),
    )
    base.update(kwargs)
    return UnionScopeSpec(**base)


def test_union_requires_identical_schema():
    """Differing schemas would silently drop or null a column."""
    plan = plan_with(union())
    with pytest.raises(CompositionError) as excinfo:
        compose(plan, (result("s1", schema=(VND,)), result("s2", schema=(COUNT,))),
                concat=lambda frames: pd.concat(frames))
    assert excinfo.value.code == "OUTPUT_SCHEMA_MISMATCH"


def test_cross_market_money_may_be_stacked_for_presentation():
    """VND and IDR have no exchange rate here, so stacking is allowed and
    aggregating is not."""
    plan = plan_with(union())
    composed = compose(
        plan, (result("s1", schema=(VND,)), result("s2", schema=(VND,))),
        concat=lambda frames: pd.concat(frames),
    )
    assert composed.row_count == 4
    assert plan.composition.allow_post_union_aggregate is False


def test_union_currency_fields_are_not_aggregatable_across_scope():
    assert VND.aggregatable_across_scope is False
    assert IDR.aggregatable_across_scope is False


# --- join_on_relation -----------------------------------------------------

def join(**kwargs):
    base = dict(
        left_subplan_id="s1", right_subplan_id="s2", relation_id="belongs_to",
        join_key_refs=("entity.shop",), join_type="left",
        null_policy="preserve_left", output_contract=frame_contract((SHOP,)),
    )
    base.update(kwargs)
    return JoinOnRelationSpec(**base)


def test_join_requires_the_key_in_both_output_schemas():
    plan = plan_with(join())
    with pytest.raises(CompositionError) as excinfo:
        compose(plan, (result("s1", schema=(VND,)), result("s2", schema=(VND,))),
                merge=lambda left, right, spec: left)
    assert excinfo.value.code == "OUTPUT_SCHEMA_MISMATCH"


def test_same_field_name_with_different_semantics_is_a_silent_overwrite():
    other = ExecutionOutputField(name="price", semantic_ref="measure.shop_rating",
                                 dtype="number", unit="score")
    plan = plan_with(join())
    with pytest.raises(CompositionError, match="semantic ref"):
        compose(plan, (result("s1", schema=(VND, SHOP)), result("s2", schema=(other, SHOP))),
                merge=lambda left, right, spec: left)


def test_join_succeeds_when_the_key_is_present_on_both_sides():
    plan = plan_with(join())
    composed = compose(
        plan, (result("s1", schema=(SHOP,)), result("s2", schema=(SHOP,))),
        merge=lambda left, right, spec: pd.DataFrame({"shop_id": ["a", "b"]}),
    )
    assert composed.row_count == 2


# --- filter_then_measure --------------------------------------------------

def filter_then_measure(**kwargs):
    base = dict(
        producer_subplan_id="s1", consumer_subplan_id="s2",
        deferred_predicate=DeferredPredicate(
            consumer_node_id="n1", ref="entity.product_listing",
            source_subplan_id="s1", source_field_ref="item_id",
        ),
        output_contract=frame_contract((SHOP,)),
    )
    base.update(kwargs)
    return FilterThenMeasureSpec(**base)


def test_empty_producer_returns_an_empty_answer_not_an_unfiltered_one():
    """Running the consumer without its filter answers a different question."""
    plan = plan_with(filter_then_measure())
    composed = compose(plan, (
        result("s1", rows=0, frame=pd.DataFrame({"item_id": []})),
        result("s2", rows=999),
    ))
    assert composed.row_count == 0
    assert composed.composed_frame is None
    # "no rows matched" is an answer; "the frame never arrived" is a fault.
    # Both have composed_frame=None, so the difference has to be stated.
    assert composed.empty_reason == "empty_producer_set"


def test_a_missing_frame_is_still_a_fault_when_nothing_declared_it_empty():
    plan = plan_with(union())
    with pytest.raises(CompositionError, match="single_frame"):
        compose(plan, (result("s1"), result("s2")), concat=None)


def test_deferred_keys_come_from_the_execution_result():
    spec = filter_then_measure()
    producer = result("s1", frame=pd.DataFrame({"item_id": ["a", "b", "a"]}), rows=3)
    assert extract_deferred_keys(producer, spec) == ("a", "b")


def test_deferred_key_set_is_capped():
    """An unbounded IN list turns a result set into a query plan."""
    spec = filter_then_measure()
    producer = result("s1", frame=pd.DataFrame({"item_id": list(range(600))}), rows=600)
    with pytest.raises(CompositionError) as excinfo:
        extract_deferred_keys(producer, spec)
    assert excinfo.value.code == "CARDINALITY_VIOLATION"


def test_materialization_is_idempotent_on_keys_and_consumer_plan():
    """A retry that reruns a measuring plan doubles the answer."""
    assert materialization_key(("a", "b"), "h1") == materialization_key(("b", "a"), "h1")
    assert materialization_key(("a", "b"), "h1") != materialization_key(("a", "b"), "h2")
    assert materialization_key(("a",), "h1") != materialization_key(("a", "b"), "h1")


# --- presentation contract ------------------------------------------------

def test_sections_may_not_carry_a_composed_frame():
    """A single frame under "sections" invites reading it as one comparable table."""
    plan = plan_with(union(output_contract=sections_contract()))
    with pytest.raises(CompositionError, match="sections"):
        compose(plan, (result("s1"), result("s2")),
                concat=lambda frames: pd.concat(frames))


def test_single_frame_requires_a_frame():
    plan = plan_with(side_by_side(("s1", "s2")))
    object.__setattr__(plan.composition, "output_contract", frame_contract())
    with pytest.raises(CompositionError, match="single_frame"):
        compose(plan, (result("s1"), result("s2")))


def test_composition_records_lineage_for_every_subplan():
    plan = plan_with(side_by_side(("s1", "s2")))
    composed = compose(plan, (result("s1"), result("s2")))
    assert {entry.subplan_id for entry in composed.lineage} == {"s1", "s2"}
