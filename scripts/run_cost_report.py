#!/usr/bin/env python3
"""Đơn giá mỗi câu trả lời — Spec2308 §WP-B10.

    PYTHONPATH=src .venv/Scripts/python.exe scripts/run_cost_report.py \\
      --report eval/reports/2026-08-27.json

Trả lời *"triển khai thật thì tốn bao nhiêu?"* bằng số — câu hỏi rất ít đội thi
trả lời được.

**B10-R3 — KHÔNG chạy lại eval.** Script này chỉ đọc report đã có, để con số chi
phí khớp đúng lần chạy đã công bố. Chạy lại sẽ cho một lần gọi LLM khác, một tỷ
lệ trúng cache khác, và một con số không ai đối chiếu được với báo cáo gốc.

Câu đáng nói kèm bảng này: *"từ chối gần như miễn phí, vì gate là code chạy
**trước** khi LLM được gọi"* — và nó phải kèm số, không kèm lời.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRICING_PATH = ROOT / "eval" / "pricing.json"

NOT_AVAILABLE = "n/a"


def pricing_for(provider: str) -> dict | None:
    """Đơn giá đã xác nhận, hoặc ``None``.

    B10-R2: provider không có đơn giá thì in ``n/a``, không đoán. Một con số chi
    phí bịa ra còn tệ hơn không có con số nào, vì nó sẽ được trích dẫn.
    """
    if not PRICING_PATH.exists():
        return None
    entry = json.loads(PRICING_PATH.read_text(encoding="utf-8")).get(provider)
    if not entry or entry.get("as_of") is None:
        return None
    if entry.get("prompt_usd_per_1m") is None or entry.get("output_usd_per_1m") is None:
        return None
    return entry



# Khoá cộng dồn được. "provider" là chuỗi, "error_counts"/"fallback_calls" là dict
# — cộng chúng lại là vô nghĩa, nên chúng KHÔNG nằm ở đây.
_SUMMABLE = (
    "api_calls", "cache_hits", "failures", "prompt_tokens", "output_tokens",
    "total_tokens", "empty_retries",
)


def flatten_telemetry(telemetry: dict | None) -> dict:
    """Gộp telemetry lồng của ``FallbackLLMClient`` thành khoá phẳng.

    Client bọc trả ``{provider, primary: {...}, fallback: {...}}``, còn mọi script
    đo đọc ``prompt_tokens`` phẳng. Không gộp thì ``cost_of`` thấy 0 token và báo
    **0 USD** — một con số 0 im lặng, tệ hơn hẳn ``n/a`` vì nó trông như một phép
    đo thành công.
    """
    telemetry = telemetry or {}
    if any(key in telemetry for key in _SUMMABLE):
        return dict(telemetry)
    totals = {key: 0 for key in _SUMMABLE}
    found = False
    for child in ("primary", "fallback"):
        inner = telemetry.get(child)
        if not isinstance(inner, dict):
            continue
        found = True
        for key in _SUMMABLE:
            value = inner.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] += value
    if not found:
        return dict(telemetry)
    totals["provider"] = telemetry.get("provider")
    totals["flattened_from"] = ["primary", "fallback"]
    return totals


def cost_of(telemetry: dict, price: dict | None) -> float | str:
    if price is None:
        return NOT_AVAILABLE
    return round(
        telemetry.get("prompt_tokens", 0) * float(price["prompt_usd_per_1m"]) / 1_000_000
        + telemetry.get("output_tokens", 0) * float(price["output_usd_per_1m"]) / 1_000_000,
        6,
    )


def _split(value: float | str, count: int) -> float | str:
    if value == NOT_AVAILABLE or not count:
        return NOT_AVAILABLE
    return round(float(value) / count, 8)


def summarise(report: dict, gated: dict | None = None) -> dict:
    metrics = report.get("metrics") or report
    rows = report.get("rows") or []
    telemetry = flatten_telemetry(metrics.get("llm_telemetry"))
    provider = metrics.get("provider") or report.get("provider") or "unknown"
    price = pricing_for(provider)

    first_run = [row for row in rows if row.get("run") == 1] or rows
    answered = [row for row in first_run if row.get("action") == "allow"]
    refused = [row for row in first_run if row.get("action") in {"clarify", "abstain"}]

    total = cost_of(telemetry, price)
    calls = telemetry.get("api_calls") or 0
    cache_hits = telemetry.get("cache_hits") or 0
    lookups = calls + cache_hits

    # Toàn bộ chi phí API quy về các câu ĐÃ TRẢ LỜI. Đây không phải một phép chia
    # tuỳ tiện: gate chạy TRƯỚC khi LLM được gọi, nên một câu bị từ chối ở gate
    # không sinh lời gọi nào. Nếu có câu từ chối SAU khi đã gọi LLM thì phép quy
    # này ước tính THẤP chi phí của chúng — nói rõ ra để không ai đọc ngược.
    report_out = {
        "report": str(report.get("_path", "")),
        "provider": provider,
        "pricing_as_of": (price or {}).get("as_of", NOT_AVAILABLE),
        "cases_answered": len(answered),
        "cases_refused": len(refused),
        "total_cost_usd": total,
        "cost_per_answered_usd": _split(total, len(answered)),
        # Gần bằng 0 và đó là điểm mạnh, không phải một chỗ trống trong bảng.
        "cost_per_refused_usd": 0.0 if total != NOT_AVAILABLE else NOT_AVAILABLE,
        "llm_cache_hit_rate": round(cache_hits / lookups, 4) if lookups else None,
        "plan_cache_hit_rate": metrics.get("plan_cache_hit_rate"),
        "llm_calls_total": calls,
        "median_seconds_per_case": metrics.get("median_seconds"),
        "caveat": (
            "Chi phí API quy hết về câu đã trả lời: gate là code chạy TRƯỚC khi "
            "LLM được gọi, nên câu bị từ chối ở gate không sinh lời gọi nào. Câu "
            "bị từ chối SAU khi đã gọi LLM sẽ bị phép quy này ước tính thấp."
        ),
    }
    if gated is not None:
        gated_metrics = gated.get("metrics") or gated
        gated_cost = cost_of(
            flatten_telemetry(gated_metrics.get("llm_telemetry")),
            pricing_for(gated_metrics.get("provider") or provider),
        )
        if total != NOT_AVAILABLE and gated_cost != NOT_AVAILABLE:
            report_out["marginal_cost_of_one_check_usd"] = round(
                float(total) - float(gated_cost), 6,
            )
        else:
            report_out["marginal_cost_of_one_check_usd"] = NOT_AVAILABLE
    return report_out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="report JSON đã có, KHÔNG chạy lại eval")
    parser.add_argument("--gated-report", default="", help="report --mode gated cùng suite")
    args = parser.parse_args()

    path = ROOT / args.report if not Path(args.report).is_absolute() else Path(args.report)
    report = json.loads(path.read_text(encoding="utf-8"))
    report["_path"] = str(path)
    gated = None
    if args.gated_report:
        gated_path = ROOT / args.gated_report
        gated = json.loads(gated_path.read_text(encoding="utf-8"))

    print(json.dumps(summarise(report, gated), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
