"""W14 giai đoạn A — giá trị không phải phép đo (SolutionSpec2808 §15).

Một hằng số ``PRICE_SENTINEL`` trong source bảo vệ ĐÚNG MỘT measure; tám measure
còn lại không được bảo vệ, và không ai thấy sự chênh đó vì nó là một câu ``if``
chứ không phải một hàng trong bảng. W14 biến nó thành bảng, và tách hai quyền
khác nhau: **loại một dòng** là quyết định của chủ dữ liệu, **từ chối trả lời
bằng một giá trị chưa ai phân loại** là quyết định của hệ.
"""
from __future__ import annotations

import pytest

from gladiators.agent.workflow import AgentRuntime
from gladiators.domain.metrics import (
    VALUE_CLASS_RULES,
    ValueClassRule,
    approved_exclusion_predicates,
    matches_value_class,
    value_class_rules_for,
)

REPDIGIT = next(rule for rule in VALUE_CLASS_RULES if rule.rule_id == "price-repdigit-nine")


@pytest.fixture(scope="module")
def runtime() -> AgentRuntime:
    return AgentRuntime()


# --- luật phát hiện --------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (9_999_999, True), (999_999_999, True),
        (3_033_180, False), (999, False), (1000, False), (0, False),
        (-9_999_999, False), (9_999_999.5, False), (99_999.0, False),
    ],
)
def test_repdigit_nine_matches_only_all_nine_integers(value, expected):
    """Luật theo ĐẶC TÍNH dữ liệu, không theo danh sách ID — một danh sách ID
    không sống sót qua một lần làm mới dữ liệu."""
    assert matches_value_class(REPDIGIT, value) is expected


def test_a_shorter_all_nine_number_is_below_the_digit_floor():
    """``999`` là ba chữ số chín và vẫn KHÔNG khớp: ngưỡng ``min_digits`` là thứ
    phân biệt một giá trị giữ chỗ với một mức giá nhỏ hợp lệ."""
    assert matches_value_class(REPDIGIT, 999) is False
    assert REPDIGIT.min_digits == 7


def test_companion_is_zero_reads_the_companion_not_the_value():
    rule = next(r for r in VALUE_CLASS_RULES if r.kind == "companion_is_zero")
    assert matches_value_class(rule, 4.9, companion=0) is True
    assert matches_value_class(rule, 4.9, companion=12) is False
    assert matches_value_class(rule, 4.9, companion=None) is False


# --- duyệt vs chưa duyệt ---------------------------------------------------

def test_an_unapproved_rule_never_becomes_a_predicate():
    """Loại một dòng là ĐỔI ĐỊNH NGHĨA metric — quyết định của chủ dữ liệu.
    Một luật chưa ai ký không được lẻn vào định nghĩa qua một predicate."""
    for rule in value_class_rules_for("measure.price"):
        if rule.decision_id is None:
            assert not any(
                value in rule.values
                for _ref, _op, value in approved_exclusion_predicates("measure.price")
            )
    # Chỉ luật đã duyệt xuất hiện, và nó tái lập ĐÚNG hằng số cũ.
    assert approved_exclusion_predicates("measure.price") == (
        ("measure.price", "lt", 999_999_999),
    )
    assert approved_exclusion_predicates("measure.price_original") == ()
    assert approved_exclusion_predicates("measure.rating") == ()


def test_approving_a_rule_turns_it_into_a_predicate(monkeypatch):
    """Điền ``decision_id`` ⇒ predicate xuất hiện. Đây là bước mà chỉ chủ dữ
    liệu được làm; test chỉ chứng minh cơ chế nối đúng, không thay họ làm."""
    from gladiators.domain import metrics

    approved = ValueClassRule(
        "price-repdigit-nine", "measure.price", "equals", "placeholder",
        values=(9_999_999,), decision_id="test-decision",
    )
    monkeypatch.setattr(metrics, "VALUE_CLASS_RULES", (approved,))
    assert metrics.approved_exclusion_predicates("measure.price") == (
        ("measure.price", "lt", 9_999_999),
    )


# --- qua runtime -----------------------------------------------------------

