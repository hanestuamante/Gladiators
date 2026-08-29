"""Invariant dispatch — §E3.

Câu hỏi trung tâm không phải "registry có 11 entry không" mà "một plan vi phạm
rule X có bị chặn bởi ĐÚNG rule X không". Trước §E3, `for_stage()` không có
caller nào và không `validator_id` nào được dereference ở runtime: rule tồn tại
trên giấy, enforcement tồn tại rời rạc trong code, và hai bên đã lệch thật.
"""
from __future__ import annotations

import dataclasses

import pytest

from gladiators.domain.invariant_handlers import (
    INVARIANT_HANDLERS,
    InvariantContext,
    InvariantDispatchError,
    _check_dispatch,
    enforce_invariants,
    hard_violations,
)
from gladiators.domain.invariants import INVARIANTS, hard_invariants
from gladiators.planner.query_ir import (
    LogicalQueryPlan,
    OutputField,
    PlanNode,
    Predicate,
)
from gladiators.planner.validator import validate_plan


# --- build-time resolution ------------------------------------------------

def test_every_spec_resolves_to_a_handler():
    # 12 từ W1.5 (SolutionSpec2808 §2.7): INV-FILTER-LITERAL-IS-DATASET-VALUE.
    assert len(INVARIANTS) == 12
    assert len(INVARIANT_HANDLERS) == 12
    for spec in INVARIANTS.values():
        assert spec.validator_id in INVARIANT_HANDLERS, spec.invariant_id


def test_handler_covers_every_stage_the_spec_declares():
    for spec in INVARIANTS.values():
        handler = INVARIANT_HANDLERS[spec.validator_id]
        assert set(spec.applies_to) <= handler.stages, spec.invariant_id


def test_unresolved_validator_id_fails_the_build():
    spec = INVARIANTS["INV-NO-CAUSAL-CLAIM"]
    broken = {spec.invariant_id: spec.model_copy(update={"validator_id": "khong.co"})}
    with pytest.raises(InvariantDispatchError, match="không resolve"):
        _check_dispatch(broken, INVARIANT_HANDLERS)


def test_handler_not_covering_a_declared_stage_fails_the_build():
    spec = INVARIANTS["INV-NO-CAUSAL-CLAIM"]
    broken = {spec.invariant_id: spec.model_copy(update={"applies_to": ("plan",)})}
    with pytest.raises(InvariantDispatchError, match="không phủ stage"):
        _check_dispatch(broken, INVARIANT_HANDLERS)


def test_empty_handler_version_fails_the_build():
    handler = INVARIANT_HANDLERS["wording.no_causal_claim"]
    broken = dict(INVARIANT_HANDLERS)
    broken["wording.no_causal_claim"] = dataclasses.replace(handler, handler_version="")
    with pytest.raises(InvariantDispatchError, match="handler_version"):
        _check_dispatch(INVARIANTS, broken)


def test_a_handler_no_spec_uses_is_rejected():
    """Handler mồ côi là nửa còn lại của cùng một lỗi: code chạy mà không rule
    nào tuyên bố nó."""
    spec = INVARIANTS["INV-NO-CAUSAL-CLAIM"]
    with pytest.raises(InvariantDispatchError, match="không spec nào dùng"):
        _check_dispatch({spec.invariant_id: spec}, INVARIANT_HANDLERS)


# --- J1: sentinel spec và code không còn lệch -----------------------------

def test_sentinel_spec_now_declares_both_price_refs():
    """§J1 phương án 1: validator đã chặn cả hai từ trước; spec chỉ khai một.
    Handler đọc spec, nên spec thiếu ref = mất một check."""
    spec = INVARIANTS["INV-PRICE-SENTINEL-EXCLUDED"]
    assert set(spec.semantic_refs) == {"measure.price", "measure.price_original"}
    assert spec.version == "1.1"


def test_no_second_copy_of_the_sensitive_ref_set_exists():
    """Enforcement phải đọc spec, không giữ set riêng."""
    source = (
        __import__("pathlib").Path("src/gladiators/planner/validator.py")
        .read_text(encoding="utf-8")
    )
    assert "sensitive_refs" not in source


@pytest.mark.parametrize("ref", ["measure.price", "measure.price_original"])
def test_rank_without_a_sentinel_filter_is_blocked_for_both_refs(ref):
    plan = _plan_ranking_on(ref, exclude_sentinel=False)
    result = validate_plan(plan)
    assert not result.valid
    assert any("INV-PRICE-SENTINEL-EXCLUDED" in issue.message for issue in result.issues)


@pytest.mark.parametrize("ref", ["measure.price", "measure.price_original"])
def test_rank_with_a_sentinel_filter_passes(ref):
    plan = _plan_ranking_on(ref, exclude_sentinel=True)
    violations = enforce_invariants("plan", InvariantContext(stage="plan", plan=plan))
    assert not [v for v in violations if v.invariant_id == "INV-PRICE-SENTINEL-EXCLUDED"]


# --- negative fixture cho từng hard rule chạy ở stage plan ----------------

def test_dedupe_before_aggregate_is_enforced_by_its_own_rule():
    plan = _plan_fanout_aggregate(with_dedupe=False)
    violations = enforce_invariants("plan", InvariantContext(stage="plan", plan=plan))
    ids = {v.invariant_id for v in violations}
    assert "INV-DEDUPE-BEFORE-AGGREGATE" in ids


def test_dedupe_present_clears_the_rule():
    plan = _plan_fanout_aggregate(with_dedupe=True)
    violations = enforce_invariants("plan", InvariantContext(stage="plan", plan=plan))
    assert "INV-DEDUPE-BEFORE-AGGREGATE" not in {v.invariant_id for v in violations}


