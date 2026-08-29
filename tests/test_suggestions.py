"""WP-A8 — gợi ý câu hỏi gần nhất khi từ chối.

`GateDecision.answerable_alternative` trước đây là chuỗi viết tay cố định theo
rule: nó không biết câu hỏi vừa rồi hỏi về cái gì.

Luật sống còn ở đây là A8-R1: gợi ý phải CHẠY ĐƯỢC THẬT. Gợi ý một câu mà hệ
cũng từ chối thì tệ hơn không gợi ý — người dùng làm theo và nhận lời từ chối
thứ hai.
"""
from __future__ import annotations

import pytest

from gladiators.agent.suggestions import nearest_answerable
from gladiators.agent.workflow import AgentRuntime


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    return AgentRuntime(trace_dir=tmp_path_factory.mktemp("traces"))


# --- A8-R1 · gợi ý nào sinh ra cũng phải chạy được -----------------------

@pytest.mark.parametrize("question", [
    "Giá trung vị tại VN",
    "Doanh thu ước tính tại VN",
])
def test_every_suggestion_actually_runs(runtime, question):
    response = runtime.run(question)
    hints = nearest_answerable(response.request, runtime)
    assert hints, "câu này bind được ref nên phải có gợi ý"
    for hint in hints:
        trial = runtime.run(hint)
        assert trial.gate.action == "allow", f"gợi ý không chạy được: {hint}"
        assert trial.evidence, f"gợi ý allow nhưng rỗng evidence: {hint}"


# --- A8-R2 · không bind được ref nào thì im lặng -------------------------

def test_no_bound_ref_gives_no_suggestion(runtime):
    """Câu hoàn toàn ngoài từ vựng thì im lặng đúng hơn là đoán."""
    response = runtime.run("Lợi nhuận của shop tại VN?")
    assert nearest_answerable(response.request, runtime) == ()


# --- xác định: chạy hai lần ra cùng kết quả -----------------------------

def test_suggestions_are_deterministic(runtime):
    response = runtime.run("Giá trung vị tại VN")
    first = nearest_answerable(response.request, runtime)
    second = nearest_answerable(response.request, runtime)
    assert first == second


# --- A8-R3 · không đổi rule_id và reason ---------------------------------

def test_rule_id_and_reason_are_untouched(runtime):
    """WP này CHỈ thêm phần gợi ý.

    Câu neo đổi từ "Giá trung vị tại VN" sang "Giá trung bình tại VN": W5 làm
    câu trung vị TRẢ LỜI ĐƯỢC (132 000 — đó là mục đích của W5), nên test này
    cần một câu vẫn bị từ chối; trung bình chưa được chứng nhận cho
    measure.price và ra A19-AGGREGATION (W5.1).
    """
    response = runtime.run("Giá trung bình tại VN")
    assert response.gate.rule_id == "A19-AGGREGATION"
    assert "gợi ý" not in response.gate.reason.lower()
    assert response.gate.answerable_alternative


# --- không đệ quy: chạy thử không được tự sinh gợi ý ---------------------

def test_trial_runs_do_not_recurse(runtime):
    """Gợi ý gọi runtime.run, mà run lại sinh gợi ý — phải có chốt chặn."""
    # W8.3: câu neo nêu rõ khái niệm — "có voucher" trần nay clarify.
    response = runtime.run("Có bao nhiêu listing có voucher có cấu trúc tại Việt Nam ngày 03/07?")
    assert response.gate.action == "allow"
    assert getattr(runtime, "_in_suggestion_trial", False) is False
