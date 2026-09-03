#!/usr/bin/env python3
"""Phase 5 L4 evaluator with independent denotation and escalation ablation."""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import traceback
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.independent.l4_oracle import build_l4_denotation
from gladiators.agent.llm import GeminiLLMClient, GroqLLMClient, HuggingFaceLLMClient
from gladiators.agent.parser import MultilingualIntentParser
from gladiators.data.repository import ArtifactRepository
from gladiators.domain.intent_registry import default_registry
from gladiators.planner.compiler import compile_plan
from gladiators.planner.consensus import NVersionResolver
from gladiators.planner.critic import PlanCritic
from gladiators.planner.executor import QueryExecutor
from gladiators.planner.open_planner import OpenAnalyticalPlanner
from gladiators.planner.query_ir import LogicalQueryPlan, OutputField, PlanNode, Predicate
from gladiators.planner.semantic_parser import AnalyticalRequest, classify_complexity


def _provider(name: str):
    if name == "groq":
        return GroqLLMClient()
    if name == "gemini":
        return GeminiLLMClient()
    if name == "huggingface":
        return HuggingFaceLLMClient()
    return None


def _fixture_plan(case: dict) -> LogicalQueryPlan:
    measures = tuple(case["measures"])
    output = (OutputField(name="brand", type="string", semantic_ref="dim.brand"),) + tuple(
        OutputField(name=ref.rsplit(".", 1)[-1], type="number", semantic_ref=ref)
        for ref in measures
    )
    sentinel = tuple(
        Predicate(ref=ref, op="lt", parameter=f"{ref.rsplit('.', 1)[-1]}_sentinel", value=999_999_999)
        for ref in measures if ref in {"measure.price", "measure.price_original"}
    )
    return LogicalQueryPlan(
        plan_id=f"phase5:{case['id']}:fixture", time_scope=(case["snapshot_date"],),
        output_node="n3", requested_output_shape=output,
        nodes=(
            PlanNode(
                node_id="n1", op="Scan", source="products_clean.csv",
                refs=("dim.brand", *measures), input_grain="listing_snapshot",
                output_grain="listing_snapshot", expected_schema=output,
                expected_cardinality="<=3341",
            ),
            PlanNode(
                node_id="n2", op="Filter", inputs=("n1",), predicates=(
                    Predicate(ref="dim.country", op="eq", parameter="country", value=case["country"]),
                    Predicate(ref="dim.date", op="eq", parameter="date", value=case["snapshot_date"]),
                    *sentinel,
                ), input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="<=1000",
            ),
            PlanNode(
                node_id="n3", op="Aggregate", inputs=("n2",), refs=measures,
                group_by=("dim.brand",), aggregation=case["aggregation"],
                input_grain="listing_snapshot", output_grain="brand",
                expected_schema=output, expected_cardinality="<=100",
            ),
        ),
    )


class OfflineL4Client:
    provider, model, prompt_version = "offline", "fixture-independent-oracle", "phase5.v1"

    def __init__(self, case: dict):
        self.plan = _fixture_plan(case)

    def plan_analytical(self, payload: dict) -> dict:
        return self.plan.model_dump(mode="json")

    def plan_analytical_alternate(self, payload: dict) -> dict:
        if "candidates" in payload:
            raise ValueError("P10 alternate planner must remain blinded.")
        return self.plan.model_dump(mode="json")

    def critique_plan(self, question: str, payload: dict) -> dict:
        return {"issues": []}

    def adjudicate_plans(self, payload: dict) -> dict:
        return {"verdict": "unresolved", "reason_issue_type": None, "detail": "Offline fixture does not vote."}


def _request(case: dict) -> AnalyticalRequest:
    parsed = MultilingualIntentParser().parse(case["question"], default_registry())
    if parsed.intent != "open_analytical" or parsed.analytical is None:
        raise ValueError(f"{case['id']} không đi vào open_analytical path: {parsed.intent}")
    request = AnalyticalRequest.model_validate(parsed.analytical)
    if classify_complexity(request) != "L4":
        raise ValueError(f"{case['id']} không được classifier gắn L4.")
    return request