def test_snapshot_scope_outside_the_governed_dates_is_blocked():
    plan = _plan_ranking_on("measure.price", exclude_sentinel=True)
    plan = plan.model_copy(update={"time_scope": ("2026-07-09",)})
    violations = enforce_invariants("plan", InvariantContext(stage="plan", plan=plan))
    assert "INV-SNAPSHOT-SCOPE" in {v.invariant_id for v in violations}


# --- answer stage ---------------------------------------------------------

@pytest.mark.parametrize("answer,expected", [
    ("Voucher gây ra mức tăng lượt bán.", "INV-NO-CAUSAL-CLAIM"),
    ("Doanh thu của shop này là 5 tỷ.", "INV-PROXY-NOT-VERIFIED-SALES"),
    ("Kết quả vi phạm A22-SCOPE nên bị chặn.", "INV-NO-INTERNAL-VOCABULARY"),
])
def test_answer_stage_rules_each_fire_on_their_own_fixture(answer, expected):
    violations = enforce_invariants(
        "answer", InvariantContext(stage="answer", answer=answer)
    )
    assert expected in {v.invariant_id for v in violations}


def test_a_clean_answer_trips_no_answer_rule():
    violations = enforce_invariants(
        "answer",
        InvariantContext(stage="answer", answer="Giá trung vị tại Việt Nam là 120.000 đồng."),
    )
    assert violations == ()


# --- dispatcher không được nới lỏng bất cứ thứ gì -------------------------

def test_dispatcher_never_downgrades_severity():
    plan = _plan_ranking_on("measure.price", exclude_sentinel=False)
    violations = enforce_invariants("plan", InvariantContext(stage="plan", plan=plan))
    for violation in violations:
        assert violation.severity == INVARIANTS[violation.invariant_id].severity
    assert hard_violations(violations)


def test_hard_rules_stay_hard():
    for invariant_id in hard_invariants():
        assert INVARIANTS[invariant_id].severity == "hard"


def test_violation_carries_the_rule_id_not_a_message_string():
    """§8.2: không ai được branch trên message; message là một bản dịch nữa là
    vỡ mọi caller đã parse nó."""
    plan = _plan_ranking_on("measure.price", exclude_sentinel=False)
    violations = enforce_invariants("plan", InvariantContext(stage="plan", plan=plan))
    assert violations
    for violation in violations:
        assert violation.invariant_id in INVARIANTS
        assert violation.message_key.startswith("invariant.")


def test_stage_filter_only_runs_rules_that_declared_the_stage():
    plan = _plan_ranking_on("measure.price", exclude_sentinel=False)
    violations = enforce_invariants("plan", InvariantContext(stage="plan", plan=plan))
    for violation in violations:
        assert "plan" in INVARIANTS[violation.invariant_id].applies_to


# --- fixtures -------------------------------------------------------------

def _field(ref: str) -> OutputField:
    return OutputField(name="gia", type="number", semantic_ref=ref)


def _plan_ranking_on(ref: str, *, exclude_sentinel: bool) -> LogicalQueryPlan:
    predicates = [Predicate(ref="dim.country", op="eq", parameter="country", value="vn")]
    if exclude_sentinel:
        predicates.append(
            Predicate(ref=ref, op="lt", parameter="sentinel", value=999_999_999)
        )
    shape = (_field(ref),)
    return LogicalQueryPlan(
        plan_id="p-sentinel",
        nodes=(
            PlanNode(
                node_id="n1", op="Scan", source="products_clean.csv",
                input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_cardinality="<=10000", expected_schema=shape,
            ),
            PlanNode(
                node_id="n2", op="Filter", inputs=("n1",), predicates=tuple(predicates),
                input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_cardinality="<=10000", expected_schema=shape,
            ),
            PlanNode(
                node_id="n3", op="Rank", inputs=("n2",), refs=(ref,), rank_by=ref,
                limit=5, descending=True,
                input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_cardinality="<=5", expected_schema=shape,
            ),
        ),
        output_node="n3", requested_output_shape=shape, time_scope=("2026-07-01",),
    )


def _plan_fanout_aggregate(*, with_dedupe: bool) -> LogicalQueryPlan:
    shape = (_field("measure.price"),)
    nodes = [
        PlanNode(
            node_id="n1", op="Scan", source="product_categories_clean.csv",
            input_grain="listing_snapshot", output_grain="listing_snapshot",
            expected_cardinality="<=10000", expected_schema=shape,
        ),
        PlanNode(
            node_id="n2", op="Join", inputs=("n1",), relation="in_shop_category",
            dedupe_policy="one_row_per_listing",
            input_grain="listing_snapshot", output_grain="listing_snapshot_x_shelf",
            expected_cardinality="<=10000", expected_schema=shape,
        ),
    ]
    last = "n2"
    if with_dedupe:
        nodes.append(PlanNode(
            node_id="n3", op="Dedupe", inputs=("n2",),
            dedupe_policy="one_row_per_listing",
            input_grain="listing_snapshot_x_shelf", output_grain="listing_snapshot",
            expected_cardinality="<=10000", expected_schema=shape,
        ))
        last = "n3"
    nodes.append(PlanNode(
        node_id="n9", op="Aggregate", inputs=(last,), refs=("measure.price",),
        aggregation="median", group_by=("dim.country",),
        input_grain="listing_snapshot", output_grain="group",
        expected_cardinality="<=10", expected_schema=shape,
    ))
    return LogicalQueryPlan(
        plan_id="p-fanout", nodes=tuple(nodes), output_node="n9",
        requested_output_shape=shape, time_scope=("2026-07-01",),
    )
