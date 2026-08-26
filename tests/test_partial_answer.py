"""Trả lời kèm giới hạn theo từng phần — Spec2308 §WP-A13.

Ranh giới quan trọng nhất ở đây là **A13-R1**: phần bị từ chối vì vượt NĂNG LỰC
dataset giữ nguyên ``A22-ALIGN-SUBREQUEST`` (mã đó bị khoá bởi ``p0_probes`` và
``dr2607``). Chỉ phần bị từ chối vì lý do KHÁC mới đi mã mới ``A23-PARTIAL``.
"""
from __future__ import annotations

import pytest

from gladiators.agent.parser import substantive_clauses
from gladiators.agent.workflow import AgentRuntime

MIXED = (
    "Có bao nhiêu listing tại Việt Nam ngày 03/07, "
    "và rating theo brand Khongtontai tại VN là bao nhiêu?"
)
CAPABILITY = (
    "Có bao nhiêu listing tại Việt Nam ngày 03/07 "
    "và lợi nhuận ròng của từng shop là bao nhiêu?"
)


@pytest.fixture(scope="module")
def runtime() -> AgentRuntime:
    return AgentRuntime()


def test_clause_split_keeps_the_original_wording():
    """Chuẩn hoá bỏ dấu và bỏ viết hoa — mà viết hoa là tín hiệu vòng P dùng để
    phân biệt một TÊN RIÊNG với một từ mô tả."""
    clauses = substantive_clauses(MIXED)
    assert len(clauses) == 2
    assert "Khongtontai" in clauses[1]


def test_a_partly_answerable_question_answers_the_part_it_can(runtime):
    response = runtime.run(MIXED)
    assert response.gate.action == "allow"
    assert response.gate.rule_id == "A23-PARTIAL"
    assert response.evidence
    # A13-R2: mọi evidence trong nhánh này mang sub_id.
    assert all(item.attrs.get("sub_id") for item in response.evidence)
    assert response.verification["passed"] is True


def test_the_answer_states_which_part_it_answered(runtime):
    """A13-R3. Trả một phần mà không nói rõ là phần nào còn nguy hiểm hơn từ chối
    cả câu: người đọc sẽ gán con số cho toàn bộ câu hỏi của họ."""
    answer = runtime.run(MIXED).answer
    assert "Số ở trên chỉ nói về phần đã trả lời." in answer
    assert "Phần chưa trả lời được" in answer
    # Số phần viết BẰNG CHỮ, không bằng chữ số (bẫy CLAUDE.md §3.1).
    assert "gồm hai phần" in answer


def test_each_part_gets_its_own_verdict_in_the_trace(runtime):
    subrequests = runtime.run(MIXED).planning["subrequests"]
    assert [item["answered"] for item in subrequests] == [True, False]
    assert subrequests[1]["rule_id"] == "A-VALUE-NOT-FOUND"


def test_a_capability_gap_keeps_the_locked_code(runtime):
    """A13-R1: không đổi tên, không đổi ngữ nghĩa mã cũ. Đây là ràng buộc cứng."""
    response = runtime.run(CAPABILITY)
    assert response.gate.rule_id != "A23-PARTIAL"


def test_a_single_clause_question_is_untouched(runtime):
    response = runtime.run("Có bao nhiêu listing tại Việt Nam ngày 03/07?")
    assert response.gate.rule_id == "A-ALLOW"
    assert "subrequests" not in response.planning
