"""W11 — predicate làm measure: đếm theo điều kiện và tỷ lệ (SolutionSpec2808 §12).

Hai ca W11 gỡ (bgk05, bgk11) KHÔNG nằm trong 18 ca từ chối oan của bộ 44 câu —
chúng lộ ra khi chạy BGK-20, và đó là toàn bộ lý do W9.4 (bộ đề độc lập về quy
trình) tồn tại. Mọi ca hành vi chạy qua runtime (§0.3 mục 3).
"""
from __future__ import annotations

import pytest

from gladiators.agent.workflow import AgentRuntime
from gladiators.domain.predicate_ops import (
    EXECUTABLE_OPS,
    canonicalize_predicate_op,
)


@pytest.fixture(scope="module")
def runtime() -> AgentRuntime:
    return AgentRuntime()


# --- W11.1a · một chuẩn operator -------------------------------------------

def test_legacy_ops_canonicalize_and_unknown_ops_explode():
    assert canonicalize_predicate_op("le") == "lte"
    assert canonicalize_predicate_op("ge") == "gte"
    assert canonicalize_predicate_op("gt") == "gt"
    for bad in ("between", "isnull", "regex", ""):
        with pytest.raises(ValueError):
            canonicalize_predicate_op(bad)


def test_the_three_dialects_are_one_type():
    """AnalyticalPredicate, IR Predicate và MetricConstraint cùng một chuẩn —
    hai danh sách là hai chỗ để chúng lệch nhau."""
    from gladiators.domain.metrics import ConstraintOp
    from gladiators.planner.query_ir import PredicateOp
    from gladiators.planner.semantic_parser import AnalyticalPredicate

    assert PredicateOp is ConstraintOp
    model = AnalyticalPredicate(field_ref="measure.price", op="ge", value_binding=1)
    assert model.op == "gte"  # legacy chỉ sống ở biên, không sống trong model


def test_the_compiler_dispatches_every_executable_op():
    """Exhaustiveness: thêm operator vào type mà quên compiler branch phải đỏ
    Ở ĐÂY, không phải trong một câu SQL chạy sai trong im lặng."""
    from gladiators.planner import compiler
    from gladiators.planner.query_ir import Predicate

    for op in sorted(EXECUTABLE_OPS):
        params: list = []
        expression = compiler._predicate_expression(
            Predicate(ref="measure.price", op=op, parameter="p", value=1),
            None, params,
        )
        assert expression is not None, op


# --- W11.1b · điều kiện trên measure thành predicate -----------------------

def test_a_condition_on_a_measure_becomes_a_filter(runtime):
    """bgk05: "bao nhiêu listing giảm giá TRÊN 50%" → allow · 8.

    Oracle pandas: ``(vn.discount_percent_num > 50).sum() == 8``. Trước W11
    parser đọc thành HAI measure và synthesizer từ chối vì đúng lý do sai.
    """
    response = runtime.run("Có bao nhiêu listing giảm giá trên 50% tại VN ngày 03/07?")
    assert response.gate.action == "allow"
    assert 8 in [item.value for item in response.evidence]


def test_a_bare_number_next_to_a_currency_measure_is_not_a_filter(runtime):
    """Điều kiện 4: "trên 50" trần cạnh một measure tiền tệ là một câu hỏi KHÁC
    (50 gì?) — guard một chiều thì bỏ qua đúng hơn đoán."""
    from gladiators.planner.semantic_parser import DeterministicSemanticParser

    request = DeterministicSemanticParser().parse(
        "Có bao nhiêu listing có giá trên 50 tại VN ngày 03/07?", "vi", "vn",
    )
    assert not any(
        item.field_ref == "measure.price" and item.op == "gt"
        for item in request.filters
    )


def test_a_bare_measure_is_never_turned_into_a_null_filter(runtime):
    """Điều kiện 2: "giảm giá" không kèm số không được thành bộ lọc so sánh."""
    from gladiators.planner.semantic_parser import DeterministicSemanticParser

    request = DeterministicSemanticParser().parse(
        "Có bao nhiêu listing giảm giá tại VN ngày 03/07?", "vi", "vn",
    )
    refs = [item.ref for item in request.requested_measures]
    assert "measure.discount_percent" in refs  # vẫn là measure, không phải filter


# --- W11.2 · tỷ lệ là một metric, không phải một cách diễn đạt -------------

