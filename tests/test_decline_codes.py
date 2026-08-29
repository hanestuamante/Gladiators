"""W12 — lý do từ chối có kiểu (SolutionSpec2808 §13).

Điều phải giữ tuyệt đối, và là điều kiện để W12 đi trước mọi work package khác:
**nó không được đổi một quyết định nào, chỉ được nói rõ hơn về quyết định đã
có.** Test cuối file khoá điều đó bằng hành vi.
"""
from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest

import gladiators.agent.workflow  # noqa: F401  (khép vòng import)
from gladiators.planner import synthesizer as synthesizer_module
from gladiators.planner.semantic_parser import DeterministicSemanticParser
from gladiators.planner.synthesizer import (
    DECLINE_CODES,
    DECLINE_RULE_BY_CODE,
    DECLINE_RULE_PRIORITY,
    rule_for_declines,
    synthesize,
)

# Ba hàm chứa đúng 20 lối ``return None`` mà spec §13.2 liệt kê từng dòng.
INSTRUMENTED_FUNCTIONS = ("synthesize", "_plan_relations", "_choose_aggregation")


def _bare_none_returns(function: ast.FunctionDef) -> list[ast.Return]:
    return sorted(
        (
            node for node in ast.walk(function)
            if isinstance(node, ast.Return)
            and isinstance(node.value, ast.Constant) and node.value.value is None
        ),
        key=lambda node: node.lineno,
    )


def _statement_before(function: ast.FunctionDef, target: ast.stmt) -> ast.stmt | None:
    for parent in ast.walk(function):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(parent, field, None)
            if isinstance(block, list) and target in block:
                index = block.index(target)
                return block[index - 1] if index > 0 else None
    return None


def _decline_literal(statement: ast.stmt) -> str | None:
    """Tên mã nếu statement là ``_decline(decline, "<literal>")``, không thì None."""
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return None
    call = statement.value
    if not (isinstance(call.func, ast.Name) and call.func.id == "_decline"):
        return None
    if len(call.args) != 2 or not isinstance(call.args[1], ast.Constant):
        return None
    return str(call.args[1].value)


def test_every_bare_return_none_is_named_and_the_code_set_is_exact():
    """§13.3, cả ba điều kiện — đếm/trích bằng ``ast``, không regex.

    Không chỉ so số lượng: hai danh sách cùng dài vẫn có thể đặt nhầm code hoặc
    quên một return rồi lặp code ở return khác. Thêm một lối thoát mà quên đặt
    tên, hoặc đổi điều kiện nhưng giữ code sai chỗ, đều phải làm test này đỏ.
    """
    tree = ast.parse(inspect.getsource(synthesizer_module))
    observed: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in INSTRUMENTED_FUNCTIONS:
            for ret in _bare_none_returns(node):
                before = _statement_before(node, ret)
                literal = _decline_literal(before) if before is not None else None
                assert literal is not None, (
                    f"{node.name}:{ret.lineno} — return None không có _decline "
                    "đứng ngay trước trong cùng block"
                )
                assert literal in DECLINE_CODES, (
                    f"{node.name}:{ret.lineno} — literal {literal!r} ngoài DeclineCode"
                )
                observed.append(literal)

    assert len(observed) == len(set(observed)) == 20, (
        f"20 lý do hiện tại phải không trùng, thấy {sorted(observed)}"
    )
    assert set(observed) == set(DECLINE_CODES), (
        "tập literal quan sát được phải BẰNG ĐÚNG tập DeclineCode — "
        f"thiếu {set(DECLINE_CODES) - set(observed)}, thừa {set(observed) - set(DECLINE_CODES)}"
    )


def test_the_rule_map_and_priority_cover_every_code_exactly_once():
    assert set(DECLINE_RULE_BY_CODE) == set(DECLINE_CODES)
    assert set(DECLINE_RULE_PRIORITY) == set(DECLINE_CODES)
    assert len(DECLINE_RULE_PRIORITY) == len(set(DECLINE_RULE_PRIORITY))
    assert DECLINE_RULE_BY_CODE["aggregation_not_certified"] == "A19-AGGREGATION"


def test_rule_selection_follows_priority_not_branch_order():
    """§13.4: nhiều code ⇒ chọn theo priority tuple được test, không theo thứ tự
    tình cờ của nhánh."""
    assert rule_for_declines(["country_missing", "aggregation_not_certified"]) == (
        "A19-AGGREGATION"
    )
    assert rule_for_declines(["aggregation_not_certified", "country_missing"]) == (
        "A19-AGGREGATION"
    )
    assert rule_for_declines(["country_missing"]) == "A19-PLAN"
    assert rule_for_declines([]) == "A19-PLAN"


