"""Vòng P — dò tồn tại giá trị chiều (Spec2308 §A5.1).

Bản song sinh của ``A-ENTITY-NOT-FOUND`` cho **giá trị chiều**. Điều nó phải làm
là chặn **sớm**: hỏi về một thương hiệu không có trong dữ liệu mà đi hết đường
lập kế hoạch rồi mới hỏng sẽ trả về một lý do nói về *kế hoạch*, trong khi vấn đề
thật là *dữ liệu không có cái tên đó*.
"""
from __future__ import annotations

import pytest

from gladiators.agent.workflow import AgentRuntime
from gladiators.agent.value_probe import (
    index_is_available,
    named_but_absent,
    bind_values,
)

pytestmark = pytest.mark.skipif(
    not index_is_available(),
    reason="artifacts/value_index.json chưa dựng (scripts/build_value_index.py)",
)


@pytest.fixture(scope="module")
def runtime() -> AgentRuntime:
    return AgentRuntime()


def test_a_named_brand_that_does_not_exist_is_refused_before_planning(runtime):
    response = runtime.run("Rating theo brand Khongtontai tại VN")
    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A-VALUE-NOT-FOUND"
    # "Chặn sớm" phải kiểm được bằng hành vi, không bằng lời: không plan nào
    # được lập, nên không có tool call phân tích nào chạy.
    assert not response.evidence
    assert response.planning.get("mode") != "llm_semantic_plan"


def test_a_brand_that_exists_still_answers(runtime):
    """Vòng P không được biến thành một nguồn từ chối oan mới."""
    response = runtime.run("Rating theo brand Nestlé tại VN")
    assert response.gate.action == "allow"


def test_naming_the_dimension_without_a_value_is_a_grouping_not_a_filter(runtime):
    """§A4.4: "theo brand" là gom nhóm. Đọc thành lọc là trả lời câu khác."""
    response = runtime.run("Rating theo brand tại VN")
    assert response.gate.action == "allow"


def test_a_lowercase_description_is_not_read_as_a_proper_name():
    """"brand không tồn tại" là một MÔ TẢ, không phải một tên riêng.

    Không có điều kiện viết hoa, heuristic đọc "không" thành tên một thương hiệu
    và cướp mất chẩn đoán đúng của ba case empty-result.
    """
    assert named_but_absent(
        "rating theo brand khong ton tai tai vn", "vn",
        frozenset({"dim.brand"}), raw_question="Rating theo brand không tồn tại tại VN",
    ) == ()


def test_a_capitalised_unknown_name_is_flagged():
    absent = named_but_absent(
        "rating theo brand khongtontai tai vn", "vn",
        frozenset({"dim.brand"}), raw_question="Rating theo brand Khongtontai tại VN",
    )
    assert absent and absent[0][0] == "dim.brand"


def test_value_binding_requires_the_dimension_to_be_named():
    """A4-R4 + §A4.4: không nêu tên chiều thì không bind giá trị cho chiều đó.

    Không có điều kiện này, "giá TRUNG vị" khớp một danh mục tên "trung" và câu
    hỏi bị lọc theo một chiều người dùng chưa bao giờ nhắc tới.
    """
    assert bind_values("gia trung vi tai vn", "vn", frozenset()) == ()
