"""Vị trí xếp hạng ("thứ 2") là một phần của câu hỏi.

Trước work package này `AnalyticalRanking` chỉ biết `top_k` — "bao nhiêu dòng"
— và không có chỗ nào để giữ "bắt đầu từ dòng thứ mấy". Cụm "thứ 2" rơi khỏi
câu hỏi mà không lớp kiểm nào thấy: plan hợp lệ, gate cho phép, verifier thấy
con số có evidence, và câu trả lời khẳng định shop hạng NHẤT là shop hạng nhì.

Ground truth tính bằng pandas thuần trên ĐÚNG bản mà bộ kiểm này nói về
(`conftest.DATA_DIR`, bộ đóng băng 3 ngày) chứ không phải trên bản đang phục
vụ — xem docstring của `conftest.py`: hai thứ đó trùng nhau cho tới ngày đổi
bản, và một phép kiểm không nói rõ nó nói về cái gì thì không phải phép kiểm.
Bảng thứ hạng vì thế được TÍNH LẠI trong `_shop_counts()`, không viết cứng.
"""
from __future__ import annotations

import pandas as pd
import pytest
from conftest import DATA_DIR

from gladiators.agent.workflow import AgentRuntime, _number_in_words, _rank_position_word
from gladiators.planner.compiler import CompiledQuery, compile_plan
from gladiators.planner.executor import QueryExecutor
from gladiators.planner.semantic_parser import (
    DeterministicSemanticParser,
    _requested_rank_offset,
    normalize,
)
from gladiators.planner.synthesizer import synthesize


@pytest.fixture(scope="module")
def runtime() -> AgentRuntime:
    return AgentRuntime()


def _result_line(response) -> str:
    lines = [line for line in response.answer.splitlines()
             if line.strip() and "Kết quả" not in line]
    return lines[0] if lines else ""


# ── Đọc vị trí ra khỏi câu hỏi ────────────────────────────────────────────

@pytest.mark.parametrize(("question", "offset"), [
    ("Shop nào có nhiều listing thứ 2 tại VN?", 1),
    ("Shop nào có nhiều listing thứ ba tại VN?", 2),
    ("Sản phẩm giá cao thứ nhì tại VN", 1),
    ("shop xếp thứ 5 về doanh số", 4),
    ("shop xếp hạng 3 về doanh số", 2),
    ("toko dengan listing terbanyak ke-2 di ID", 1),
    # Không nêu vị trí ⇒ hành vi cũ, không đổi một byte.
    ("Shop nào có nhiều listing nhất tại VN?", 0),
    ("Ngày nào doanh thu cao nhất tại VN?", 0),
])
def test_reads_the_asked_position(question: str, offset: int) -> None:
    assert _requested_rank_offset(normalize(question)) == offset


@pytest.mark.parametrize("question", [
    # "thứ hai" là một THỨ TRONG TUẦN khi đứng sau "ngày" — cùng chữ, khác
    # nghĩa, và chỗ duy nhất phân biệt được là từ ngay trước nó.
    "ngày thứ hai có bao nhiêu listing",
    "vào thứ 2 có bao nhiêu listing",
    # "doanh thu" chứa "thu"; không rào thì "doanh thu 2 ngày" thành hạng nhì.
    "doanh thu 2 ngày gần nhất tại VN",
    # Danh từ phổ biến của chính miền dữ liệu này đội lốt số thứ tự sau khi bỏ
    # dấu: "cửa hàng Nam" → "hang nam", "hàng năm" → "hang nam".
    "cửa hàng Nam có bao nhiêu listing",
    "doanh thu hàng năm của shop",
    "kệ hàng 3 tầng giá bao nhiêu",
    # "liệt kê" đã là marker số-nhiều; đọc thêm thành "hạng năm" thì một cụm
    # vừa xin năm dòng vừa xin dòng thứ năm.
    "liệt kê 5 shop có nhiều listing nhất",
])
def test_a_common_noun_is_not_a_rank(question: str) -> None:
    assert _requested_rank_offset(normalize(question)) == 0


# ── Plan phải mang vị trí, và plan cũ không được đổi ──────────────────────

