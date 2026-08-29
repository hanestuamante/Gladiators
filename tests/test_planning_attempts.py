"""W12.2 — ``planning.attempts``: cái gì đã thử, và từ chối vì sao.

Mọi test ở đây đi qua ``AgentRuntime.run`` thật, không gọi hàm cô lập — đúng bài
học P-B (`CLAUDE.md` §5.1.3): tám test cô lập từng xanh suốt thời gian một nhánh
là code chết.
"""
from __future__ import annotations

import pytest

from gladiators.agent.workflow import AgentRuntime

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(scope="module")
def runtime() -> AgentRuntime:
    return AgentRuntime()


def test_the_case_the_gateway_used_to_skip_now_answers(runtime):
    """Ca ans035 — ca W12 dùng để chứng minh "nhánh chưa bao giờ chạy".

    Trước W12, lời từ chối là "không có provider" — chỉ sai đường: người đọc
    trace đi mua một provider trong khi thứ chặn là
    ``_synthesis_beats_template``. W5.3 mở đúng cái cổng đó cho câu hỏi vô
    hướng, nên ans035 nay trả lời được.
    """
    response = runtime.run("Giá trung vị tại Việt Nam ngày 03/07 là bao nhiêu?")
    assert response.gate.action == "allow"
    assert 132000.0 in [item.value for item in response.evidence]
    attempts = {item["branch"]: item for item in response.planning["attempts"]}
    assert attempts["synthesizer"]["tried"] is True
    assert attempts["synthesizer"]["declined"] == []


def test_a_branch_that_never_ran_says_so_with_a_reason(runtime):
    """Bất biến W12 vẫn phải đúng cho MỌI nhánh không chạy, trên một câu vẫn bị
    từ chối — nếu không, lần chặn tiếp theo lại vô hình như trước W12."""
    response = runtime.run("Giá trung bình tại Việt Nam ngày 03/07 là bao nhiêu?")
    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A19-AGGREGATION"
    attempts = {item["branch"]: item for item in response.planning["attempts"]}
    # tried=False bắt buộc kèm lý do — cho MỌI nhánh không chạy.
    for item in attempts.values():
        if not item["tried"]:
            assert item["declined"], f"nhánh {item['branch']} không thử mà không nói vì sao"


def test_the_case_the_ladder_used_to_block_now_answers(runtime):
    """Ca ans031 — chính ca mà W12 dùng để chứng minh "plan ĐÚNG, thang chặn".

    W12 làm cho lý do nhìn thấy được: ``attempts`` cho thấy synthesizer thành
    công và không từ chối gì, nên A19-PLAN ở đây khác hẳn A19-PLAN của một ca
    synthesizer bó tay. W7 gỡ nốt cái chặn. Hai khẳng định của W12 vẫn phải
    đúng — nếu ``attempts`` mất đi thì lần chặn tiếp theo lại vô hình như cũ.
    """
    response = runtime.run(
        "Có bao nhiêu listing của shop chính hãng tại Việt Nam ngày 03/07?",
    )
    assert response.gate.action == "allow"
    assert 465 in [item.value for item in response.evidence]
    assert response.planning["escalation_mode"] == "single"
    assert response.planning["risk"]["deterministic_bypass"]["applied"] is True
    attempts = {item["branch"]: item for item in response.planning["attempts"]}
    assert attempts["synthesizer"]["tried"] is True
    assert attempts["synthesizer"]["declined"] == []


def test_every_a22_refusal_carries_a_failing_alignment_verdict(runtime):
    """§13.4: planning.alignment và gate.rule_id không được phép mâu thuẫn.

    Đo được ở ans019: gate nói A22-ALIGN-DATE trong khi ``planning.alignment``
    ghi ``aligned: true`` — verdict chặn nằm ở khoá khác và người đọc không có
    cách nào biết phải nhìn đâu.
    """
    # Câu neo cũ ("thay đổi thế nào từ 01/07 đến 03/07") nay TRẢ LỜI ĐƯỢC nhờ
    # W6 — đổi sang một câu vẫn mang từ chối A22: tiền đề "giảm mạnh" bị dữ
    # liệu phủ nhận (581 → 668).
    response = runtime.run("Vì sao số listing tại Việt Nam giảm mạnh từ 01/07 đến 03/07?")
    assert response.gate.rule_id.startswith("A22")

    verdicts = [
        value for key, value in response.planning.items()
        if "alignment" in key and isinstance(value, dict) and "aligned" in value
    ]
    assert any(item["aligned"] is False for item in verdicts), (
        "mọi ca A22-* phải có ít nhất một khoá alignment aligned=False"
    )
    assert response.planning["alignment_verdict"]["rule_id"] == response.gate.rule_id


def test_an_answered_question_records_the_winning_branch_too(runtime):
    """Ghi MỌI nhánh, kể cả nhánh thắng — không có mẫu số thì không biết nhánh
    nào đang gánh việc."""
    response = runtime.run("Có bao nhiêu listing tại Việt Nam ngày 03/07?")
    assert response.gate.action == "allow"
    attempts = response.planning.get("attempts") or []
    assert attempts, "đường thắng cũng phải để lại chuỗi nhánh"
    assert any(item["branch"] in {"synthesizer", "template"} for item in attempts)


def test_exception_boundaries_preserve_the_typed_reasons():
    """§13.4: lý do typed phải sống sót qua ``OpenPlannerError`` →
    ``AnalyticalPlanError``. Chết ở boundary thì collector gom được bao nhiêu
    cũng vô nghĩa."""
    from gladiators.planner.analytical import AnalyticalPlanError
    from gladiators.planner.open_planner import OpenPlannerError

    original = OpenPlannerError(
        "x", rule_id="A19-AGGREGATION",
        decline_codes=("aggregation_not_certified",),
        attempts=({"branch": "synthesizer", "tried": True, "declined": []},),
    )
    converted = AnalyticalPlanError(
        str(original), rule_id=original.rule_id,
        decline_codes=original.decline_codes, attempts=original.attempts,
    )
    assert converted.rule_id == "A19-AGGREGATION"
    assert converted.decline_codes == ("aggregation_not_certified",)
    assert converted.attempts[0]["branch"] == "synthesizer"

    # Mặc định additive: caller cũ raise bằng message trần vẫn ra A19-PLAN.
    bare = AnalyticalPlanError("chỉ có message")
    assert bare.rule_id == "A19-PLAN"
    assert bare.decline_codes == () and bare.attempts == ()


def test_w12_changed_no_outcome_on_the_locked_suites(runtime):
    """§13.6 dòng cuối — điều kiện đủ để W12 đi trước mọi work package khác.

    Ba ca đại diện ba kết cục (allow / abstain / clarify) trên bộ khoá; phép kiểm
    toàn suite nằm ở eval gate, đây là hàng rào nhanh trong pytest.
    """
    for question, action in (
        ("Có bao nhiêu listing tại Việt Nam ngày 03/07?", "allow"),
        ("Lợi nhuận ròng của từng shop tại Việt Nam là bao nhiêu?", "abstain"),
        ("Có bao nhiêu listing?", "clarify"),
    ):
        assert runtime.run(question).gate.action == action, question
