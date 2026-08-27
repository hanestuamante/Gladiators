#!/usr/bin/env python3
"""Bảng P-A vs P-B — Spec2308 §WP-A11, nghiệm thu.

    GLADIATORS_ENABLE_LLM_PARSER=1 PYTHONPATH=src \\
      .venv/Scripts/python.exe scripts/run_intent_policy_report.py \\
      --suite eval/independent/answerable_manual.json --provider deepseek

Đo trên **bộ đề độc lập** (B3), không phải bộ tự viết: trên bộ tự viết,
``over_refusal_rate`` luôn bằng 0 theo định nghĩa (§B1.2), nên nó không phân biệt
được hai chính sách.

**Chỉ đề xuất đổi mặc định khi cả ba điều cùng đúng**: độ phủ TĂNG, rủi ro KHÔNG
tăng, và p95 vẫn trong ngân sách. Thiếu một điều thì giữ `P-A` và báo cáo lý do —
đó cũng là một kết quả, và là kết quả phải nói ra chứ không phải giấu đi (A11-R3).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_latency_report import percentile  # noqa: E402
from run_risk_coverage import _answerable, _correct  # noqa: E402

POLICIES = ("P-A", "P-B")


def measure(cases: list[dict], runtime) -> dict[str, object]:
    """Độ phủ / rủi ro / từ chối oan / p95, cộng dấu vết chính sách đã bắn."""
    answered = wrong = refused_answerable = answered_unanswerable = 0
    labelled = 0
    seconds: list[float] = []
    policy_reasons: dict[str, int] = {}
    llm_won = 0

    for case in cases:
        label = _answerable(case)
        if label is None:
            continue
        labelled += 1
        response = runtime.run(case["question"])
        seconds.append(
            float((response.planning.get("timing") or {}).get("total", 0.0)) / 1000,
        )
        verdict = response.llm.get("intent_policy") or {}
        reason = str(verdict.get("reason") or verdict.get("policy") or "?")
        policy_reasons[reason] = policy_reasons.get(reason, 0) + 1
        if reason == "deterministic_open":
            llm_won += 1

        if response.gate.action == "allow":
            answered += 1
            if not _correct(response, case):
                wrong += 1
            if not label:
                answered_unanswerable += 1
        elif label:
            refused_answerable += 1

    answerable_total = sum(1 for case in cases if _answerable(case))
    unanswerable_total = sum(1 for case in cases if _answerable(case) is False)
    telemetry = (
        runtime.llm_client.telemetry()
        if runtime.llm_client and hasattr(runtime.llm_client, "telemetry") else {}
    )
    return {
        "labelled_cases": labelled,
        "coverage": round(answered / labelled, 4) if labelled else None,
        "risk": round(wrong / answered, 4) if answered else 0.0,
        "over_refusal_rate": (
            round(refused_answerable / answerable_total, 4) if answerable_total else None
        ),
        "over_answer_rate": (
            round(answered_unanswerable / unanswerable_total, 4)
            if unanswerable_total else None
        ),
        "p95_seconds": percentile(seconds, 0.95),
        "p50_seconds": percentile(seconds, 0.50),
        "answered": answered, "wrong": wrong,
        # Chính sách CÓ bắn hay không phải đo được. Hai bảng số giống nhau vì
        # P-B không bao giờ kích hoạt, và hai bảng giống nhau vì P-B kích hoạt mà
        # vô hại, là hai kết luận khác hẳn.
        "policy_reasons": policy_reasons,
        "llm_label_taken": llm_won,
        "llm_telemetry": telemetry,
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

    # A11-R4: KHÔNG bật cờ này trong source. Nó được bật ở đây, trong một script
    # đo chạy tay, và chỉ sống trong tiến trình này.
    os.environ["GLADIATORS_ENABLE_LLM_PARSER"] = "1"

    from gladiators.runtime_factory import create_runtime

    results: dict[str, object] = {}
    for policy in POLICIES:
        os.environ["GLADIATORS_INTENT_POLICY"] = policy
        results[policy] = measure(cases, create_runtime(args.provider))

    pa, pb = results["P-A"], results["P-B"]

    def better(key: str, lower_is_better: bool = False) -> bool | None:
        left, right = pa.get(key), pb.get(key)
        if left is None or right is None:
            return None
        return right < left if lower_is_better else right > left

    coverage_up = better("coverage")
    risk_up = better("risk")
    from gladiators.agent.budget import P95_BUDGET_SECONDS

    within = (pb.get("p95_seconds") or 0) <= P95_BUDGET_SECONDS
    recommend = bool(coverage_up and not risk_up and within)

    report = {
        "suite": args.suite, "provider": args.provider,
        "measured_on": date.today().isoformat(),
        "cases": len(cases),
        "results": results,
        "default_policy": "P-A",
        "recommend_switch_to_p_b": recommend,
        "recommendation_reason": (
            "Độ phủ tăng, rủi ro không tăng, p95 trong ngân sách."
            if recommend else
            "KHÔNG đủ điều kiện đổi mặc định. A11-R3 đòi P-B phải THẮNG, không "
            "phải hoà: cần độ phủ tăng VÀ rủi ro không tăng VÀ p95 trong ngân "
            "sách. Giữ P-A."
        ),
    }
    output = args.output or f"eval/reports/{date.today().isoformat()}-intent-policy.json"
    out = ROOT / output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def cell(value: object) -> str:
        return "n/a" if value is None else f"{value}"

    print(f"{'':<26}{'P-A':>12}{'P-B':>12}")
    for label, key in (
        ("Độ phủ (coverage)", "coverage"),
        ("Rủi ro (risk)", "risk"),
        ("Từ chối oan", "over_refusal_rate"),
        ("Trả lời thứ không có", "over_answer_rate"),
        ("p50 độ trễ (s)", "p50_seconds"),
        ("p95 độ trễ (s)", "p95_seconds"),
        ("Nhãn LLM được lấy", "llm_label_taken"),
    ):
        print(f"{label:<26}{cell(pa.get(key)):>12}{cell(pb.get(key)):>12}")
    print()
    print(report["recommendation_reason"])
    print(f"Chi tiết: {output}")


if __name__ == "__main__":
    main()