def test_plan_carries_the_position() -> None:
    request = DeterministicSemanticParser().parse(
        "Shop nào có nhiều listing thứ 2 tại VN?", "vi", "vn",
    )
    assert request.ranking is not None and request.ranking.offset == 1
    plan = synthesize(request, "vn").plan
    rank = next(node for node in plan.nodes if node.op == "Rank")
    assert rank.rank_offset == 1
    # PLAN_ID phải mô tả đúng chính nó: hai plan cắt ở hai vị trí khác nhau mà
    # mang cùng một id là hai thứ khác nhau đội một tên — và id này là khoá
    # cache thực thi, nên trùng tên nghĩa là trả kết quả của câu hỏi kia.
    assert "desc#2" in plan.plan_id


def test_a_plan_without_a_position_is_byte_identical() -> None:
    """Bất biến #7: thêm trường không được đổi dump của plan đã khoá."""
    request = DeterministicSemanticParser().parse(
        "Shop nào có nhiều listing nhất tại VN?", "vi", "vn",
    )
    plan = synthesize(request, "vn").plan
    rank = next(node for node in plan.nodes if node.op == "Rank")
    assert rank.rank_offset == 0
    assert "rank_offset" not in rank.model_dump()
    assert ":desc:" in plan.plan_id and "#" not in plan.plan_id


def test_the_compiler_fetches_past_both_edges() -> None:
    """Lát cắt của "thứ 2" có HAI biên, và cả hai chỉ nhìn được khi hàng xóm
    của chúng còn trong frame — nên SQL vẫn lấy từ dòng đầu."""
    request = DeterministicSemanticParser().parse(
        "Shop nào có nhiều listing thứ 3 tại VN?", "vi", "vn",
    )
    compiled = compile_plan(synthesize(request, "vn").plan)
    assert (compiled.rank_offset, compiled.rank_limit) == (2, 1)
    assert "OFFSET" not in compiled.sql.upper()
    assert "LIMIT 4" in compiled.sql.upper()


# ── Câu trả lời phải nêu đúng vị trí, bằng chữ ───────────────────────────

@pytest.mark.parametrize(("position", "word"), [
    (1, "nhất"), (2, "thứ hai"), (4, "thứ tư"), (10, "thứ mười"),
    (11, "thứ mười một"), (14, "thứ mười bốn"), (15, "thứ mười lăm"),
    (21, "thứ hai mươi mốt"), (24, "thứ hai mươi tư"), (25, "thứ hai mươi lăm"),
])
def test_the_position_is_spelled_out(position: int, word: str) -> None:
    """Bằng CHỮ, không bằng chữ số: `verifier.scan_numbers` đòi evidence cho mọi
    chữ số trong câu trả lời, và "thứ 2" là một chữ số không evidence nào đỡ."""
    assert _rank_position_word({"offset": position - 1}) == word


def test_no_digit_leaks_into_the_position_phrase() -> None:
    for offset in range(0, 99):
        assert not any(ch.isdigit() for ch in _rank_position_word({"offset": offset}))


def test_number_words_do_not_collide() -> None:
    """Cách đọc thứ tự khác cách đọc số lượng ở đúng ba chỗ; một bảng sai ba
    chỗ vẫn là ba câu trả lời sai."""
    assert _number_in_words(4) == "tư"
    assert _number_in_words(14) == "mười bốn"
    assert _number_in_words(24) == "hai mươi tư"


# ── Chạy thật, đối chiếu pandas ──────────────────────────────────────────

def _shop_counts() -> pd.Series:
    """Số listing theo shop ở snapshot MỚI NHẤT của thị trường VN.

    Ngày lấy từ dữ liệu, không viết cứng: hệ mặc định trả lời ở snapshot mới
    nhất, và một ngày viết cứng biến bộ đề thành phép kiểm về một ngày cụ thể
    thay vì về thứ hạng.
    """
    snapshots = pd.read_csv(f"{DATA_DIR}/product_snapshot_metrics.csv")
    shops = pd.read_csv(f"{DATA_DIR}/shop_info_clean.csv")
    names = shops[shops.country_code == "vn"].drop_duplicates("shop_id")
    market = snapshots[snapshots.country_code == "vn"]
    day = market[market.date == market.date.max()]
    counts = day.groupby("shop_id")["product_listing_key"].nunique()
    return counts.rename(index=names.set_index("shop_id")["shop_name"]).sort_values(
        ascending=False, kind="mergesort",
    )


