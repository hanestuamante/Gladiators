"""Đối chứng "để model tự viết SQL" — Spec2308 §WP-B5.

Test ở đây kiểm **bộ máy đo**, không kiểm model: phép đo thật cần một provider
và một khoá API. Điều phải chắc chắn trước khi con số nào được công bố là bộ máy
phân loại đúng — đặc biệt là ô ``wrong_value_silent``, vốn là toàn bộ luận điểm.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_sql_baseline import (  # noqa: E402
    SYNTAX_RETRIES,
    _sql_from,
    classify,
    raw_schema,
    run_one,
)


class _Executor:
    """Chỉ đủ hình dạng mà ``run_one`` chạm tới."""

    def __init__(self, frame=None, error: Exception | None = None):
        self._frame, self._error = frame, error
        self.connection = self

    def execute(self, sql):
        if self._error is not None:
            raise self._error
        return self

    def fetchdf(self):
        return self._frame


class _Client:
    def __init__(self, *replies: str):
        self.replies, self.prompts = list(replies), []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.replies[min(len(self.prompts), len(self.replies)) - 1]


CASE = {"id": "c1", "question": "Có bao nhiêu listing tại VN?",
        "expected_value": {"listing_count": 668}}


def test_a_right_number_is_correct():
    assert classify(pd.DataFrame({"n": [668]}), CASE) == "correct"


def test_a_wrong_number_returned_without_any_signal_is_the_dangerous_class():
    """Đây là ô ăn tiền của cả bảng: một con số SAI trả về mà KHÔNG có tín hiệu
    nào cho biết nó sai. Nó khác hẳn crashed — một lỗi nhìn thấy được là một lỗi
    sửa được."""
    assert classify(pd.DataFrame({"n": [551]}), CASE) == "wrong_value_silent"


def test_an_empty_result_counts_as_a_refusal_not_a_wrong_answer():
    assert classify(pd.DataFrame({"n": []}), CASE) == "refused"
    assert classify(None, CASE) == "refused"


def test_the_schema_given_to_the_baseline_is_raw():
    """Đưa catalog vào là đo lại hệ Gladiators dưới một cái tên khác."""
    schema = raw_schema()
    assert "products(" in schema
    # Không semantic ref, không invariant: baseline chỉ được thấy cột vật lý.
    assert "measure." not in schema
    assert "INV-" not in schema


def test_sql_is_extracted_from_a_fenced_reply():
    assert _sql_from("```sql\nSELECT 1\n```") == "SELECT 1"
    assert _sql_from("SELECT 1;") == "SELECT 1"


def test_a_syntax_error_gets_exactly_one_retry_with_the_error_attached():
    """Cho baseline điều kiện tốt nhất hợp lý — một đối chứng bị dìm là một đối
    chứng vô giá trị, và người đọc nhận ra điều đó ngay."""
    client = _Client("SELECT nonsense")
    executor = _Executor(error=RuntimeError("Parser Error"))
    row = run_one(CASE, client, "schema", executor)

    assert row["outcome"] == "crashed"
    assert len(client.prompts) == SYNTAX_RETRIES + 1
    assert "Lần trước lỗi" in client.prompts[-1]


def test_a_write_statement_is_refused_before_it_reaches_the_database():
    """B5-R2. Phòng vệ chiều sâu không được nới ra chỉ vì đây là một script đo."""
    client = _Client("DELETE FROM products_clean")
    executor = _Executor(frame=pd.DataFrame({"n": [668]}))
    row = run_one(CASE, client, "schema", executor)
    assert row["outcome"] == "crashed"
    assert row["error"]


def test_the_baseline_never_touches_the_agent_runtime():
    """B5-R1. Bất biến "không mở raw-SQL path ở runtime" giữ nguyên."""
    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "run_sql_baseline.py"
    ).read_text(encoding="utf-8")
    # Kiểm phần MÃ, không kiểm docstring: docstring nhắc tới /ask để nói rằng nó
    # KHÔNG nối vào đó, và một phép grep thô sẽ đọc lời cam kết thành vi phạm.
    code = chr(10).join(
        line for line in source.splitlines()
        if not line.lstrip().startswith(("#", "*", "1.", "2.", "3."))
    )
    assert "AgentRuntime(" not in code
    assert "import AgentRuntime" not in code
    # Cũng không được thêm một cửa raw-SQL vào lớp production.
    executor_source = (
        Path(__file__).resolve().parents[1]
        / "src" / "gladiators" / "planner" / "executor.py"
    ).read_text(encoding="utf-8")
    assert "def execute_sql" not in executor_source
