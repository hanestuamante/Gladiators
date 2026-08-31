"""Hai thứ mà bộ dữ liệu mới làm lộ ra, và cả hai đều là "guard chưa từng chạy".

1. **Artifact tuỳ chọn.** ``shop_stats_clean.csv`` chỉ có từ lần thu 07/2026.
   Bắt buộc nó ⇒ một bản dữ liệu cũ ĐÚNG bị chấm là hỏng. Nhét panel vào
   ``shop_info`` ⇒ grain của chín measure ``static_latest`` đổi âm thầm.

2. **Cận số dòng.** ``max_result_rows`` từng so với cardinality LỚN NHẤT ở node
   bất kỳ, tức cả lần quét bảng gốc. Trên 3 341 dòng nó không bao giờ bắn; trên
   22 695 dòng nó chặn MỌI truy vấn kể cả truy vấn trả về một dòng. Guard chỉ
   được thử khi dữ liệu lớn lên — và lúc đó mới thấy nó đo nhầm đại lượng.
"""
from __future__ import annotations

import pytest

from gladiators.data.repository import ArtifactRepository
from gladiators.domain.tables import (
    OPTIONAL_ARTIFACTS,
    REQUIRED_ARTIFACT_NAMES,
    ArtifactName,
)
from gladiators.planner.analytical import build_analytical_plan
from gladiators.planner.compiler import CompilationError, compile_plan
from gladiators.domain.calendar import load_calendar
from gladiators.planner.executor import ExecutionFailure, QueryExecutor, _declared_cardinality
from conftest import DATA_DIR


@pytest.fixture(scope="module")
def repo():
    return ArtifactRepository()


@pytest.fixture(scope="module")
def executor(repo):
    ex = QueryExecutor(repo)
    yield ex
    ex.close()


# --- artifact tuỳ chọn ------------------------------------------------------


def test_the_optional_tier_is_narrow_and_named():
    assert OPTIONAL_ARTIFACTS == frozenset({ArtifactName.SHOP_STATS})
    assert set(REQUIRED_ARTIFACT_NAMES) == {
        name.value for name in ArtifactName if name not in OPTIONAL_ARTIFACTS
    }


def test_the_frozen_dataset_reports_the_optional_artifact_as_absent(repo):
    """Bản đóng băng KHÔNG có panel shop, và điều đó phải đọc được — chứ không
    phải hiện ra như một bảng đã thu mà rỗng dòng."""
    available = set(repo.available_artifacts())
    assert set(REQUIRED_ARTIFACT_NAMES) <= available
    assert not repo.has_artifact(ArtifactName.SHOP_STATS.value)


def test_no_view_is_registered_for_an_uncollected_artifact(repo, executor):
    """Đăng ký một frame RỖNG thay thế sẽ khiến mọi truy vấn lên nó trả "0 dòng"
    — tức "đo được và không có gì", đúng thứ CLAUDE.md §3.1 cấm."""
    assert ArtifactName.SHOP_STATS.value not in executor.available_artifacts
    with pytest.raises(Exception):
        executor.connection.execute("SELECT 1 FROM shop_stats").fetchone()


def test_compiling_against_an_uncollected_source_fails_with_a_data_reason(repo):
    """Để plan đi tiếp thì DuckDB báo "table không tồn tại" — một lỗi hạ tầng,
    trong khi sự thật là một giới hạn dữ liệu. Hai thứ đó phải nói khác nhau."""
    plan = build_analytical_plan("listing_count", "vn")
    node = plan.nodes[0]
    broken = plan.model_copy(update={
        "nodes": (node.model_copy(update={"source": ArtifactName.SHOP_STATS.value}),)
        + tuple(plan.nodes[1:]),
    })
    with pytest.raises(CompilationError, match="chưa thu"):
        compile_plan(broken, available_sources=frozenset(repo.available_artifacts()))


def test_compiling_without_declared_availability_still_works(repo):
    """``available_sources=None`` = không kiểm — giữ nguyên mọi caller cũ, kể cả
    test dựng plan trần không có repository nào."""
    assert compile_plan(build_analytical_plan("listing_count", "vn")).sql