def _execute(repository: ArtifactRepository, plan: LogicalQueryPlan):
    compiled = compile_plan(plan)
    executor = QueryExecutor(repository)
    try:
        return executor.execute(compiled)
    finally:
        executor.close()


def _normal(value: Any) -> Any:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return value


def _rows(frame) -> list[dict[str, Any]]:
    result = [
        {column: _normal(value) for column, value in zip(frame.columns, row)}
        for row in frame.itertuples(index=False, name=None)
    ]
    return sorted(result, key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False, default=str))


def _equivalent(actual: list[dict[str, Any]], expected: list[dict[str, Any]]) -> bool:
    if len(actual) != len(expected):
        return False
    actual = sorted(actual, key=lambda row: str(row.get("brand")))
    expected = sorted(expected, key=lambda row: str(row.get("brand")))
    for left, right in zip(actual, expected):
        if set(left) != set(right):
            return False
        for key in left:
            a, b = left[key], right[key]
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                if not math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9):
                    return False
            elif a != b:
                return False
    return True


def run_once(case: dict, mode: str, repository: ArtifactRepository, client: Any) -> dict:
    started = time.perf_counter()
    request = _request(case)
    primary = OpenAnalyticalPlanner(client).plan(case["question"], request, case["country"])
    selected = primary.plan
    meta = {
        "primary_plan_id": primary.plan.plan_id, "primary_attempts": primary.attempts,
        "plan_disagreement": False, "result_disagreement": False,
        "adjudicated": False, "unresolved": False,
    }
    if mode == "critic":
        review = PlanCritic(client).review(case["question"], selected)
        meta["critic_issues"] = [issue.model_dump() for issue in review.issues]
        meta["critic_dropped"] = [issue.model_dump() for issue in review.dropped]
        if review.issues:
            raise RuntimeError("P9 critic rejected primary plan.")
    elif mode == "nversion":
        consensus = NVersionResolver(repository, client, client).resolve(
            case["question"], request, case["country"], selected,
        )
        selected = consensus.plan
        meta.update(
            selected=consensus.selected,
            plan_disagreement=consensus.plan_disagreement,
            result_disagreement=consensus.result_disagreement,
            adjudicated=consensus.adjudicated,
            alternate_attempts=consensus.alternate_attempts,
            consensus_reason=consensus.reason,
        )
    execution = _execute(repository, selected)
    actual = _rows(execution.frame)
    expected = build_l4_denotation(case, repository.root)
    correct = _equivalent(actual, expected)
    meta.update(
        selected_plan_id=selected.plan_id, plan_hash=execution.plan_hash,
        row_count=execution.row_count, denotation_correct=correct,
        false_consensus=(mode == "nversion" and not meta["result_disagreement"] and not correct),
        latency_seconds=time.perf_counter() - started,
    )
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="eval/l4_acceptance.json")
    parser.add_argument("--provider", choices=("offline", "groq", "gemini", "huggingface"), default="offline")
    parser.add_argument("--modes", default="single,critic,nversion")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--output", default="artifacts/phase5")
    parser.add_argument(
        "--gold-review-status", choices=("pending_human_review", "approved"),
        default="pending_human_review",
        help="Chỉ đặt approved sau khi reviewer nghiệp vụ duyệt semantics/gold của cả 6 case.",
    )
    args = parser.parse_args()
    cases = json.loads(Path(args.suite).read_text(encoding="utf-8"))
    modes = tuple(dict.fromkeys(item.strip() for item in args.modes.split(",") if item.strip()))
    if not modes or not set(modes).issubset({"single", "critic", "nversion"}):
        raise SystemExit("--modes chỉ nhận single,critic,nversion")

    repository = ArtifactRepository("data/processed")
    shared_client = _provider(args.provider)
    rows: list[dict[str, Any]] = []
    for mode in modes:
        for case in cases:
            for run in range(1, args.runs + 1):
                client = OfflineL4Client(case) if args.provider == "offline" else shared_client
                try:
                    row = {"id": case["id"], "mode": mode, "run": run, **run_once(case, mode, repository, client)}
                except Exception as exc:
                    row = {
                        "id": case["id"], "mode": mode, "run": run,
                        "denotation_correct": False, "crashed": True,
                        "error": type(exc).__name__, "error_message": str(exc)[:500],
                        "traceback": "".join(traceback.format_exception(exc, limit=6))[-2000:],
                    }
                rows.append(row)

    metrics: dict[str, Any] = {
        "provider": args.provider, "model": getattr(shared_client, "model", "offline"),
        "cases": len(cases), "runs": args.runs,
        "gold_review_status": args.gold_review_status,
        "production_go_no_go": "NO-GO",
        "reason": "Đang tính acceptance sau khi tổng hợp từng mode.",
        "modes": {},
    }
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["mode"]].append(row)
    for mode, items in grouped.items():
        total = len(items)
        latencies = [float(item.get("latency_seconds", 0)) for item in items]
        stable_cases = []
        for case in cases:
            case_rows = [row for row in items if row["id"] == case["id"]]
            hashes = {row.get("plan_hash") for row in case_rows if row.get("plan_hash")}
            stable_cases.append(len(case_rows) == args.runs and len(hashes) == 1)
        metrics["modes"][mode] = {
            "runs": total,
            "denotation_accuracy": sum(bool(item.get("denotation_correct")) for item in items) / total,
            "crash_rate": sum(bool(item.get("crashed")) for item in items) / total,
            "plan_disagreement_rate": sum(bool(item.get("plan_disagreement")) for item in items) / total,
            "result_disagreement_rate": sum(bool(item.get("result_disagreement")) for item in items) / total,
            "false_consensus_rate": sum(bool(item.get("false_consensus")) for item in items) / total,
            "adjudication_rate": sum(bool(item.get("adjudicated")) for item in items) / total,
            "mean_latency_seconds": statistics.fmean(latencies),
            "p95_latency_seconds": sorted(latencies)[max(0, math.ceil(0.95 * total) - 1)],
            "plan_stability_rate": sum(stable_cases) / len(stable_cases),
        }
    required_modes = {"single", "critic", "nversion"}
    nversion = metrics["modes"].get("nversion", {})
    go_checks = {
        "production_provider": args.provider != "offline",
        "gold_human_reviewed": args.gold_review_status == "approved",
        "all_ablation_modes_present": required_modes.issubset(metrics["modes"]),
        "l4_denotation_accuracy_gte_0_80": nversion.get("denotation_accuracy", 0) >= 0.80,
        "crash_rate_zero": nversion.get("crash_rate", 1) == 0,
        "plan_stability_gte_0_85": nversion.get("plan_stability_rate", 0) >= 0.85,
        "p95_latency_lte_25s": nversion.get("p95_latency_seconds", math.inf) <= 25,
    }
    metrics["go_no_go_checks"] = go_checks
    if all(go_checks.values()):
        metrics["production_go_no_go"] = "GO"
        metrics["reason"] = "Đạt toàn bộ Phase 5 L4 acceptance checks của runner."
    else:
        failed = [name for name, passed in go_checks.items() if not passed]
        metrics["reason"] = "Chưa đạt: " + ", ".join(failed)
    if shared_client is not None and hasattr(shared_client, "telemetry"):
        metrics["llm_telemetry"] = shared_client.telemetry()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    report = {"metrics": metrics, "rows": rows}
    stem = output / f"{date.today()}-{args.provider}"
    stem.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    stem.with_suffix(".md").write_text(
        "# Phase 5 L4 evaluation\n\n" + "\n".join(f"- **{key}:** {value}" for key, value in metrics.items()) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
