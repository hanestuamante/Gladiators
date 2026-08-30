"""W15.3 — khai kỳ vọng thì phải có người chấm (SolutionSpec2808 §16.4).

Kiểm kê §16.1: 14 file trong ``eval/`` khai ``expected_action`` (240 ca) mà CI
chấm đúng MỘT. Một file kỳ vọng không có người đọc là một tài liệu, không phải
một phép đo — và nó trông giống hệt một phép đo đang xanh. ``questions_critic``
lọt đúng bằng cách đó: có test ĐỌC file (làm đầu vào), không test nào chạm
``expected_action``.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Mỗi entry trỏ tới một LỆNH hoặc TEST ID cụ thể — không phải một câu mô tả.
SCORED_BY = {
    "eval/questions.json":
        "scripts/run_evaluation.py --runs 3 --provider offline (CI)",
    "eval/questions_v2.json":
        "scripts/run_evaluation.py --suite eval/questions_v2.json (W3 CI)",
    "eval/questions_a19.json":
        "scripts/run_evaluation.py --suite eval/questions_a19.json (W3 CI)",
    "eval/questions_ambiguity.json":
        "scripts/run_evaluation.py --suite eval/questions_ambiguity.json (W3 CI)",
    "eval/questions_boundaries.json":
        "scripts/run_evaluation.py --suite eval/questions_boundaries.json (W3 CI)",
    "eval/questions_counting.json":
        "scripts/run_evaluation.py --suite eval/questions_counting.json (W3 CI)",
    "eval/questions_schema.json":
        "scripts/run_evaluation.py --suite eval/questions_schema.json (W3 CI)",
    "eval/questions_critic.json":
        "scripts/run_evaluation.py --suite eval/questions_critic.json (CI, W15.2)",
    "eval/questions_multiturn.json": "scripts/run_multiturn.py (CI, W15.1)",
    "eval/dr2607.json": "tests/test_dr2607_regression.py::test_executable_route_contracts",
    "eval/p0_probes.json": "tests/test_p0_regression_lock.py::test_baseline_action_and_rule_are_pinned",
    "eval/independent/answerable_manual.json": "scripts/run_risk_coverage.py",
    # Benchmark accuracy v1 (TC_formulation): scorer nghiêm ngặt riêng, chạy
    # trong CI (dev) và ở release evaluation (holdout).
    "eval/accuracy/v1/dev.json":
        "scripts/run_accuracy_benchmark.py --split dev (CI)",
    "eval/accuracy/v1/holdout.json":
        "scripts/run_accuracy_benchmark.py --split holdout (release evaluation)",
}

# Bộ đề chỉ dùng với provider thật, cố ý không có scorer offline. Nằm trong
# allowlist CÓ LÝ DO, không nằm ngoài bảng: "không ai chấm" phải là một quyết
# định đọc được, không phải một khoảng trống.
PROVIDER_ONLY = {
    "eval/groq_regression.json": "cần provider Groq — không replay offline được",
    "eval/pilot_gemini.json": "cần provider Gemini — không replay offline được",
}

# Bản ghi ANNOTATION thô của benchmark accuracy — không phải suite để chấm:
# chúng là đầu vào của adjudication (agreement/kappa ghi ở manifest), và nhãn
# trong đó đã được hợp nhất vào dev.json/holdout.json vốn CÓ scorer.
ANNOTATION_RECORDS = {
    "eval/accuracy/v1/annotations_A.json",
    "eval/accuracy/v1/annotations_B.json",
    # JSON Schema của benchmark — nhắc TÊN trường expected_action trong định
    # nghĩa kiểu, không khai kỳ vọng nào.
    "eval/accuracy/v1/schema.json",
}


def _declares_expected_action(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    text = json.dumps(payload)
    return '"expected_action"' in text


def test_every_suite_declaring_expected_action_has_a_scorer():
    declaring = sorted(
        str(path.relative_to(REPO)).replace("\\", "/")
        for path in REPO.glob("eval/**/*.json")
        # eval/reports/ là ĐẦU RA của các phép đo — per-case verdict trong đó
        # nhắc expected_action nhưng không phải một suite cần scorer.
        if "reports" not in path.parts and _declares_expected_action(path)
    )
    for path in declaring:
        if path in ANNOTATION_RECORDS:
            continue
        assert path in SCORED_BY or path in PROVIDER_ONLY, (
            f"{path} khai expected_action nhưng không ai đọc nó — thêm scorer "
            "hoặc khai lý do vào PROVIDER_ONLY"
        )


def test_the_maps_do_not_name_ghost_suites():
    for path in list(SCORED_BY) + list(PROVIDER_ONLY):
        assert (REPO / path).exists(), f"{path} không tồn tại"


# --- scorer phải ĐỎ ĐƯỢC khi kỳ vọng sai -----------------------------------
#
# "Có test đọc file" không phải điều kiện — điều kiện là có ai đó so
# response.gate.action với expected_action, và cách chứng minh duy nhất không
# dựa vào đọc code bằng mắt là đưa cho scorer một kỳ vọng CỐ TÌNH SAI rồi xem
# nó có đỏ không. Một scorer không đỏ được khi kỳ vọng sai là một scorer không
# tồn tại.


def _doctored_copy(suite_path: str, tmp_path: Path) -> Path:
    cases = json.loads((REPO / suite_path).read_text(encoding="utf-8"))
    flipped = False
    for case in cases:
        turns = case.get("turns") or [case]
        for entry in turns:
            if entry.get("expected_action") == "allow":
                entry["expected_action"] = "abstain"
                flipped = True
                break
        if flipped:
            break
    assert flipped, f"{suite_path}: không có ca allow nào để lật"
    out = tmp_path / Path(suite_path).name
    out.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    return out


@pytest.mark.parametrize("suite", [
    "eval/questions_counting.json",   # đại diện họ run_evaluation --suite
    "eval/questions_critic.json",
])
def test_run_evaluation_goes_red_on_a_wrong_expectation(suite, tmp_path):
    doctored = _doctored_copy(suite, tmp_path)
    result = subprocess.run(
        [sys.executable, "scripts/run_evaluation.py", "--suite", str(doctored),
         "--runs", "1", "--provider", "offline"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=REPO,
    )
    report = json.loads(result.stdout[result.stdout.index("{"):])
    assert report["end_to_end_accuracy"] < 1.0, (
        f"{suite}: scorer không đỏ khi kỳ vọng cố tình sai"
    )
    assert report["failures"], suite


def test_run_multiturn_goes_red_on_a_wrong_expectation(tmp_path):
    doctored = _doctored_copy("eval/questions_multiturn.json", tmp_path)
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        from run_multiturn import run
    finally:
        sys.path.pop(0)
    report = run(str(doctored.relative_to(REPO)) if doctored.is_relative_to(REPO)
                 else str(doctored))
    assert report["turns_failed"] >= 1
    assert report["failures"]


def test_risk_coverage_counts_a_wrong_expectation(tmp_path):
    """run_risk_coverage suy nhãn answerable từ expected_action — lật một ca
    allow thành abstain phải đổi over_answer_rate/refusal ở L0."""
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        import run_risk_coverage as rc
    finally:
        sys.path.pop(0)
    cases = json.loads(
        (REPO / "eval/independent/answerable_manual.json").read_text(encoding="utf-8"),
    )
    flipped = next(c for c in cases if c["expected_action"] == "allow"
                   and c["id"] == "ans001")
    flipped["expected_action"] = "abstain"
    flipped["answerable"] = False

    from gladiators.agent.workflow import AgentRuntime

    row = rc.measure(cases, AgentRuntime())
    # ans001 vẫn được hệ trả lời ⇒ với nhãn lật, nó thành một ca "trả lời thứ
    # không answerable" và over_answer_rate phải KHÁC 0.
    assert row["over_answer_rate"] > 0


# --- scorer pytest: nghĩa vụ AST -------------------------------------------
#
# CHỆCH KHỎI SPEC CÓ CHỦ ĐÍCH cho hai suite chấm bằng pytest: chạy pytest lồng
# trong pytest với một file fixture bị tráo đòi dựng cả cây làm việc giả (test
# đọc đường dẫn tương đối lúc import module). Thay bằng nghĩa vụ AST — cùng
# khuôn với test AST của W12: khẳng định file test THẬT SỰ so sánh
# ``gate.action`` với ``expected_action``, không chỉ đọc file làm đầu vào.


@pytest.mark.parametrize(("test_file", "expectation_key"), [
    ("tests/test_dr2607_regression.py", "expected_action"),
    # p0 lock ghim kỳ vọng dưới khoá baseline["action"], không phải
    # expected_action — cùng nghĩa vụ, khác tên khoá.
    ("tests/test_p0_regression_lock.py", "action"),
])
def test_the_pytest_scorer_actually_asserts_the_expectation(test_file, expectation_key):
    tree = ast.parse((REPO / test_file).read_text(encoding="utf-8"))
    source = ast.dump(tree)
    # Cả hai vế phải xuất hiện trong một phép so sánh ở đâu đó trong file:
    # truy cập .gate.action và subscript theo khoá kỳ vọng.
    touches_action = "attr='action'" in source and "attr='gate'" in source
    touches_expectation = f"value='{expectation_key}'" in source
    assert touches_action and touches_expectation, (
        f"{test_file} đọc suite nhưng không so gate.action với {expectation_key}"
    )
