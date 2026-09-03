"""Insight API performance report — ultimate solution §16 P10.

Measures the read path against a real bundle: p50/p95 latency per endpoint and
the cost of the one call that touches the CSV.

Reports percentiles rather than a mean. A mean hides the tail, and the tail is
what a user notices -- an endpoint averaging 5ms with a 400ms p95 feels broken
even though the average looks excellent.

    python scripts/build_insight_performance_report.py [--runs 50]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

warnings.filterwarnings("ignore")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from gladiators.insights.api import router, set_repository  # noqa: E402
from gladiators.insights.repository import InsightRepository, latest_bundle_dir  # noqa: E402

SCHEMA_VERSION = "insight-performance.v1"
BUNDLE_ROOT = REPO / "artifacts" / "insights"

# Budgets are advisory here: this is a read path over an immutable local file,
# so anything slow means a scan crept in, not that the machine is busy.
P95_BUDGET_MS = {
    "health": 50.0, "overview": 250.0, "cards": 100.0,
    "card_detail": 50.0, "evidence": 50.0, "chart": 100.0,
}


def percentiles(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "p50": round(statistics.median(ordered), 2),
        "p95": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 2),
        "max": round(ordered[-1], 2),
        "mean": round(statistics.fmean(ordered), 2),
    }


def measure(client, path: str, params: dict, runs: int) -> dict:
    latencies: list[float] = []
    status = None
    for _ in range(runs):
        started = time.perf_counter()
        response = client.get(path, params=params)
        latencies.append((time.perf_counter() - started) * 1000)
        status = response.status_code
    return {"status": status, "runs": runs, **percentiles(latencies)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--output", default=str(REPO / "eval" / "insight_performance.json"))
    args = parser.parse_args()

    bundle = latest_bundle_dir(BUNDLE_ROOT)
    if bundle is None:
        print("SKIP: chưa có insight bundle; chạy scripts/build_insight_mart.py trước.")
        return 0

    repository = InsightRepository(bundle)
    app = FastAPI()
    app.include_router(router)
    set_repository(repository)

    with TestClient(app) as client:
        cards = client.get("/insights/v1/cards", params={"limit": 50}).json()["cards"]
        insight_id = cards[0]["insight_id"] if cards else None
        evidence_id = cards[0]["evidence_ids"][0] if cards else None

        endpoints = {
            "health": ("/insights/v1/health", {}),
            "overview": ("/insights/v1/overview", {"country": "vn"}),
            "cards": ("/insights/v1/cards", {"limit": 20}),
            "chart": ("/insights/v1/charts/price_move", {"country": "vn"}),
        }
        if insight_id:
            endpoints["card_detail"] = (f"/insights/v1/cards/{insight_id}", {})
        if evidence_id:
            endpoints["evidence"] = (f"/insights/v1/evidence/{evidence_id}", {})

        results = {
            name: measure(client, path, params, args.runs)
            for name, (path, params) in endpoints.items()
        }
    set_repository(None)

    breaches = [
        {"endpoint": name, "p95": stats["p95"], "budget": P95_BUDGET_MS[name]}
        for name, stats in results.items()
        if name in P95_BUDGET_MS and stats["p95"] > P95_BUDGET_MS[name]
    ]
    report = {
        "schema_version": SCHEMA_VERSION,
        "dataset_version": repository.dataset_version,
        "as_of_date": repository.as_of_date,
        "scorecard_rows": int(len(repository.scorecard)),
        "card_count": len(repository.cards()),
        "runs_per_endpoint": args.runs,
        "latency_ms": results,
        "p95_budget_ms": P95_BUDGET_MS,
        "breaches": breaches,
        "note": "Percentile chứ không phải trung bình: trung bình che mất đuôi, "
                "mà đuôi mới là thứ người dùng cảm thấy.",
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"Performance report → {Path(args.output).relative_to(REPO)}")
    for name, stats in sorted(results.items()):
        budget = P95_BUDGET_MS.get(name)
        mark = "FAIL" if budget and stats["p95"] > budget else "ok  "
        print(f"  [{mark}] {name:12s} p50 {stats['p50']:7.2f}ms  p95 {stats['p95']:7.2f}ms"
              f"  (budget {budget}ms)")
    if breaches:
        print(f"\n{len(breaches)} endpoint vượt ngân sách p95.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
