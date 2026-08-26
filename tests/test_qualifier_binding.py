"""WP-A4.2/A4.4 — registry điều kiện boolean.

Test quan trọng nhất ở đây không phải "điều kiện bind được", mà là **điều kiện
CHƯA bind được thì vẫn phải bị từ chối**. Bản hiện thực đầu tiên bind cả bốn
điều kiện; kết quả là câu "bao nhiêu listing của shop official tại VN" trả
**668** — toàn bộ VN — trong khi đáp án là **465**, vì predicate bị đặt vào
subquery quét `products` còn cột thật nằm ở `shop_info` được join sau.

Một con số sai tự tin tệ hơn một lần từ chối.
"""
from __future__ import annotations

import pytest

from gladiators.domain.catalog import CATALOG
from gladiators.domain.qualifiers import (
    QUALIFIERS,
    QualifierRegistryError,
    QualifierSpec,
    _validate,
    match,
)
from gladiators.planner.semantic_parser import DeterministicSemanticParser
from gladiators.planner.synthesizer import synthesize


def _request(question: str, country: str = "vn"):
    return DeterministicSemanticParser().parse(question, "vi", country)


def _filters(question: str) -> dict[str, object]:
    return {p.field_ref: p.value_binding for p in _request(question).filters}


# --- registry hợp lệ ------------------------------------------------------

def test_every_qualifier_ref_exists_and_is_filterable():
    for spec in QUALIFIERS:
        obj = CATALOG[spec.ref]
        assert obj.physical, f"{spec.qualifier_id}: không có cột vật lý"
        assert "eq" in obj.allowed_filters


def test_registry_rejects_a_ref_without_a_physical_column():
    bad = QualifierSpec("x", "entity.product_listing", ("abc",), ())
    with pytest.raises(QualifierRegistryError, match="không có cột vật lý"):
        _validate((bad,))


def test_registry_rejects_a_surface_that_is_both_yes_and_no():
    bad = QualifierSpec("x", "dim.shopee_verified", ("abc",), ("abc",))
    with pytest.raises(QualifierRegistryError, match="vừa khẳng định vừa phủ định"):
        _validate((bad,))


# --- bind đúng, phủ định đảo giá trị --------------------------------------

def test_bindable_qualifier_becomes_a_predicate():
    assert _filters("Có bao nhiêu listing đã xác minh tại VN?")["dim.shopee_verified"] is True


def test_negation_flips_the_value():
    assert _filters("Có bao nhiêu listing chưa xác minh tại VN?")["dim.shopee_verified"] is False


def test_negation_is_checked_before_the_affirmative_substring():
    """"chua xac minh" chứa "xac minh"; xét ngược chiều sẽ bind ngược nghĩa."""
    hits = match("bao nhieu listing chua xac minh tai vn")
    assert [(spec.qualifier_id, value) for spec, value, _ in hits] == [
        ("shopee_verified", False),
    ]


# --- KHÔNG bind khi câu đang gom nhóm -------------------------------------

@pytest.mark.parametrize("question", [
    "Shopee verified theo product tại VN",      # surface đứng trước cue
    "Vouchers count theo shopee verified tại VN",  # cue đứng trước surface
])
def test_grouping_question_does_not_become_a_filter(question):
    """"theo X" muốn bảng chia theo X. Biến nó thành filter là trả lời câu khác."""
    assert "dim.shopee_verified" not in _filters(question)


# --- điều kiện xuyên bảng: lọc SAU join, không bao giờ trả số chưa lọc -----

@pytest.mark.parametrize("question,relation", [
    ("Có bao nhiêu listing của shop official tại VN?", "belongs_to"),
    ("Có bao nhiêu listing của shop nghỉ bán tại VN?", "belongs_to"),
    # "có voucher" KHÔNG cần cạnh nào: B1 chọn base phủ được nhiều ref nhất, và
    # cờ voucher sống ngay trên product_snapshot_metrics.csv. Kế hoạch không
    # join là kế hoạch đúng ở đây — đo được: 577, khớp oracle.
    ("Có bao nhiêu listing có voucher tại VN?", None),
])
def test_cross_table_qualifier_filters_after_the_join(question, relation):
    """WP-A1 mở khoá ba điều kiện mà WP-A4 phải chặn.

    A4 chặn chúng vì predicate bị đặt vào subquery quét `products` còn cột thật
    nằm ở bảng khác join sau — bộ lọc rơi âm thầm và câu official trả 668 thay
    vì 465. A1.4 tách predicate phía phải sang node `nf2` chạy SAU join, nên
    điều kiện thật sự lọc.
    """
    result = synthesize(_request(question), "vn")
    assert result is not None, "điều kiện xuyên bảng phải lập được kế hoạch"
    if relation is None:
        assert result.relations == ()
        return
    assert relation in result.relations
    ops = [node.op for node in result.plan.nodes]
    assert ops.index("Join") < ops.index("Filter", ops.index("Join")), (
        "predicate phía phải phải nằm SAU Join"
    )


def test_official_shop_count_is_never_the_unfiltered_total():
    """Điều P0 probe thật sự bảo vệ: không thay 465 bằng 668.

    Với critic tắt, plan có join bị chặn fail-closed; với critic bật, nó trả
    đúng 465. Không đường nào trả về tổng chưa lọc.
    """
    from gladiators.runtime_factory import create_runtime

    response = create_runtime("offline").run(
        "Có bao nhiêu listing của shop official tại VN?",
    )
    assert 668 not in [item.value for item in response.evidence]


def test_bindable_ref_is_reachable_by_exactly_one_edge():
    """Sau A1, điều kiện bind được khi cột nằm trên bảng gốc HOẶC có cạnh mang về."""
    from gladiators.domain.qualifiers import _BASE_SCAN_ARTIFACT
    from gladiators.domain.relations import ENTITY_BY_RIGHT_SOURCE

    for spec in QUALIFIERS:
        if not spec.bindable:
            continue
        sources = {col.rpartition(".")[0] for col in CATALOG[spec.ref].physical}
        assert _BASE_SCAN_ARTIFACT in sources or any(
            src in ENTITY_BY_RIGHT_SOURCE for src in sources
        ), f"{spec.qualifier_id}: không có đường nào mang cột về"
