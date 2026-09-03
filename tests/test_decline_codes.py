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

    # 20 → 21 ở W18: `relation_grain_invalid` tách khỏi `relation_plan_failed`.
    # Bộ chọn quan hệ BỎ CUỘC và bộ chọn quan hệ DỰNG RA MỘT CẠNH KHÔNG HỢP LỆ
    # là hai nguyên nhân khác nhau, và gộp chúng vào một mã làm trace nói rằng
    # chúng giống nhau.
    assert len(observed) == len(set(observed)) == 23, (
        f"23 lý do hiện tại phải không trùng, thấy {sorted(observed)}"
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
    # W8.3: sáu câu voucher — plan cũ tồn tại nhờ alias trần được chọn THẦM
    # nghĩa structured; xem INTENTIONALLY_LOST ở test_synthesizer_equivalence.
    'questions:q28': 'W8.3 voucher ambiguity',
    'questions:q29': 'W8.3 voucher ambiguity',
    'questions:q32': 'W8.3 voucher ambiguity',
    'questions:q60': 'W8.3 voucher ambiguity',
    'questions_v2:v2q10': 'W8.3 voucher ambiguity',
    'questions_v2:v2q11': 'W8.3 voucher ambiguity',
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
    "semantic_linking:sl37": (
        "W24 (Spec3008 §11): ca MỚI thêm vào suite semantic_linking — catalog "
        "trước đây KHÔNG có object nào phơi `products_clean.csv.item_id`, nên "
        "không plan nào lọc được về một listing cụ thể và mọi câu nêu mã sản "
        "phẩm bị `_has_unbound_qualifier` từ chối. Mở rộng, không dịch entry "
        "cũ. Đã đối chiếu với pandas trước khi thêm: mã 2260506115 tại vn ngày "
        "03/07 có giá 372537.0, và hệ trả đúng con số đó."
    ),
    "dr2607:tc32": (
        "W18 (Spec3008 §5): plan MẤT có chủ đích — 'Shop mỹ phẩm Glad2Glow' "
        "bind được `dim.brand = GLAD2GLOW`, nhưng ref đó không nằm trên bảng "
        "nguồn nên bộ chọn quan hệ thêm một cạnh registry không khai và plan ra "
        "`grain_mismatch` + `fanout_risk`. Bộ sinh không được trả về một plan "
        "nó tự biết là hỏng. Runtime KHÔNG đổi: vẫn `abstain / A-MISSING-ADS`, "
        "đúng kỳ vọng fixture. Lý do đầy đủ ở INTENTIONALLY_LOST."
    ),
    "dr2607:tc08": (
        "W18 + W25: câu nêu đích danh 'bánh quy Kinh Đô' nên `dim.brand` bind "
        "được và plan hẹp lại từ 10 xuống 2 dòng — một điều kiện bị bỏ rơi làm "
        "hệ trả một con số RỘNG HƠN câu hỏi. Cùng lúc `entity.shop` rời grouping "
        "vì nó không còn là chiều gom nhóm. Runtime KHÔNG đổi: vẫn "
        "`clarify / A-AMBIGUOUS`, đúng kỳ vọng fixture."
    ),
    "dr2607:tc01": (
        "W1.2 (SolutionSpec2808 §2.4): 'tại shop Perfetti Van Melle Vietnam' "
        "trước đây thành group_by entity.shop — trả mọi shop. "
        "VALUE_DIMENSION_BY_UNIT bind tên shop thành predicate dim.shop_name "
        "và bỏ grouping. "
        "W25-R3 (Spec3008 §12): dim.shop_name nay CÓ cột trên products_clean, "
        "nên bộ lọc theo tên shop không cần cạnh belongs_to nữa — node Join "
        "thành Project. Đã chạy CẢ HAI plan trên dữ liệu thật trước khi sửa "
        "fixture: 22 dòng, cùng giá trị (4.0 / 95.0 / 104.0 …). Rút gọn thuần, "
        "không đổi kết quả."
    ),
}


def _predicate_sets(plan):
    return [
        {tuple(sorted(pred.items())) for pred in node.get("predicates", [])}
        for node in plan.get("nodes", [])
    ]


def _strip_predicates(node):
    if isinstance(node, dict):
        return {k: _strip_predicates(v) for k, v in node.items() if k != "predicates"}
    if isinstance(node, list):
        return [_strip_predicates(x) for x in node]
    return node


def _only_filters_added(current, committed) -> bool:
    """True khi plan mới GIỐNG HỆT plan cũ, chỉ THÊM predicate — không bớt.

    W18 bind được những giá trị mà câu hỏi NÊU ĐÍCH DANH (brand, tên shop) và
    trước đây rơi mất. Kết quả là plan HẸP HƠN, đúng hướng: một điều kiện bị bỏ
    rơi làm hệ trả một con số RỘNG HƠN câu hỏi, và không lớp nào phía sau phát
    hiện được. Lớp này chỉ miễn khi diff nằm gọn trong việc THÊM predicate — bớt
    một predicate là đi ngược, và vẫn phải đỏ.
    """
    if not isinstance(current, dict) or not isinstance(committed, dict):
        return False
    if _strip_predicates(current) != _strip_predicates(committed):
        return False
    new_sets, old_sets = _predicate_sets(current), _predicate_sets(committed)
    return len(new_sets) == len(old_sets) and all(
        old <= new for new, old in zip(new_sets, old_sets)
    )