def test_a_declared_share_answers_with_full_lineage(runtime):
    """bgk11: 96.26% kèm tử số 643 và mẫu số 668, ba evidence, lineage đủ."""
    response = runtime.run(
        "Tỷ lệ listing có giảm giá tại VN ngày 03/07 là bao nhiêu phần trăm?",
    )
    assert response.gate.action == "allow"
    by_metric = {item.metric: item for item in response.evidence}
    assert by_metric["discounted_listing_count"].value == 643
    assert by_metric["product_count"].value == 668
    rate = by_metric["discounted_listing_rate"]
    assert abs(rate.value - 100 * 643 / 668) < 1e-9
    assert rate.attrs["derivation_op"] == "share"
    assert rate.attrs["scale"] == 100
    assert rate.parent_evidence_ids == (
        by_metric["discounted_listing_count"].evidence_id,
        by_metric["product_count"].evidence_id,
    )
    assert response.verification["passed"] is True


def test_a_bare_ratio_word_is_clarified_not_guessed(runtime):
    """"Tỷ lệ" trần không nói mẫu số là gì — không đoán."""
    response = runtime.run("Tỷ lệ tại VN là bao nhiêu?")
    assert response.gate.action != "allow"


def test_the_median_discount_is_not_hijacked_by_the_share_metric(runtime):
    """Không có "tỷ lệ" trong câu ⇒ vẫn là median discount, W11 không cướp."""
    response = runtime.run("Giảm giá trung vị tại VN ngày 03/07 là bao nhiêu?")
    assert response.gate.action == "allow"
    assert 20.0 in [item.value for item in response.evidence]


def test_share_arithmetic_is_a_consistency_invariant():
    """Một tỷ lệ lệch tử/mẫu của chính nó phải bị A26 bắt — kiểm trên giá trị
    CHƯA làm tròn."""
    from gladiators.agent.consistency import check_evidence_arithmetic
    from gladiators.contracts import Evidence, SourceLocator

    def item(metric, value, **extra):
        return Evidence(
            evidence_id=f"ev:{metric}:{value}", metric=metric, value=value,
            unit="listings", source_tier="btc_dataset",
            source_locator=SourceLocator(kind="internal", value="test"),
            dataset_version="test", **extra,
        )

    numerator = item("discounted_listing_count", 643)
    denominator = item("product_count", 668)
    broken_rate = item(
        "discounted_listing_rate", 50.0,
        attrs={"derivation_op": "share", "scale": 100},
        parent_evidence_ids=(numerator.evidence_id, denominator.evidence_id),
    )
    issues = check_evidence_arithmetic([numerator, denominator, broken_rate])
    assert any(issue.code == "share_arithmetic_mismatch" for issue in issues)

    over_numerator = item("discounted_listing_count", 700)
    over_rate = item(
        "discounted_listing_rate", 100 * 700 / 668,
        attrs={"derivation_op": "share", "scale": 100},
        parent_evidence_ids=(over_numerator.evidence_id, denominator.evidence_id),
    )
    issues = check_evidence_arithmetic([over_numerator, denominator, over_rate])
    # 700 > 668: tử vượt mẫu là một phân hoạch hỏng, bất kể phép chia đúng.
    assert any(issue.code == "share_partition_broken" for issue in issues)


def test_a_plan_cannot_swap_the_declared_denominator():
    """§12.3.1: validator mở closure từ ShareDefinition — plan tự thay tử/mẫu
    trong schema phải bị từ chối."""
    from gladiators.planner.semantic_parser import DeterministicSemanticParser
    from gladiators.planner.synthesizer import synthesize
    from gladiators.planner.validator import validate_plan

    request = DeterministicSemanticParser().parse(
        "Tỷ lệ listing có giảm giá tại VN ngày 03/07 là bao nhiêu phần trăm?",
        "vi", "vn",
    )
    plan = synthesize(request, "vn").plan
    assert validate_plan(plan).valid
    node = next(n for n in plan.nodes if n.op == "Aggregate")
    swapped_schema = tuple(reversed(node.expected_schema))
    tampered = plan.model_copy(update={"nodes": tuple(
        n.model_copy(update={"expected_schema": swapped_schema})
        if n.node_id == node.node_id else n
        for n in plan.nodes
    )})
    assert not validate_plan(tampered).valid


def test_a_zero_denominator_never_renders_as_zero_percent():
    """Chia cho 0 thành NULL trong SQL — không bao giờ thành 0 phần trăm."""
    from gladiators.planner.compiler import compile_plan
    from gladiators.planner.semantic_parser import DeterministicSemanticParser
    from gladiators.planner.synthesizer import synthesize

    request = DeterministicSemanticParser().parse(
        "Tỷ lệ listing có giảm giá tại VN ngày 03/07 là bao nhiêu phần trăm?",
        "vi", "vn",
    )
    sql = compile_plan(synthesize(request, "vn").plan).sql
    assert "WHEN product_count = 0 THEN NULL" in sql
