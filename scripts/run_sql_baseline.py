#!/usr/bin/env python3
"""Đối chứng "để model tự viết SQL" — Spec2308 §WP-B5.

    PYTHONPATH=src .venv/Scripts/python.exe scripts/run_sql_baseline.py \\
      --suite eval/independent/answerable_manual.json --provider deepseek

Trả lời câu *"phức tạp vậy để làm gì, sao không để LLM viết SQL?"* bằng **một
phép đo chạy trên chính bộ đề đó**, thay vì bằng lập luận.

**B5-R1 — script này KHÔNG nối vào ``/ask`` và KHÔNG nối vào ``AgentRuntime``.**
Bất biến "không mở raw-SQL path ở runtime" giữ nguyên: đây là một chế độ đo, chạy
tay, và cái nó đo là *một hệ thống khác* chứ không phải một chế độ của hệ này.

Ba luật để phép đối chứng công bằng — thiếu một luật thì nó phản tác dụng:

1. **Cho baseline điều kiện tốt nhất hợp lý**: cùng model, cùng mô tả cột, và
   cho thử lại một lần khi SQL lỗi cú pháp. Một đối chứng bị dìm là một đối chứng
   vô giá trị — và người đọc nhận ra điều đó ngay.
2. **Chấm bằng CÙNG MỘT oracle** cho cả hai phía.
3. **Công bố cả chỗ baseline thắng.** Gần như chắc chắn nó nhanh hơn và trả lời
   nhiều câu hơn. Nói ra điều đó **làm mạnh** luận điểm, vì nó cho thấy nhóm hiểu
   mình đã đánh đổi cái gì để lấy cái gì.
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import date
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]

# Số lần cho thử lại khi SQL sai cú pháp. Đúng MỘT, và lần thử lại được kèm
# thông báo lỗi — đó là điều kiện công bằng, không phải sự rộng lượng.
SYNTAX_RETRIES = 1


def raw_schema() -> str:
    """Lược đồ **THÔ**: tên bảng, tên cột, kiểu. Không catalog, không invariant.

    Đây chính là điều đang được đo. Đưa catalog vào là đo lại hệ Gladiators dưới
    một cái tên khác; giữ nó thô là đo đúng thứ câu hỏi đối chứng nói tới.
    """
    from gladiators.domain.bindings import default_binding_snapshot

    lines: list[str] = []
    for spec in default_binding_snapshot().tables.values():
        columns = ", ".join(
            f"{column.name} {column.physical_type or 'unknown'}"
            for column in spec.columns
        )
        lines.append(f"{spec.view_name}({columns})")
    return chr(10).join(lines)


PROMPT = """Bạn là một chuyên gia SQL. Viết MỘT câu SELECT DuckDB trả lời câu hỏi.

Lược đồ:
{schema}

Câu hỏi: {question}

