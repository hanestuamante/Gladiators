"""WP-A10 — ràng buộc loại entity khi phân giải.

`AnalyticalRequest.resolved_entities` đã có `entity_type` với đúng năm giá trị,
nhưng chưa ai dùng nó làm RÀNG BUỘC: resolver xếp hạng trên một tập ứng viên
phẳng, không bước nào hỏi *"câu này cần một thực thể thuộc loại nào?"*.

Điểm quan trọng nhất ở đây là A10-R1: lọc hết ứng viên thì KHÔNG quay lại tập
chưa lọc. Quay lại là cách một câu hỏi về kệ shop được trả lời bằng một danh mục
sàn — đúng thứ `INV-SHELF-NOT-PLATFORM-CATEGORY` cấm.
"""
from __future__ import annotations

import pytest

from gladiators.agent.entity_resolution import (
    ENTITY_TYPE_BY_REF,
    expected_entity_types,
)
from gladiators.agent.workflow import AgentRuntime
from gladiators.planner.semantic_parser import DeterministicSemanticParser

PARSER = DeterministicSemanticParser()


def _types(question: str, country: str = "vn") -> tuple[str, ...]:
    return expected_entity_types(PARSER.parse(question, "vi", country))


# --- A10-R2 · chỉ suy từ ref đã bind, không từ văn bản tự do -------------

@pytest.mark.parametrize("question,expected", [
    ("Kệ shop nào nhiều sản phẩm nhất tại VN", ("shelf",)),
    ("Danh mục sàn nào nhiều listing nhất", ("category",)),
    ("Shop nào nhiều listing nhất", ("shop",)),
    ("Brand nào có rating cao nhất tại VN", ("brand",)),
])
def test_type_is_inferred_from_bound_refs(question, expected):
    assert _types(question) == expected


def test_no_type_inferred_leaves_behaviour_unchanged():
    """Không suy được loại nào ⇒ giữ nguyên hành vi hiện tại."""
    assert _types("Giá trung vị tại VN") == ()


def test_every_mapped_ref_exists_in_the_catalog():
    from gladiators.domain.catalog import CATALOG

    for ref in ENTITY_TYPE_BY_REF:
        assert ref in CATALOG, f"{ref} không có trong catalog"


def test_shelf_and_category_never_collapse_into_one_type():
    """Hai hệ phân loại phải suy ra hai loại KHÁC nhau.

    Gộp chúng là bước đầu tiên của việc trả lời câu hỏi về kệ shop bằng một
    danh mục sàn.
    """
    assert _types("Kệ shop nào nhiều sản phẩm nhất tại VN") != _types(
        "Danh mục sàn nào nhiều listing nhất",
    )


# --- verdict phải sống sót qua MỌI nhánh của workflow --------------------

@pytest.mark.parametrize("question", [
    "Kệ shop nào nhiều sản phẩm nhất tại VN",
    "Shop nào nhiều listing nhất tại Indonesia",
])
def test_constraint_reaches_the_trace(tmp_path, question):
    """planning_meta bị gán đè ở nhánh macro và nhánh analytical.

    Một thành phần chạy shadow mà verdict biến mất thì nó không còn được đo.
    """
    response = AgentRuntime(trace_dir=tmp_path).run(question)
    verdict = response.planning.get("entity_type_constraint")
    assert verdict and verdict["expected"], question
    assert verdict["resolver_pool"] == "listing"
