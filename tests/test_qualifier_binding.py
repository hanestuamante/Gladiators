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


# --- điều kiện CHƯA bind được vẫn phải chặn synthesizer --------------------

@pytest.mark.parametrize("question", [
    "Có bao nhiêu listing của shop official tại VN?",
    "Có bao nhiêu listing của shop nghỉ bán tại VN?",
    "Có bao nhiêu listing có voucher tại VN?",
])
def test_unbindable_qualifier_still_makes_the_synthesizer_decline(question):
    """Ba điều kiện này nằm ở bảng khác, cần join mà grammar đặt sai chỗ.

    Bind chúng làm bộ lọc rơi âm thầm: câu official trả 668 thay vì 465. Guard
    một chiều — chưa bind được thì vẫn từ chối.
    """
    request = _request(question)
    assert synthesize(request, "vn") is None


def test_bindable_flag_matches_the_scan_table():
    from gladiators.domain.qualifiers import _BASE_SCAN_ARTIFACT

    for spec in QUALIFIERS:
        on_base = all(
            col.startswith(f"{_BASE_SCAN_ARTIFACT}.") for col in CATALOG[spec.ref].physical
        )
        assert spec.bindable == on_base, (
            f"{spec.qualifier_id}: bindable={spec.bindable} nhưng cột "
            f"{'nằm trên' if on_base else 'nằm ngoài'} {_BASE_SCAN_ARTIFACT}"
        )