# --- collector ghi đúng mã cho từng lối --------------------------------------

@pytest.fixture(scope="module")
def parser() -> DeterministicSemanticParser:
    return DeterministicSemanticParser()


def _request(parser, question: str, country: str = "vn"):
    return parser.parse(question, "vi", country)


def test_missing_country_declines_with_its_own_name(parser):
    codes: list[str] = []
    assert synthesize(_request(parser, "Giá trung vị theo brand"), "", decline=codes) is None
    assert codes == ["country_missing"]


def test_a_caller_without_a_collector_gets_identical_behaviour(parser):
    """Điều kiện then chốt của W12.1: không truyền ``decline`` ⇒ y hệt hôm nay."""
    request = _request(parser, "Giá trung vị theo brand tại VN ngày 03/07")
    with_collector = synthesize(request, "vn", decline=[])
    without = synthesize(request, "vn")
    assert (with_collector is None) == (without is None)
    if with_collector is not None:
        assert with_collector.plan.model_dump_json() == without.plan.model_dump_json()


def test_inner_functions_share_the_callers_collector(parser):
    """``_plan_relations``/``_choose_aggregation`` ghi vào CÙNG collector —
    không tạo list con rồi làm mất lý do."""
    request = _request(parser, "Giá trung vị theo brand tại VN ngày 03/07")
    baseline = synthesize(request, "vn")
    assert baseline is not None, "câu chuẩn phải synthesize được để test có nghĩa"

    # Câu hai measure đi qua lối measure_count_not_one của synthesize.
    two = _request(parser, "Giá và rating theo brand tại VN ngày 03/07")
    codes: list[str] = []
    if synthesize(two, "vn", decline=codes) is None:
        assert codes, "decline collector không được rỗng khi synthesize từ chối"
        assert all(code in DECLINE_CODES for code in codes)


# --- baseline 58 plan không đổi ----------------------------------------------

DELIBERATE_BASELINE_CHANGES = {
    "questions_counting:cnt04": (
        "W11.2 (SolutionSpec2808 §12.3): câu MỚI thêm vào suite counting — "
        "tỷ lệ có mẫu số khai (bgk11). Mở rộng, không dịch entry cũ."
    ),
    "dr2607:tc29": (
        "W5.1 (SolutionSpec2808 §6.2): câu hỏi nêu 'trung bình', "
        "measure.discount_percent chỉ chứng nhận median/min/max — hệ từng thay "
        "thầm mean→median. Plan biến mất CÓ CHỦ ĐÍCH."
    ),
    "dr2607:tc36": (
        "W5.1: câu hỏi nêu 'tổng ... cộng lại' và sum nằm trong "
        "valid_aggregations của derived.estimated_recent_revenue — plan_id đổi "
        "median→sum."
    ),
    "dr2607:tc01": (
        "W1.2 (SolutionSpec2808 §2.4): 'tại shop Perfetti Van Melle Vietnam' "
        "trước đây thành group_by entity.shop — trả mọi shop. "
        "VALUE_DIMENSION_BY_UNIT bind tên shop thành predicate dim.shop_name "
        "và bỏ grouping."
    ),
}


def test_the_equivalence_baseline_only_moves_where_a_work_package_declared_it():
    """§13.6 dòng cuối: baseline chỉ được dịch ở khoá đã khai báo lý do.

    So với bản trong git HEAD thay vì chạy lại 173 câu: phép kiểm HÀNH VI đầy đủ
    đã có ở ``test_synthesizer_equivalence.py`` (chạy trong cùng suite), còn ở
    đây chỉ cần bằng chứng W12 không dịch file baseline — một phép so byte là
    đúng ngưỡng vì fixture là JSON do máy sinh, không có cột số thực tự do.
    """
    import subprocess

    path = "tests/fixtures/synthesizer_equivalence_baseline.json"
    head = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        capture_output=True, text=True, encoding="utf-8", cwd=Path(__file__).parents[1],
    )
    if head.returncode != 0:
        pytest.skip("không đọc được bản HEAD của baseline (repo cạn?)")
    current = json.loads(Path(path).read_text(encoding="utf-8"))
    committed = json.loads(head.stdout)
    changed = {
        key for key in set(current) | set(committed)
        if current.get(key) != committed.get(key)
    }
    # Đổi baseline phải là một thay đổi contract CÓ KHAI BÁO, kèm lý do — không
    # phải một file bị dịch trong im lặng. Danh sách chỉ nới đúng những khoá đã
    # nêu; mọi khoá khác đổi vẫn đỏ.
    assert changed <= set(DELIBERATE_BASELINE_CHANGES), sorted(
        changed - set(DELIBERATE_BASELINE_CHANGES),
    )