def test_a_boundary_value_under_an_unapproved_rule_blocks_the_answer(runtime):
    """Giá cao nhất ở Indonesia là một giá trị toàn chữ số chín. Trước W14 nó đi
    ra như một mức giá thật — không lớp nào phía sau bắt được, vì tie detector
    chỉ sống trên đường ``Rank`` với ``rank_limit``."""
    response = runtime.run("Listing nào có giá cao nhất tại Indonesia?")
    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A19-VALUE-CLASS"
    report = response.planning["value_class"]
    assert report["blocked"] is True
    assert report["boundary_hits"][0]["rule_id"] == "price-repdigit-nine"
    assert report["boundary_hits"][0]["approved"] is False
    # Câu từ chối không khẳng định giá trị đó là rác — chỉ khẳng định chưa ai
    # quyết định nó là gì. Và không chèn chữ số (CLAUDE.md §3.1).
    assert not any(char.isdigit() for char in response.gate.reason)


def test_a_clean_boundary_answers_and_says_so(runtime):
    """Giá cao nhất ở VN không rơi vào luật nào ⇒ trả lời như cũ, và khoá đếm
    ``blocked`` bật lên FALSE — một số 0 ĐO ĐƯỢC khác hẳn một nhánh không ai
    biết có chạy hay không (CLAUDE.md §5.1.3)."""
    response = runtime.run("Listing nào có giá cao nhất tại Việt Nam?")
    assert response.gate.action == "allow"
    assert 3_033_180.0 in [item.value for item in response.evidence]
    assert response.planning["value_class"]["blocked"] is False
    assert "measure.price" in response.planning["value_class"]["checked_refs"]


def test_a_measure_with_no_rule_is_untouched(runtime):
    """Không luật nào cho ``measure.like_count`` ⇒ không kiểm, không đổi."""
    response = runtime.run("Listing nào có số lượt thích cao nhất tại Indonesia?")
    report = response.planning.get("value_class") or {}
    assert "measure.like_count" not in (report.get("checked_refs") or [])


def test_a_median_is_never_blocked_by_a_boundary_value(runtime):
    """Trung vị bền với đuôi: chặn nó lấy đi năng lực mà không đổi được con số
    nào. ``aggregation ∈ {median, mean, sum, count, share}`` không kiểm biên."""
    from gladiators.planner.query_ir import LogicalQueryPlan

    response = runtime.run("Có bao nhiêu listing tại Indonesia ngày 03/07?")
    assert response.gate.action == "allow"
    assert (response.planning.get("value_class") or {}).get("blocked") is not True


def test_the_registry_reproduces_the_old_constant_exactly():
    """58 plan bị khoá không đổi một byte — bằng chứng registry tái lập ĐÚNG
    nhánh ``if`` cũ, chứ không phải một luật mới đội lốt refactor."""
    from gladiators.planner.analytical import build_analytical_plan
    from gladiators.planner.compiler import compile_plan

    compiled = compile_plan(build_analytical_plan("highest_price_listing", "vn"))
    assert compiled.exclusion_predicate_refs == ("measure.price",)
    assert "999999999" in compiled.sql or 999999999 in compiled.parameters


def test_every_rule_names_a_ref_that_exists():
    """Bất biến import: một ref gõ sai trong registry phải nổ lúc dựng catalog,
    không phải lúc một câu hỏi vô tình chạm vào nó."""
    from gladiators.domain.catalog import CATALOG

    for rule in VALUE_CLASS_RULES:
        assert rule.ref in CATALOG, rule.rule_id
        if rule.companion_ref:
            assert rule.companion_ref in CATALOG, rule.rule_id


def test_no_rule_carries_a_decision_id_an_agent_invented():
    """A12-R6 cùng luật: agent không được điền ``decision_id``. Giá trị duy nhất
    được phép hôm nay là xuất xứ THẬT của hằng số cũ — một literal trong source,
    không phải một quyết định có chữ ký."""
    approved = {rule.decision_id for rule in VALUE_CLASS_RULES if rule.decision_id}
    assert approved == {"legacy-source-literal"}
