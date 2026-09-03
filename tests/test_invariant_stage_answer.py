"""E3 merge unit `answer` — call site đi qua dispatcher, không lint bản sao.

Đỏ trước khi migrate: `workflow._generate` gọi thẳng `check_wording`, nên không
gì buộc nó tôn trọng registry. Ba điều test này khoá lại:

1. Mọi rule tag mà `check_wording` sinh ra phải được một handler `answer` nhận.
   Thêm một rule tag mới mà quên khai handler là cách lexicon và registry lệch
   nhau trong im lặng.
2. Dispatcher phải bắt được đúng những gì call site cũ bắt (parity).
3. Severity phải được giữ nguyên như spec khai — dispatcher không được tự nâng
   warning thành hard hay ngược lại (§E3.4).
"""
from __future__ import annotations

import pytest

from gladiators.agent.wording import check_wording
from gladiators.domain.invariant_handlers import (
    INVARIANT_HANDLERS,
    InvariantContext,
    enforce_invariants,
    hard_violations,
)
from gladiators.domain.invariants import INVARIANTS

CAUSAL = "Việc hạ giá đã làm tăng lượt bán và dẫn đến doanh số cao hơn."
JARGON = "LogicalQueryPlan cho thấy semantic_ref này thiếu catalog slice."
RULE_ID = "Yêu cầu bị chặn bởi A22-ALIGN-DATE nên không trả lời được."
REVENUE_NO_LABEL = "Doanh thu của shop này là 12.500.000 đồng."
CLEAN = "Trong phạm vi đã chọn, số cửa hàng quan sát được là 10."


def _answer_ctx(answer: str) -> InvariantContext:
    return InvariantContext(stage="answer", answer=answer)


# --- 1. lexicon và registry không được lệch --------------------------------

def test_every_wording_rule_tag_is_claimed_by_a_handler():
    """Rule tag không handler nào nhận = một luật chạy ngoài registry."""
    claimed: set[str] = set()
    for handler in INVARIANT_HANDLERS.values():
        if "answer" in handler.stages:
            claimed |= set(getattr(handler, "rules", frozenset()))

    produced = {
        item["rule"]
        for text in (CAUSAL, JARGON, RULE_ID, REVENUE_NO_LABEL)
        for item in check_wording(text)
    }
    assert produced, "fixture không kích hoạt rule nào — test đã mất tác dụng"
    assert produced <= claimed, f"rule tag không có handler: {sorted(produced - claimed)}"


# --- 2. parity: dispatcher bắt đúng thứ call site cũ bắt -------------------

@pytest.mark.parametrize(
    "answer",
    [CAUSAL, JARGON, RULE_ID, REVENUE_NO_LABEL],
    ids=["causal", "jargon", "rule_id", "revenue_no_estimate_label"],
)
def test_dispatcher_catches_what_check_wording_catches(answer):
    assert check_wording(answer), "fixture không còn kích hoạt rule nào"
    assert enforce_invariants("answer", _answer_ctx(answer))


def test_clean_answer_passes_both():
    assert check_wording(CLEAN) == []
    assert enforce_invariants("answer", _answer_ctx(CLEAN)) == ()


# --- 3. severity giữ nguyên như spec khai ---------------------------------

def test_severity_is_taken_from_the_spec_not_invented():
    violations = enforce_invariants("answer", _answer_ctx(CAUSAL))
    assert violations
    for item in violations:
        assert item.severity == INVARIANTS[item.invariant_id].severity


def test_proxy_label_rule_stays_a_warning():
    """§E3.4: dispatcher không được nâng warning thành hard.

    Ghi rõ ở đây vì call site hiện chặn cả warning — parity đó là có chủ đích,
    nhưng nó phải là quyết định của call site, không phải do dispatcher nói dối
    về severity.
    """
    violations = enforce_invariants("answer", _answer_ctx(REVENUE_NO_LABEL))
    proxy = [v for v in violations if v.invariant_id == "INV-PROXY-NOT-VERIFIED-SALES"]
    assert proxy, "fixture không kích hoạt được rule proxy"
    assert all(item.severity == "warning" for item in proxy)
    assert hard_violations(tuple(proxy)) == ()


def test_causal_claim_stays_hard():
    violations = enforce_invariants("answer", _answer_ctx(CAUSAL))
    assert hard_violations(violations), "causal claim phải là hard violation"


# --- 4. handler không được lint lại khi call site đã lint ------------------

def test_precomputed_violations_are_reused_not_relinted():
    """Handler nhận sẵn violation thì không gọi lại lexicon.

    Một bản sao thứ hai của lexicon là đúng cách hai tập từ ngữ lệch nhau, nên
    handler phải dùng lại kết quả call site đã tính.
    """
    ctx = InvariantContext(
        stage="answer", answer=None,
        wording_violations=({"rule": "causal_language", "term": "boi vi"},),
    )
    violations = enforce_invariants("answer", ctx)
    assert [item.invariant_id for item in violations] == ["INV-NO-CAUSAL-CLAIM"]
