#!/usr/bin/env python3
"""Báo cáo độ trễ theo p50/p95 — Spec2308 §WP-A6, nghiệm thu.

    PYTHONPATH=src .venv/Scripts/python.exe scripts/run_latency_report.py \
      --suite eval/questions.json --provider offline

Báo p50/p95 chứ KHÔNG báo trung bình: trung bình che mất đuôi xấu, và người xem
demo sẽ gặp đúng cái đuôi đó.

A6-R4 — đo trước, tối ưu sau. Script này phải có mặt và cho ra số nền trước khi
bất kỳ thay đổi tối ưu nào được merge; nếu không, "nhanh hơn" là một khẳng định
không kiểm lại được.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from gladiators.agent.budget import (
    MAX_LLM_CALLS_CRITICAL,
    P50_BUDGET_SECONDS,
    P95_BUDGET_SECONDS,
    STAGES,
)
from gladiators.runtime_factory import create_runtime

ROOT = Path(__file__).resolve().parents[1]


def percentile(values: list[float], fraction: float) -> float | None:
    """Phân vị theo phương pháp gần nhất-thứ-hạng, không nội suy.

    Nội suy sinh ra một con số chưa từng đo được. Với một mẫu vài chục lượt chạy,
    "giá trị thật nào đứng ở vị trí đó" trung thực hơn một trung bình có trọng số.
    """
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(fraction * len(ordered) + 0.5) - 1))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="eval/questions.json")
    parser.add_argument("--provider", default="offline")
    parser.add_argument("--limit", type=int, default=0, help="0 = cả bộ đề")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    cases = json.loads((ROOT / args.suite).read_text(encoding="utf-8"))
    if args.limit:
        cases = cases[: args.limit]
    runtime = create_runtime(args.provider)

    totals: list[float] = []
    critical: list[int] = []
    per_stage: dict[str, list[float]] = {stage: [] for stage in STAGES}
    cache_hits = cache_lookups = 0
    crashes = 0

    for case in cases:
        try:
            response = runtime.run(case["question"])
        except Exception:                      # một crash vẫn là một lượt chạy
            crashes += 1
            continue
        timing = response.planning.get("timing") or {}
        totals.append(float(timing.get("total", 0.0)))
        critical.append(int(response.planning.get("llm_calls_critical") or 0))
        for stage in STAGES:
            per_stage[stage].append(float(timing.get(stage, 0.0)))
        cache = response.planning.get("plan_cache")
        if isinstance(cache, dict):
            cache_lookups += 1
            cache_hits += bool(cache.get("hit"))

    p50 = percentile(totals, 0.50)
    p95 = percentile(totals, 0.95)
    llm_telemetry = (
        runtime.llm_client.telemetry()
        if runtime.llm_client and hasattr(runtime.llm_client, "telemetry") else {}
    )
    report = {
        "suite": args.suite, "provider": args.provider,
        "cases": len(cases), "measured": len(totals), "crashes": crashes,
        "p50_seconds": None if p50 is None else round(p50 / 1000, 4),
        "p95_seconds": None if p95 is None else round(p95 / 1000, 4),
        "llm_calls_critical_p95": percentile([float(v) for v in critical], 0.95),
        "stage_p95_ms": {
            stage: percentile(values, 0.95) for stage, values in per_stage.items()
        },
        "plan_cache_hit_rate": (
            round(cache_hits / cache_lookups, 4) if cache_lookups else None
        ),
        "llm_cache_hit_rate": llm_telemetry.get("cache_hit_rate"),
        "budget": {
            "p50_seconds": P50_BUDGET_SECONDS, "p95_seconds": P95_BUDGET_SECONDS,
            "max_llm_calls_critical": MAX_LLM_CALLS_CRITICAL,
        },
    }
    report["within_budget"] = bool(
        report["p50_seconds"] is not None
        and report["p50_seconds"] <= P50_BUDGET_SECONDS
        and report["p95_seconds"] <= P95_BUDGET_SECONDS
        and (report["llm_calls_critical_p95"] or 0) <= MAX_LLM_CALLS_CRITICAL,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        out = ROOT / args.output
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
