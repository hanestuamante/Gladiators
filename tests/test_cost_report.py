"""Đơn giá mỗi câu trả lời — Spec2308 §WP-B10.

Điều phải giữ: **không đoán**. Một con số chi phí bịa ra còn tệ hơn không có con
số nào, vì nó sẽ được trích dẫn.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_cost_report import NOT_AVAILABLE, cost_of, pricing_for, summarise  # noqa: E402


def test_pricing_lives_in_data_with_a_date_not_in_code():
    """B10-R1. Một đơn giá hard-code không có as_of sẽ âm thầm sai sau lần đổi
    giá đầu tiên, và không ai biết nó sai từ lúc nào."""
    payload = json.loads(Path("eval/pricing.json").read_text(encoding="utf-8"))
    for name, entry in payload.items():
        if name.startswith("_"):
            continue
        assert "as_of" in entry
        assert "prompt_usd_per_1m" in entry and "output_usd_per_1m" in entry

    source = Path("scripts/run_evaluation.py").read_text(encoding="utf-8")
    assert "1.5 / 1_000_000" not in source
    assert "9.0 / 1_000_000" not in source


def test_a_provider_without_a_confirmed_price_reports_n_a():
    """B10-R2. Không đoán."""
    assert pricing_for("deepseek") is None
    assert cost_of({"prompt_tokens": 1000, "output_tokens": 100}, None) == NOT_AVAILABLE


def test_a_provider_with_a_price_reports_a_number():
    price = pricing_for("gemini")
    assert price is not None
    assert cost_of({"prompt_tokens": 1_000_000, "output_tokens": 0}, price) == 1.5


def test_refusals_are_reported_as_costing_nothing_and_that_is_the_point():
    """Gate là code chạy TRƯỚC khi LLM được gọi, nên một câu bị từ chối ở gate
    không sinh lời gọi nào."""
    report = {
        "metrics": {"provider": "gemini",
                    "llm_telemetry": {"prompt_tokens": 2_000_000, "output_tokens": 0}},
        "rows": [
            {"run": 1, "action": "allow"}, {"run": 1, "action": "allow"},
            {"run": 1, "action": "abstain"}, {"run": 1, "action": "clarify"},
        ],
    }
    summary = summarise(report)
    assert summary["cases_answered"] == 2 and summary["cases_refused"] == 2
    assert summary["total_cost_usd"] == 3.0
    assert summary["cost_per_answered_usd"] == 1.5
    assert summary["cost_per_refused_usd"] == 0.0
    # Cách quy chi phí phải đi KÈM con số, không nằm trong một tài liệu khác.
    assert "gate là code chạy TRƯỚC" in summary["caveat"]


def test_the_report_reader_never_reruns_the_eval():
    """B10-R3. Chạy lại sẽ cho một tỷ lệ trúng cache khác và một con số không ai
    đối chiếu được với báo cáo gốc."""
    source = Path("scripts/run_cost_report.py").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    assert "AgentRuntime" not in code
    assert "create_runtime" not in code
