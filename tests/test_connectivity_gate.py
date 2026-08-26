"""WP-A2 — kiểm kết nối ref ở gate.

Câu hỏi có ref không nối được hiện rơi vào `A19-CAT`/`A19-PLAN`: đúng là từ chối,
nhưng lý do mô tả sai bản chất, nên người dùng diễn đạt lại rồi nhận đúng lời từ
chối đó.

Mặc định SHADOW. Test này khoá cả hai chiều: shadow không đổi quyết định, và khi
bật thì issue thắng đúng theo luật fixability.
"""
from __future__ import annotations

import pytest

from gladiators.contracts import GateIssue, IssueDetail
from gladiators.agent.gate import select_issue
from gladiators.planner.feasibility import connectivity_blockers
from gladiators.planner.semantic_parser import DeterministicSemanticParser

PARSER = DeterministicSemanticParser()


def _request(question: str, country: str = "vn"):
    return PARSER.parse(question, "vi", country)


# --- A2-R4 · chỉ bắn khi find_path thật sự trả None ------------------------

@pytest.mark.parametrize("question", [
    "Giá trung vị tại VN",
    "Shop rating cao nhất tại VN",
    "Kệ shop nào nhiều sản phẩm nhất tại VN",
    "Có bao nhiêu listing có voucher tại VN",
])
def test_refs_on_the_spine_have_no_blocker(question):
    assert connectivity_blockers(_request(question)) == ()


def test_transition_metric_artifact_has_no_entity_mapping():
    """`product_transition_metrics.csv` không được quan hệ nào bind.

    Đây là khoảng trống THẬT: 10 ref delta sống ở đó và không cạnh nào mang
    chúng về, nên plan luôn hỏng ở compiler. Blocker nêu đúng điều đó.
    """
    blockers = connectivity_blockers(_request("Thay đổi giá trung vị tại VN là bao nhiêu?"))
    assert "unmapped_artifact:product_transition_metrics.csv" in blockers


# --- A2-R3 · reason không chứa chữ số -------------------------------------

def test_blocker_codes_carry_no_digits_for_the_user():
    """Message abstain mang chữ số bị verifier chấm là số bịa (§1.2.1).

    Hàm này chỉ trả mã ngắn; caller diễn đạt thành câu. Khoá lại để không ai
    nhét con số vào đây sau này.
    """
    blockers = connectivity_blockers(_request("Thay đổi giá trung vị tại VN là bao nhiêu?"))
    for item in blockers:
        assert not any(char.isdigit() for char in item.split(":", 1)[0])


# --- fixability: blocker này không khắc phục được -------------------------

def test_disconnected_issue_beats_a_fixable_one():
    """Không thông tin nào người dùng thêm vào sẽ tạo ra một quan hệ."""
    def issue(rule_id: str, priority: int, fixable: bool) -> GateIssue:
        return GateIssue(
            rule_id=rule_id, phase=3, priority=priority, action="abstain", reason="",
            detail=IssueDetail(category="fanout", code="refs_disconnected"),
            fixable=fixable,
        )

    pool = [issue("A-CROSS-CURRENCY-SCOPE", 1, True), issue("A-REFS-DISCONNECTED", 9, False)]
    assert select_issue(pool).rule_id == "A-REFS-DISCONNECTED"


# --- A2-R1 · mặc định OFF, shadow không đổi quyết định --------------------

def test_shadow_is_the_default(monkeypatch, tmp_path):
    from gladiators.agent.workflow import AgentRuntime

    monkeypatch.delenv("GLADIATORS_ENABLE_CONNECTIVITY_GATE", raising=False)
    response = AgentRuntime(trace_dir=tmp_path).run(
        "Thay đổi giá trung vị tại VN là bao nhiêu?",
    )
    verdict = response.planning.get("connectivity") or {}
    assert verdict.get("shadow") is True
    assert verdict.get("blockers"), "shadow vẫn phải ĐO, không chỉ tắt"
    # Quyết định vẫn là của nhánh cũ, không phải của phép kiểm mới.
    assert response.gate.rule_id != "A-REFS-DISCONNECTED"