@pytest.mark.parametrize("position", [1, 2, 3])
def test_the_named_shop_is_the_one_at_that_position(runtime, position: int) -> None:
    truth = _shop_counts()
    name, count = truth.index[position - 1], truth.iloc[position - 1]
    ordinal = "nhất" if position == 1 else f"thứ {position}"
    response = runtime.run(f"Shop nào có nhiều listing {ordinal} tại VN?")

    assert response.gate.action == "allow"
    line = _result_line(response)
    assert name in line
    assert f"{count:g} listing" in line
    assert _rank_position_word({"offset": position - 1}) in line


def test_the_ascending_position_reads_from_the_other_end(runtime) -> None:
    truth = _shop_counts()
    name, count = truth.index[-2], truth.iloc[-2]
    response = runtime.run("Shop nào có ít listing thứ 2 tại VN?")
    line = _result_line(response)
    assert response.gate.action == "allow"
    assert name in line and f"{count:g} listing" in line


def test_a_position_past_the_end_says_so(runtime) -> None:
    """Lý do phải ĐÚNG, không chỉ kết luận. Trả rỗng vì hết hạng không phải trả
    rỗng vì phép lọc ngày không khớp dòng nào — một lý do sai dẫn người dùng đi
    sửa đúng thứ không hỏng."""
    response = runtime.run("Shop nào có nhiều listing thứ 15 tại VN?")
    line = _result_line(response)
    assert "thứ mười lăm" in line
    assert "không có tới hạng" in line
    # Con số phải ở lại: evidence rỗng mang giá trị 0, và không claim nào trỏ
    # vào nó thì cả lượt rơi A-VERIFICATION-FINAL.
    assert response.verification["passed"] is True


def test_a_position_never_silently_becomes_the_top(runtime) -> None:
    """Phép kiểm quan trọng nhất của cả file: câu trả lời cho một vị trí KHÁC
    phải khác câu trả lời cho hạng nhất."""
    top = _result_line(runtime.run("Shop nào có nhiều listing nhất tại VN?"))
    second = _result_line(runtime.run("Shop nào có nhiều listing thứ 2 tại VN?"))
    assert top != second
    assert _shop_counts().index[0] not in second


# ── Hoà ở BIÊN TRÊN cũng làm vị trí không xác định ────────────────────────

class _NoArtifacts:
    def available_artifacts(self):
        return ()

    def read(self, artifact):                      # pragma: no cover - không gọi
        raise AssertionError("bộ đề này không đọc artifact nào")


def _values_query(rows: str, *, offset: int) -> CompiledQuery:
    return CompiledQuery(
        sql=f"SELECT * FROM (VALUES {rows}) AS t(g, v) ORDER BY v DESC LIMIT 99",
        parameters=(), plan_hash="test", expected_columns=("g", "v"),
        postconditions=(), expected_cardinality="<=99", ordered=True,
        rank_column="v", rank_limit=1, rank_offset=offset,
    )


@pytest.mark.parametrize(("rows", "offset", "tied"), [
    # 5 5 4 — hạng nhất hoà, nên "thứ 2" vừa là shop hoà kia vừa là shop đứng
    # sau cả hai. Dữ liệu không phân định, và chọn một là trả lời tuỳ tiện.
    ("(1, 5), (2, 5), (3, 4)", 1, True),
    # Cùng dữ liệu, hỏi hạng NHẤT: hoà ở biên dưới — phép kiểm cũ đã bắt.
    ("(1, 5), (2, 5), (3, 4)", 0, True),
    # 6 5 4 — không hoà ở biên nào, "thứ 2" xác định.
    ("(1, 6), (2, 5), (3, 4)", 1, False),
    # 6 5 5 — hoà ở dưới lát cắt của "thứ 2".
    ("(1, 6), (2, 5), (3, 5)", 1, True),
])
def test_a_tie_at_either_edge_makes_the_position_undetermined(
    rows: str, offset: int, tied: bool,
) -> None:
    executor = QueryExecutor(_NoArtifacts())
    result = executor.execute(_values_query(rows, offset=offset))
    assert result.rank_tie_at_cut is tied
    assert len(result.frame) == 1
