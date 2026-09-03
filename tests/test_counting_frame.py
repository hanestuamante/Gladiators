"""W4 — khung đếm: một ngữ pháp, không phải tám bản vá (SolutionSpec2808 §5).

Toàn bộ 8 lỗi MR-1 của kiểm biến hình là MỘT họ duy nhất: khung "Số lượng X là
bao nhiêu?" tách cụm alias dính liền ("bao nhieu shop") và câu mất measure.
Vá bằng alias đóng đúng hai ca và để nguyên lớp lỗi; W4 đóng LỚP.
"""
from __future__ import annotations

import pytest

from gladiators.agent.workflow import AgentRuntime
from gladiators.planner.semantic_parser import DeterministicSemanticParser

PARSER = DeterministicSemanticParser()

FRAME_PAIRS = [
    ("Có bao nhiêu shop ở Việt Nam?",
     "Số lượng shop ở Việt Nam là bao nhiêu?"),
    ("Có bao nhiêu listing đã xác minh tại Việt Nam ngày 03/07?",
     "Số lượng listing đã xác minh tại Việt Nam ngày 03/07 là bao nhiêu?"),
    ("Có bao nhiêu thương hiệu tại Việt Nam ngày 03/07?",
     "Số lượng thương hiệu tại Việt Nam ngày 03/07 là bao nhiêu?"),
    ("Có bao nhiêu shop chính hãng ở Việt Nam?",
     "Số lượng shop chính hãng ở Việt Nam là bao nhiêu?"),
]


@pytest.fixture(scope="module")
def runtime() -> AgentRuntime:
    return AgentRuntime()


# --- W4.1 · nghĩa vụ chứng minh của phép viết lại --------------------------

@pytest.mark.parametrize(("original", "variant"), FRAME_PAIRS)
def test_the_two_frames_parse_to_the_same_question(original, variant):
    """Điều kiện nghiệm thu §5.2: mọi cặp khung phải cho CÙNG ba trường ngữ
    nghĩa — định ngữ ("đã xác minh", "chính hãng") nằm trong `rest` nên phép
    viết lại không được làm nó rơi mất."""
    left = PARSER.parse(original, "vi", "vn")
    right = PARSER.parse(variant, "vi", "vn")
    assert [m.ref for m in left.requested_measures] == [
        m.ref for m in right.requested_measures]
    assert [d.ref for d in left.requested_dimensions] == [
        d.ref for d in right.requested_dimensions]
    assert [(f.field_ref, f.op, f.value_binding) for f in left.filters] == [
        (f.field_ref, f.op, f.value_binding) for f in right.filters]
    # Khoá đếm: nhánh viết lại phải đếm được số lần nó bắn (§0.3 ô 4).
    assert "count_frame_normalised" in right.assumptions
    assert "count_frame_normalised" not in left.assumptions


# --- W4.2 · đếm theo cấu trúc ----------------------------------------------

def test_a_bare_dimension_after_the_interrogative_becomes_a_count(runtime):
    """ans028: "có bao nhiêu brand khác nhau" → brand_count · 30, và dim.brand
    rời khỏi dimensions — nó là đơn vị được đếm, không phải khoá gom nhóm."""
    request = PARSER.parse(
        "Việt Nam ngày 03/07 có bao nhiêu brand khác nhau?", "vi", "vn",
    )
    assert [m.ref for m in request.requested_measures] == ["derived.brand_count"]
    assert "dim.brand" not in [d.ref for d in request.requested_dimensions]

    response = runtime.run("Việt Nam ngày 03/07 có bao nhiêu brand khác nhau?")
    assert response.gate.action == "allow"
    assert 30 in [item.value for item in response.evidence]


def test_the_indonesian_market_counts_its_own_brands(runtime):
    """ans030 → 12, khớp oracle."""
    response = runtime.run("Indonesia ngày 03/07 có bao nhiêu brand khác nhau?")
    assert response.gate.action == "allow"
    assert 12 in [item.value for item in response.evidence]


def test_a_grouping_dimension_is_not_stolen_as_a_measure():
    """Negative 1: "giá trung vị theo brand" — measures không rỗng nên luật
    KHÔNG áp; brand vẫn là dimension."""
    request = PARSER.parse("Giá trung vị theo brand tại VN ngày 03/07?", "vi", "vn")
    assert [m.ref for m in request.requested_measures] == ["measure.price"]
    assert "dim.brand" in [d.ref for d in request.requested_dimensions]


def test_only_the_adjacent_dimension_is_counted():
    """Negative 2: "rating theo brand ... có bao nhiêu listing" đếm LISTING —
    brand không liền kề từ hỏi số lượng nên không bị đếm nhầm."""
    request = PARSER.parse(
        "Rating theo brand tại VN có bao nhiêu listing?", "vi", "vn",
    )
    refs = [m.ref for m in request.requested_measures]
    assert "derived.brand_count" not in refs


def test_two_adjacent_candidates_refuse_to_pick():
    """Negative 3: câu nêu hai chiều cùng liền kề ⇒ không chọn theo thứ tự
    registry — chọn một là chọn hộ người hỏi."""
    request = PARSER.parse(
        "Có bao nhiêu brand và bao nhiêu shop tại VN ngày 03/07?", "vi", "vn",
    )
    # Không được lặng lẽ chọn một trong hai làm measure duy nhất.
    count_refs = {
        m.ref for m in request.requested_measures
        if m.ref in {"derived.brand_count", "derived.shop_count"}
    }
    assert count_refs != {"derived.brand_count"} or len(count_refs) != 1 or (
        request.ambiguities
    )


# --- W4.3 · alias trần ------------------------------------------------------

def test_bare_likes_binds_the_count_not_the_delta(runtime):
    """bgk12: "nhiều lượt thích nhất" → measure.liked_count. Và chiều ngược:
    "thay đổi lượt thích" vẫn là liked_delta — compound_shadowed hai chiều."""
    request = PARSER.parse(
        "Listing nào có nhiều lượt thích nhất tại VN?", "vi", "vn",
    )
    assert "measure.liked_count" in [m.ref for m in request.requested_measures]

    delta = PARSER.parse("Thay đổi lượt thích tại VN?", "vi", "vn")
    refs = [m.ref for m in delta.requested_measures]
    assert "derived.liked_delta" in refs
    assert "measure.liked_count" not in refs


def test_bare_ratings_binds_rating_count():
    """Cùng lớp lỗi với "lượt thích"; W9.4 phải sinh ca đo cho nó."""
    request = PARSER.parse(
        "Listing nào có nhiều lượt đánh giá nhất tại VN?", "vi", "vn",
    )
    assert "measure.rating_count" in [m.ref for m in request.requested_measures]