# --- cận số dòng ------------------------------------------------------------


def test_a_small_result_over_a_large_scan_is_not_blocked(executor, repo):
    """Hồi quy cho đúng lỗi bộ dữ liệu mới làm lộ: "listing nào giá cao nhất"
    quét cả bảng nhưng trả MỘT dòng. Guard cũ so cận với 3 341 (lần quét) chứ
    không phải 2 (kết quả), nên trên bảng lớn hơn nó chặn nhầm."""
    compiled = compile_plan(build_analytical_plan("highest_price_listing", "vn"))
    result, widest = executor._estimated_rows(compiled.sql, compiled.parameters)
    assert widest is not None and widest > result, (
        "cần một plan mà lần quét rộng hơn kết quả thì test này mới có nghĩa"
    )
    assert executor.execute(compiled).row_count >= 1


def test_an_ungrouped_aggregate_is_bounded_by_its_own_contract(executor):
    """DuckDB ước tính node aggregate bằng cardinality ĐẦU VÀO. Plan thì tự khai
    ``expected_cardinality='1'``, và postcondition kiểm lại nó SAU khi chạy —
    nên tin hợp đồng của plan là tin một thứ có người chấm."""
    compiled = compile_plan(build_analytical_plan("listing_count", "vn"))
    assert compiled.expected_cardinality == "1"
    _, widest = executor._estimated_rows(compiled.sql, compiled.parameters)
    assert widest is not None and widest > executor.max_result_rows / 10
    assert executor.execute(compiled).row_count == 1


def test_the_result_cap_still_fires_when_the_plan_claims_too_many(executor):
    """Nới guard KHÔNG được thành gỡ guard: plan tự khai một cận quá lớn thì
    vẫn phải bị chặn trước khi chạy."""
    compiled = compile_plan(build_analytical_plan("listing_count", "vn"))
    greedy = compiled.__class__(
        **{**vars(compiled), "expected_cardinality": f"<={executor.max_result_rows + 1}"},
    )
    with pytest.raises(ExecutionFailure, match="giới hạn số dòng"):
        executor.execute(greedy)


def test_the_fanout_cap_is_relative_to_this_dataset(executor, repo):
    """Một hằng số tuyệt đối lại đúng ở bộ 3 341 dòng và sai ở bộ 22 695 dòng —
    đúng cách guard cũ hỏng. Ngưỡng phải bám bảng lớn nhất của chính bản này."""
    largest = max(len(repo.read(name)) for name in executor.available_artifacts)
    assert executor.max_intermediate_rows == max(
        largest * QueryExecutor.FANOUT_ALLOWANCE, executor.max_result_rows,
    )
    assert executor.max_intermediate_rows > largest


def test_a_plan_that_blows_up_intermediates_is_refused(repo):
    """Cận fanout phải BẮN được, nếu không nó chỉ là một thuộc tính trang trí."""
    tiny = QueryExecutor(repo, max_intermediate_rows=1)
    try:
        compiled = compile_plan(build_analytical_plan("highest_price_listing", "vn"))
        with pytest.raises(ExecutionFailure, match="dòng trung gian"):
            tiny.execute(compiled)
    finally:
        tiny.close()


SNAPSHOT_ROWS = load_calendar(DATA_DIR).row_count


@pytest.mark.parametrize(("declared", "expected"), [
    ("1", (1, False)), ("<=50", (50, False)), ("<= 3341", (3341, False)),
    ("2", (2, False)),
    ("", (None, False)), (None, (None, False)), ("nhiều", (None, False)),
    ("<=abc", (None, False)),
    # Cận KÝ HIỆU mang cờ True: nó nói về cỡ BẢN DỮ LIỆU, không về cỡ kết quả.
    # Thiếu phân biệt này, cửa `max_result_rows` bắn theo số dòng của dataset —
    # cùng một truy vấn lọt trên bộ 3 ngày và bị chặn trên bộ 20 ngày dù kết quả
    # y hệt 4 113 dòng ở cả hai.
    ("<=snapshot_rows", (SNAPSHOT_ROWS, True)),
])
def test_declared_cardinality_parsing(declared, expected):
    assert _declared_cardinality(declared) == expected
