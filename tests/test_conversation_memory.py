"""Bộ nhớ hội thoại ngắn hạn — Spec2308 §WP-A3.

Điều nguy hiểm nhất một bộ nhớ có thể làm không phải là quên, mà là **nhớ sai
một cách vô hình**. Ba luật của WP này đều nhắm vào đó, và các test dưới đây
kiểm từng luật bằng hành vi chứ không bằng cấu trúc.
"""
from __future__ import annotations

import pytest

from gladiators.agent.conversation import (
    ConversationState,
    ConversationStore,
    Inheritance,
    MAX_TURN_AGE,
    apply_to_request,
    update_from_response,
)
from gladiators.agent.workflow import AgentRuntime

SCOPED = "Có bao nhiêu shop ở Việt Nam?"
UNSCOPED = "Có bao nhiêu listing?"


@pytest.fixture
def runtime() -> AgentRuntime:
    return AgentRuntime()


def test_a_confirmed_country_survives_into_the_next_turn(runtime):
    """Câu hỏi thiếu thị trường ra clarify khi hỏi một mình; có ngữ cảnh thì trả
    lời được. Đây là chính mục tiêu của WP: biến ngõ cụt thành một bước có ích."""
    assert runtime.run(UNSCOPED).gate.action == "clarify"

    runtime.run(SCOPED, session_id="t1")
    second = runtime.run(UNSCOPED, session_id="t1")
    assert second.gate.action == "allow"
    assert second.evidence
    assert "country" in second.planning["conversation"]["inherited"]


def test_memory_never_bypasses_the_gate(runtime):
    """Luật 3. Bộ nhớ chỉ ĐIỀN Ô, tuyệt đối không CẤP PHÉP."""
    runtime.run(SCOPED, session_id="t2")
    second = runtime.run(UNSCOPED, session_id="t2")
    assert second.gate.evaluated_phases, "lượt hai vẫn phải đi qua gate"


def test_inheritance_is_visible_in_the_response(runtime):
    """Luật 2. Bộ nhớ vô hình là bộ nhớ không kiểm được — UI phải dựng được chip
    "đang dùng: thị trường VN" kèm nút bỏ từ đúng khoá này."""
    runtime.run(SCOPED, session_id="t3")
    conversation = runtime.run(UNSCOPED, session_id="t3").planning["conversation"]
    assert conversation["session_id"] == "t3"
    assert conversation["turn"] == 2
    assert conversation["inherited"]


def test_a_reset_clears_the_context(runtime):
    runtime.run(SCOPED, session_id="t4")
    assert runtime.conversations.reset("t4") is True
    assert runtime.run(UNSCOPED, session_id="t4").gate.action == "clarify"


def test_no_session_id_leaves_behaviour_untouched(runtime):
    """A3-R3. Đây là điều kiện để bảy suite cũ không đổi, và nó phải đúng theo
    CẤU TRÚC: không có session thì không có state, nên không nhánh nào chạy."""
    runtime.run(SCOPED, session_id="t5")
    without = runtime.run(UNSCOPED)
    assert without.gate.action == "clarify"
    assert "conversation" not in without.planning


def test_a_slot_the_turn_already_filled_is_never_overwritten():
    """A3-R4. Ghi đè là để một câu cũ lấn át câu người dùng vừa gõ."""
    from gladiators.contracts import StructuredRequest

    state = ConversationState(
        session_id="s", turn=1, confirmed={"country": "vn"}, origin={"country": 1},
    )
    request = StructuredRequest(
        intent="analytical_query", country="id", language="vi", slots={},
    )
    updated, inherited = apply_to_request(request, state, frozenset())
    assert updated.country == "id"
    assert inherited.slots == {}


def test_an_unresolved_entity_is_never_remembered():
    """Luật 1. Nhớ một phỏng đoán sai nghĩa là không bao giờ hỏi lại nó nữa."""
    from gladiators.contracts import StructuredRequest

    request = StructuredRequest(
        intent="analytical_query", country="vn", language="vi",
        entity_text="kem", slots={},
    )
    state = update_from_response(
        None, "s", request, {"countries": ["vn", "id"]},
        entity_state="ambiguous_broad", new_topics=frozenset(),
    )
    assert "entity_text" not in state.confirmed
    assert state.confirmed["country"] == "vn"


def test_a_slot_older_than_the_turn_budget_is_dropped():
    from gladiators.contracts import StructuredRequest

    state = ConversationState(
        session_id="s", turn=MAX_TURN_AGE + 1,
        confirmed={"country": "vn"}, origin={"country": 1},
    )
    request = StructuredRequest(intent="analytical_query", language="vi", slots={})
    updated, inherited = apply_to_request(request, state, frozenset())
    assert updated.country is None
    assert "country" in inherited.dropped


def test_a_topic_change_drops_the_entity_but_keeps_the_scope():
    """Chệch khỏi spec CÓ CHỦ ĐÍCH, xem ghi chú ở ``conversation.SCOPE_SLOTS``.

    Spec xoá TOÀN BỘ state khi đổi chủ đề. Làm vậy thì gần như mọi câu hỏi tiếp
    theo mất ngữ cảnh — câu tiếp theo thường hỏi một measure khác, tức một chủ đề
    khác — nên WP không đạt được chính mục tiêu của nó. "Thị trường VN" không
    thuộc chủ đề nào; một listing cụ thể thì có.
    """
    from gladiators.contracts import StructuredRequest

    state = ConversationState(
        session_id="s", turn=1,
        confirmed={"country": "vn", "entity_text": "ABC123"},
        origin={"country": 1, "entity_text": 1},
        topic_signature=frozenset({"T1"}),
    )
    request = StructuredRequest(intent="analytical_query", language="vi", slots={})
    updated, inherited = apply_to_request(request, state, frozenset({"T9"}))
    assert updated.country == "vn"
    assert updated.entity_text is None
    assert inherited.expired is True
    assert "entity_text" in inherited.dropped


def test_the_store_expires_sessions_by_ttl():
    store = ConversationStore(ttl_seconds=0.0)
    store.put(ConversationState(session_id="old", touched_at=-1.0))
    assert store.get("old") is None


def test_the_store_evicts_least_recently_used():
    store = ConversationStore(capacity=2)
    for name in ("a", "b"):
        store.put(ConversationState(session_id=name, touched_at=1e9))
    store.get("a")
    store.put(ConversationState(session_id="c", touched_at=1e9))
    assert store.get("b") is None
    assert store.get("a") is not None


def test_an_empty_inheritance_renders_without_a_state_error():
    state = ConversationState(session_id="s", turn=1)
    assert Inheritance().as_dict(state)["inherited"] == []