Chỉ trả về SQL, không giải thích.{error}"""


def _sql_from(text: str) -> str:
    body = text.strip()
    if "```" in body:
        parts = [part for part in body.split("```") if "select" in part.lower()]
        if parts:
            body = parts[0]
    return body.replace("sql\n", "", 1).strip().rstrip(";")


def _expected_values(case: dict) -> list[float]:
    return [
        float(value) for value in (case.get("expected_value") or {}).values()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]


def classify(frame, case: dict) -> str:
    """``correct`` | ``wrong_value_silent`` | ``refused`` | ``crashed``.

    ``wrong_value_silent`` là ô ăn tiền của cả bảng: một con số SAI được trả về
    **mà không có tín hiệu nào** cho biết nó sai. Nó khác hẳn ``crashed`` — một
    lỗi nhìn thấy được là một lỗi sửa được.
    """
    targets = _expected_values(case)
    if not targets:
        return "correct" if frame is not None and len(frame) else "refused"
    if frame is None or frame.empty:
        return "refused"
    numbers: list[float] = []
    for column in frame.columns:
        for value in frame[column].tolist()[:5]:
            try:
                numbers.append(float(value))
            except (TypeError, ValueError):
                continue
    if any(abs(number - target) < 0.5 for number in numbers for target in targets):
        return "correct"
    return "wrong_value_silent"


def run_one(case: dict, client, schema: str, executor) -> dict:
    from gladiators.planner.compiler import assert_read_only_sql

    started = perf_counter()
    error, sql, frame, outcome = "", "", None, "crashed"
    for attempt in range(SYNTAX_RETRIES + 1):
        prompt = PROMPT.format(
            schema=schema, question=case["question"],
            error=f"\n\nLần trước lỗi: {error}" if error else "",
        )
        try:
            sql = _sql_from(client.complete(prompt))
            # B5-R2: vẫn phải qua assert_read_only_sql, và vẫn chạy trong một
            # executor đã khoá cấu hình. Phòng vệ chiều sâu không được nới ra chỉ
            # vì đây là một script đo.
            assert_read_only_sql(sql)
            # Chạy qua CHÍNH connection đã khoá cấu hình của QueryExecutor
            # (read-only, không external access, lock_configuration=true), nhưng
            # KHÔNG thêm một phương thức raw-SQL vào lớp production: một cửa
            # raw-SQL mở ra "chỉ để đo" là một cửa raw-SQL đang mở.
            frame = executor.connection.execute(sql).fetchdf()
            outcome = classify(frame, case)
            break
        except Exception as exc:                      # noqa: BLE001 — phân loại, không nuốt
            error = f"{type(exc).__name__}: {exc}"[:300]
            outcome = "crashed"
            if attempt == SYNTAX_RETRIES:
                break
    return {
        "id": case["id"], "question": case["question"], "sql": sql,
        "outcome": outcome, "error": error or None,
        "seconds": round(perf_counter() - started, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="eval/independent/answerable_manual.json")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    cases = json.loads((ROOT / args.suite).read_text(encoding="utf-8"))
    if isinstance(cases, dict):
        cases = cases.get("cases", [])
    cases = [case for case in cases if case.get("question")]
    if args.limit:
        cases = cases[: args.limit]

    from gladiators.data.repository import ArtifactRepository
    from gladiators.runtime_factory import create_runtime

    runtime = create_runtime(args.provider)
    client = runtime.llm_client
    if client is None or not hasattr(client, "complete"):
        # Không có provider thì KHÔNG in một bảng rỗng trông như một phép đo.
        print(json.dumps({
            "suite": args.suite, "provider": args.provider,
            "measured": False,
            "reason": (
                "Provider không có phương thức complete(); đối chứng này cần một "
                "LLM thật. Chạy với --provider deepseek và khoá API."
            ),
        }, ensure_ascii=False, indent=2))
        return

    from gladiators.planner.executor import QueryExecutor

    executor = QueryExecutor(ArtifactRepository())
    schema = raw_schema()
    try:
        rows = [run_one(case, client, schema, executor) for case in cases]
    finally:
        executor.close()

    counts = {
        name: sum(1 for row in rows if row["outcome"] == name)
        for name in ("correct", "wrong_value_silent", "refused", "crashed")
    }
    total = len(rows) or 1
    report = {
        "suite": args.suite, "provider": args.provider,
        "model": getattr(client, "model", "unknown"),
        "measured_on": date.today().isoformat(),
        "syntax_retries_allowed": SYNTAX_RETRIES,
        "cases": len(rows), "measured": True,
        "counts": counts,
        "rates": {name: round(value / total, 4) for name, value in counts.items()},
        "median_seconds": round(statistics.median(row["seconds"] for row in rows), 3)
        if rows else None,
        "note": (
            "B5-R3: không giấu kết quả bất lợi. Baseline nhanh hơn và trả lời "
            "nhiều câu hơn là kết quả DỰ KIẾN — điểm so sánh là ô "
            "wrong_value_silent, tức số câu trả lời SAI mà không có tín hiệu nào "
            "báo là sai."
        ),
        "rows": rows,
    }
    output = args.output or f"eval/reports/{date.today().isoformat()}-sql-baseline.json"
    out = ROOT / output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(
        {key: value for key, value in report.items() if key != "rows"},
        ensure_ascii=False, indent=2,
    ))


if __name__ == "__main__":
    main()
