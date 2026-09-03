"""W13.4 — plan bị khoá phải COMPILE VÀ CHẠY ĐƯỢC (SolutionSpec2808 §14.6).

Đây là phép kiểm mà nếu tồn tại từ đầu thì cả lớp lỗi HTTP 500 không ra tới
runtime: ``test_existing_plans_are_unchanged`` so ``model_dump_json`` và **không
bao giờ compile hay chạy** plan, nên 5/58 plan mang hình ``Scan→Filter→Rank``
sống trong baseline như một hợp đồng đã duyệt — trong khi chúng không thể thoả
hợp đồng output của chính chúng.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from gladiators.agent.workflow import AgentRuntime
from gladiators.data.repository import ArtifactRepository
from gladiators.planner.compiler import RANK_KEY_ALIAS, compile_plan
from gladiators.planner.executor import QueryExecutor
from gladiators.planner.query_ir import LogicalQueryPlan

BASELINE = json.loads(
    Path("tests/fixtures/synthesizer_equivalence_baseline.json").read_text(
        encoding="utf-8",
    ),
)

# §0.4: entry không chạy được phải nằm trong allowlist CÓ GHI LÝ DO — không giấu.
# Phát hiện khi viết chính test này: plan sl01 không qua nổi validate_plan ngay
# hôm nay (Rank trên measure.price_original thiếu lọc sentinel — synthesizer chỉ
# chèn sentinel cho measure.price, §4.8). Runtime không bao giờ chạy nó: workflow
# kiểm validate_plan(...).valid rồi rơi về template, nên nó là một HỢP ĐỒNG CHẾT
# sống trong baseline. Gỡ nó là việc của một work package về sentinel per-measure
# (W14 giai đoạn B), không phải của W13 — W13 không được đổi baseline (0 entry).
VALIDATION_REJECTED = {
    "semantic_linking:sl01": (
        "INV-PRICE-SENTINEL-EXCLUDED: Rank measure.price_original không có "
        "predicate loại sentinel; synthesizer chỉ guard measure.price"
    ),
}

# Phép quét sinh 84 câu của §21.14(c) — nguồn của §1.6.3 và của nghiệm thu W13.
RANKING_SWEEP = [
    f"{subject} nào có {measure} {direction} {market}?"
    for subject, measure, direction, market in itertools.product(
        ["Listing", "Sản phẩm", "Mặt hàng"],
        ["giá", "giá gốc", "điểm đánh giá", "số lượt đánh giá",
         "số lượt thích", "số ảnh", "phần trăm giảm giá"],
        ["cao nhất", "thấp nhất"],
        ["tại Việt Nam", "tại Indonesia"],
    )
]


@pytest.fixture(scope="module")
def executor() -> QueryExecutor:
    ex = QueryExecutor(ArtifactRepository())
    yield ex
    ex.close()


@pytest.fixture(scope="module")
def runtime() -> AgentRuntime:
    return AgentRuntime()


@pytest.mark.parametrize(
    "key",
    sorted(
        k for k, v in BASELINE.items()
        if isinstance(v, dict) and "exc" not in v and k not in VALIDATION_REJECTED
    ),
)
def test_locked_plan_produces_the_columns_it_declares(key, executor):
    """57/58 plan bị khoá không chỉ phải GIỮ NGUYÊN — chúng phải CHẠY ĐƯỢC."""
    plan = LogicalQueryPlan.model_validate(BASELINE[key])
    compiled = compile_plan(plan)
    frame = executor.execute(compiled).frame
    assert tuple(frame.columns) == compiled.expected_columns, key


@pytest.mark.parametrize("key", sorted(VALIDATION_REJECTED))
def test_a_dead_contract_in_the_baseline_stays_declared(key):
    """Entry trong allowlist phải THẬT SỰ hỏng vì đúng lý do đã ghi.

    Ai đó sửa được nó (thêm sentinel per-measure) thì test này đỏ — và đó là tín
    hiệu để XOÁ nó khỏi allowlist kèm lý do contract, chứ không phải để allowlist
    âm thầm phồng lên thành một tấm thảm quét bụi.
    """
    from gladiators.planner.compiler import CompilationError

    plan = LogicalQueryPlan.model_validate(BASELINE[key])
    with pytest.raises(CompilationError, match="PRICE-SENTINEL"):
        compile_plan(plan)


@pytest.mark.parametrize("question", RANKING_SWEEP)
def test_ranking_question_never_raises(question, runtime):
    """Bất biến #6 (fail-closed) kiểm QUA RUNTIME, không gọi hàm cô lập.

    Trước W13: 24/84 câu ở đây thoát khỏi ``run()`` bằng ``ExecutionFailure`` và
    thành HTTP 500 — một câu hỏi trả lời được đi ra bằng traceback, nặng hơn mọi
    ca từ chối oan. Không try/except quanh ``run``: raise chính là fail.
    """
    response = runtime.run(question)
    assert response.gate.action in {"allow", "clarify", "abstain"}


def test_the_rank_key_never_leaks_into_the_answer_frame(runtime):
    """W13.2: ``__rank_key__`` là cột kỹ thuật — nó phải sống tới tie detection
    rồi biến mất trước khi evidence được dựng."""
    response = runtime.run("Listing nào có giá thấp nhất tại Việt Nam?")
    assert response.gate.action == "allow"
    for item in response.evidence:
        assert RANK_KEY_ALIAS not in str(item.metric)
        assert RANK_KEY_ALIAS not in json.dumps(item.attrs, ensure_ascii=False, default=str)


def test_the_projection_does_not_blind_the_tie_detector(runtime):
    """Điều kiện hình dạng thứ nhất của §14.8: bản thiếu ``RANK_KEY_ALIAS`` trả
    ``allow`` với ``rating = 0.0`` cho đúng câu này — một kết quả HOÀ ở mép cắt
    đi ra như một câu trả lời chắc chắn."""
    response = runtime.run("Listing nào có điểm đánh giá thấp nhất tại Indonesia?")
    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A22-ALIGN-RANK-TIE"


def test_the_tie_message_names_the_direction_that_was_asked(runtime):
    """W13.5: chiều lấy từ node Rank của plan, không từ chuỗi câu hỏi."""
    low = runtime.run("Listing nào có điểm đánh giá thấp nhất tại Indonesia?")
    assert "thấp nhất" in low.gate.reason
    assert "cao nhất" not in low.gate.reason


def test_the_template_path_is_untouched(runtime):
    """Điều kiện hình dạng thứ hai của §14.8: đường template không đổi."""
    response = runtime.run("Listing nào có giá cao nhất tại Việt Nam?")
    assert response.gate.action == "allow"
    values = [item.value for item in response.evidence if item.metric == "price"]
    assert values == [3033180.0]


def test_a_broken_execution_becomes_a_typed_refusal_not_a_traceback(runtime, monkeypatch):
    """W13.3 độc lập với W13.1/W13.2: hai mục kia sửa MỘT nguyên nhân, mục này
    sửa LỚP HẬU QUẢ — nên nó phải bắt được cả nguyên nhân chưa biết."""
    from gladiators.agent import workflow as workflow_module
    from gladiators.planner.executor import ExecutionFailure, ExecutionIssue

    def explode(tool_plan, ctx):
        raise ExecutionFailure(
            ExecutionIssue(code="schema_invalid", message_key="test.synthetic",
                           details={"why": "test"}),
            "nổ có chủ đích",
        )

    monkeypatch.setattr(workflow_module, "dispatch", explode)
    response = AgentRuntime().run("Có bao nhiêu listing tại Việt Nam ngày 03/07?")

    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A19-EXECUTION"
    assert response.evidence == []
    error = response.planning["execution_error"]
    # code/details CÓ KIỂU, không phải str(exc) — diagnose_refusals đọc khoá này.
    assert error["type"] == "ExecutionFailure"
    assert error["code"] == "schema_invalid"
    assert error["details"] == {"why": "test"}


def test_the_execution_error_key_stays_silent_on_a_healthy_run(runtime):
    """Khoá đếm bắt buộc (§0.3 ô 4): nếu W13.1 đúng thì số lần bắn là 0 — và một
    số 0 ĐO ĐƯỢC khác hẳn một nhánh không ai biết có chạy hay không."""
    response = runtime.run("Có bao nhiêu listing tại Việt Nam ngày 03/07?")
    assert response.gate.action == "allow"
    assert "execution_error" not in response.planning