def _strip_labels(node):
    """Bỏ TÊN CỘT của các field chiếu một đơn vị phân tích.

    W25 đổi tên chiếu từ khoá (``shop_id``) sang nhãn (``shop_name``) — cùng
    ``semantic_ref``, cùng kiểu, chỉ khác nhãn hiển thị. Bỏ đúng trường ``name``
    của đúng những field đó, giữ nguyên mọi thứ khác.
    """
    from gladiators.domain.catalog import LABEL_REF_BY_UNIT

    if isinstance(node, dict):
        if node.get("semantic_ref") in LABEL_REF_BY_UNIT and "name" in node:
            node = {k: v for k, v in node.items() if k != "name"}
        return {k: _strip_labels(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_strip_labels(x) for x in node]
    return node


def _only_labels_moved(current, committed) -> bool:
    if not isinstance(current, dict) or not isinstance(committed, dict):
        return False
    return _strip_labels(current) == _strip_labels(committed)


def _strip_cardinality(node):
    if isinstance(node, dict):
        return {k: _strip_cardinality(v) for k, v in node.items()
                if k not in ("expected_cardinality", "original_cardinality")}
    if isinstance(node, list):
        return [_strip_cardinality(x) for x in node]
    return node


def _only_cardinality_moved(current, committed) -> bool:
    """True khi hai plan giống hệt nhau sau khi bỏ đúng hai khoá cardinality."""
    if not isinstance(current, dict) or not isinstance(committed, dict):
        return False
    return _strip_cardinality(current) == _strip_cardinality(committed)



def _only_declared_aggregation_moved(current, committed) -> bool:
    """True khi hai plan chỉ khác ở Ô PHÉP TỔNG HỢP của ``plan_id``, và ô đó
    chuyển từ một phép CÓ TÊN sang ``noagg``.

    `plan_id` từng ghi phép mà `_choose_aggregation` ĐỀ XUẤT, chứ không phải
    phép plan THỰC HIỆN. 36 plan (35 `median`, 1 `count`) khai một phép tổng
    hợp trong khi chuỗi node của chúng KHÔNG có node Aggregate nào — nghĩa là
    mọi thứ đọc plan_id (telemetry, khoá cache, người đọc trace) tin vào một
    phép tính chưa bao giờ chạy, và hai plan khác nhau về cấu trúc dùng chung
    một khoá.

    Lớp này TỰ CHỨNG MINH như ba lớp trên: chỉ miễn khi đúng một ô đổi, và chỉ
    theo chiều `<phép> → noagg`. Chiều ngược lại (bịa thêm một phép) vẫn đỏ.
    """
    if not isinstance(current, dict) or not isinstance(committed, dict):
        return False
    if {k for k in set(current) | set(committed)
            if current.get(k) != committed.get(k)} != {"plan_id"}:
        return False
    new = str(current["plan_id"]).split(":")
    old = str(committed["plan_id"]).split(":")
    if len(new) != len(old) or new[2] != "noagg" or old[2] == "noagg":
        return False
    return new[:2] + new[3:] == old[:2] + old[3:]


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
    # W30 (Spec3008 §17, LUẬT W30-R5) dịch ``expected_cardinality`` của 52 plan
    # từ một CON SỐ của một bản dữ liệu sang một KÝ HIỆU trên lịch snapshot.
    # Khai nó thành một LỚP thay vì 52 dòng giống hệt nhau — nhưng lớp đó phải
    # tự CHỨNG MINH: một khoá chỉ được miễn khi diff của nó nằm gọn trong hai
    # khoá cardinality. Khai bằng tên mà không kiểm là mở một cửa cho mọi thay
    # đổi khác đi kèm.
    changed = {
        key for key in changed
        if not _only_cardinality_moved(current.get(key), committed.get(key))
    }
    # W25 (Spec3008 §12): tên cột chiếu đổi từ KHOÁ sang NHÃN. Cùng khuôn với
    # lớp trên — khai bằng tên mà không kiểm là mở cửa cho mọi thay đổi khác đi
    # kèm, nên lớp này cũng tự chứng minh.
    changed = {
        key for key in changed
        if not _only_labels_moved(current.get(key), committed.get(key))
    }
    # W18 (Spec3008 §5): giá trị mà câu hỏi nêu đích danh nay bind được, nên
    # plan HẸP HƠN. Cùng khuôn hai lớp trên — lớp này cũng tự chứng minh, và nó
    # chỉ miễn chiều THÊM predicate.
    changed = {
        key for key in changed
        if not _only_filters_added(current.get(key), committed.get(key))
    }
    # `plan_id` thôi khai phép tổng hợp mà plan KHÔNG thực hiện. Cùng khuôn ba
    # lớp trên: tự chứng minh, và chỉ theo chiều `<phép> → noagg`.
    changed = {
        key for key in changed
        if not _only_declared_aggregation_moved(
            current.get(key), committed.get(key),
        )
    }
    # Câu TRƯỚC ĐÂY không có plan mà NAY có là mở rộng hợp lệ — chính mục tiêu
    # của W17/W24/W26, và ``test_synthesizer_equivalence`` đã khai nguyên tắc
    # đó. Chiều ngược lại (mất plan) KHÔNG được miễn ở đây: nó phải đi qua
    # ``INTENTIONALLY_LOST`` kèm lý do.
    changed = {
        key for key in changed
        if not (
            isinstance(current.get(key), dict)
            and not isinstance(committed.get(key), dict)
        )
    }
    # Đổi baseline phải là một thay đổi contract CÓ KHAI BÁO, kèm lý do — không
    # phải một file bị dịch trong im lặng. Danh sách chỉ nới đúng những khoá đã
    # nêu; mọi khoá khác đổi vẫn đỏ.
    assert changed <= set(DELIBERATE_BASELINE_CHANGES), sorted(
        changed - set(DELIBERATE_BASELINE_CHANGES),
    )
