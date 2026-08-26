"""WP-B1 — chỉ số dự đoán có chọn lọc.

Một hệ **được phép nói "không biết"** không thể chấm bằng một tỷ lệ pass duy
nhất. Lỗ hổng cụ thể đang vá: metric từ chối cũ chỉ đếm `abstain`, trong khi
`clarify` chiếm 32% bộ đề chính và 52,5% DR-40 — một câu **trả lời được** mà hệ
trả `clarify` không rơi vào chỉ số nào, nó biến mất.

Test dựng `rows` bằng tay và so với giá trị tính tay, để công thức không thể
"đúng theo chính nó".
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_evaluation import (  # noqa: E402
    action_stability_rate,
    majority_action,
    selective_metrics,
)


# --- B1.3 · đa số phiếu thay cho run == 1 ---------------------------------

def test_majority_action_picks_the_majority_not_the_first_run():
    """Lấy `run == 1` là lấy một mẫu, không phải lấy hành vi."""
    rows = [
        {"id": "c1", "run": 1, "action": "allow"},
        {"id": "c1", "run": 2, "action": "clarify"},
        {"id": "c1", "run": 3, "action": "clarify"},
    ]
    assert majority_action(rows, "c1") == "clarify"


def test_majority_action_is_stable_when_all_runs_agree():
    rows = [{"id": "c1", "run": r, "action": "abstain"} for r in (1, 2, 3)]
    assert majority_action(rows, "c1") == "abstain"


def test_action_stability_rate_counts_cases_that_never_wobble():
    rows = [
        # c1 ổn định
        {"id": "c1", "run": 1, "action": "allow"},
        {"id": "c1", "run": 2, "action": "allow"},
        # c2 dao động
        {"id": "c2", "run": 1, "action": "allow"},
        {"id": "c2", "run": 2, "action": "clarify"},
    ]
    assert action_stability_rate(rows) == 0.5


# --- B1.1 · sáu chỉ số, so với số tính tay --------------------------------

# 4 case: 2 answerable (a1, a2) · 2 không answerable (r1, r2)
CASES = [
    {"id": "a1", "expected_action": "allow"},
    {"id": "a2", "expected_action": "allow"},
    {"id": "r1", "expected_action": "clarify"},
    {"id": "r2", "expected_action": "abstain"},
]

ROWS = [
    # a1: answerable, được trả lời, ĐÚNG
    {"id": "a1", "run": 1, "action": "allow", "evidence_count": 1, "passed": True},
    # a2: answerable nhưng bị CLARIFY -> từ chối oan. Đây là ca mà chỉ số cũ bỏ sót.
    {"id": "a2", "run": 1, "action": "clarify", "evidence_count": 0, "passed": False},
    # r1: không answerable, bị từ chối -> đúng
    {"id": "r1", "run": 1, "action": "clarify", "evidence_count": 0, "passed": True},
    # r2: không answerable NHƯNG được trả lời -> trả lời oan
    {"id": "r2", "run": 1, "action": "allow", "evidence_count": 2, "passed": False},
]


@pytest.fixture(scope="module")
def m():
    return selective_metrics(CASES, ROWS)


def test_coverage(m):
    # answered ∧ answerable = {a1} ; answerable = {a1, a2}
    assert m["coverage"] == 0.5


def test_risk(m):
    # answered = {a1, r2} ; answered ∧ ¬correct = {r2}
    assert m["risk"] == 0.5


def test_over_refusal_rate_sees_clarify(m):
    """Chỉ số cũ mù ca này: a2 trả lời được nhưng bị `clarify`."""
    # refused ∧ answerable = {a2} ; answerable = {a1, a2}
    assert m["over_refusal_rate"] == 0.5


def test_over_answer_rate(m):
    # answered ∧ ¬answerable = {r2} ; ¬answerable = {r1, r2}
    assert m["over_answer_rate"] == 0.5


def test_refusal_precision(m):
    # refused ∧ ¬answerable = {r1} ; refused = {a2, r1}
    assert m["refusal_precision"] == 0.5


def test_refusal_recall(m):
    # refused ∧ ¬answerable = {r1} ; ¬answerable = {r1, r2}
    assert m["refusal_recall"] == 0.5


# --- clarify PHẢI được tính là một dạng từ chối ---------------------------

def test_clarify_counts_as_refusal_not_as_nothing():
    """Nếu `clarify` bị bỏ qua, over_refusal_rate sẽ ra 0 — con số gây hiểu nhầm."""
    cases = [{"id": "x", "expected_action": "allow"}]
    rows = [{"id": "x", "run": 1, "action": "clarify", "evidence_count": 0, "passed": False}]
    out = selective_metrics(cases, rows)
    assert out["over_refusal_rate"] == 1.0
    assert out["coverage"] == 0.0


def test_allow_without_evidence_is_not_answered():
    """`allow` mà không có evidence thì chưa trả lời được gì."""
    cases = [{"id": "x", "expected_action": "allow"}]
    rows = [{"id": "x", "run": 1, "action": "allow", "evidence_count": 0, "passed": False}]
    out = selective_metrics(cases, rows)
    assert out["coverage"] == 0.0


# --- B1.2 · luật suy diễn nhãn answerable ---------------------------------

def test_explicit_answerable_key_wins_over_inference():
    """Bộ đề độc lập (B3) sẽ khai `answerable` tường minh; nó phải thắng."""
    cases = [{"id": "x", "expected_action": "clarify", "answerable": True}]
    rows = [{"id": "x", "run": 1, "action": "clarify", "evidence_count": 0, "passed": True}]
    out = selective_metrics(cases, rows)
    assert out["over_refusal_rate"] == 1.0


def test_self_written_suite_always_scores_zero_over_refusal():
    """§B1.2: trên bộ tự viết, luật suy diễn làm chỉ số này LUÔN bằng 0.

    Đó chính là lý do báo cáo phải tự dán cảnh báo — con số 0 ở đây không có
    nghĩa là hệ không từ chối oan, nó chỉ có nghĩa là bộ đề không đo được điều đó.
    """
    cases = [
        {"id": "a", "expected_action": "allow"},
        {"id": "b", "expected_action": "clarify"},
    ]
    rows = [
        {"id": "a", "run": 1, "action": "allow", "evidence_count": 1, "passed": True},
        {"id": "b", "run": 1, "action": "clarify", "evidence_count": 0, "passed": True},
    ]
    assert selective_metrics(cases, rows)["over_refusal_rate"] == 0.0


# --- B1-R1 · không xoá chỉ số cũ ------------------------------------------

def test_old_abstention_keys_survive():
    from scripts.run_evaluation import main  # noqa: F401  (import được là đủ)
    import inspect

    from scripts import run_evaluation

    source = inspect.getsource(run_evaluation)
    for key in ("abstention_precision", "abstention_recall", "abstention_f1"):
        assert f'"{key}"' in source, f"B1-R1: không được xoá {key}"


# --- mẫu số rỗng phải là None, không phải 0.0 ------------------------------

def test_empty_denominator_reports_none_not_zero():
    """`CLAUDE.md` §3.1 — điền 0 làm "không đo được" trông giống "đo được và bằng 0".

    `questions_a19` và `questions_ambiguity` không có case answerable nào. Báo
    `coverage = 0.0` ở đó sẽ đọc thành "hệ không phủ được gì", trong khi sự thật
    là không có gì để phủ.
    """
    cases = [{"id": "r1", "expected_action": "abstain"}]
    rows = [{"id": "r1", "run": 1, "action": "abstain", "evidence_count": 0, "passed": True}]
    out = selective_metrics(cases, rows)
    assert out["coverage"] is None, "không có case answerable ⇒ coverage không đo được"
    assert out["over_refusal_rate"] is None
    assert out["risk"] is None, "không trả lời câu nào ⇒ risk không đo được"
    # còn hai chỉ số này đo được vì có case không-answerable và có refusal
    assert out["refusal_precision"] == 1.0
    assert out["refusal_recall"] == 1.0
