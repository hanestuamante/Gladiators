#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))

from gladiators.agent.llm import FakeLLMClient, GeminiLLMClient, GroqLLMClient, HuggingFaceLLMClient
from gladiators.agent.verifier import verify_numeric_claims
from gladiators.agent.workflow import AgentRuntime


INDEPENDENT_GOLDEN = json.loads(
    (Path(__file__).resolve().parents[1] / "eval" / "independent" / "golden_v2.json").read_text(encoding="utf-8")
)


def div(a, b): return a / b if b else 0.0


def expected_plan(runtime, intent: str) -> list[str]:
    spec = runtime.registry.get(intent)
    return list(spec.tool_plan) if spec else []


def trajectory_correct(case, response, runtime) -> bool:
    actual = [call.name for call in response.tool_calls]
    if case["expected_action"] == "allow":
        return actual == expected_plan(runtime, case["expected_intent"]) and all(call.status == "ok" for call in response.tool_calls)
    if case["expected_action"] == "abstain":
        plan = expected_plan(runtime, case["expected_intent"])
        return actual == [] or (actual == plan[:len(actual)] and all(call.status in {"ok", "empty"} for call in response.tool_calls))
    plan = expected_plan(runtime, case["expected_intent"])
    return actual == [] or actual == plan[:1]


def evidence_correct(case, response, runtime) -> bool:
    if case["expected_action"] != "allow":
        return response.evidence == []
    metrics = [e.metric for e in response.evidence]
    if case["expected_intent"] == "sales_decline":
        if set(metrics) != {"monthly_sold_delta", "days_since_previous"} or not response.resolved_listing_key:
            return False
        rows = runtime.repo.transitions.query("product_listing_key == @response.resolved_listing_key and transition_metric_eligible == True").sort_values("date")
        if rows.empty: return False
        row = rows.iloc[-1]; values = {e.metric: float(e.value) for e in response.evidence}
        return math.isclose(values["monthly_sold_delta"], float(row.monthly_sold_delta)) and math.isclose(values["days_since_previous"], float(row.days_since_previous))
    if case["expected_intent"] == "similar_product":
        scores = [float(e.value) for e in response.evidence]
        return len(scores) == 5 and metrics == ["similarity_score"] * 5 and scores == sorted(scores, reverse=True) and all(e.attrs.get("candidate_listing_key") != response.resolved_listing_key and e.attrs.get("rank") == i for i, e in enumerate(response.evidence, 1))
    if case["expected_intent"] == "promotion_effectiveness":
        required = {f"{group}_{metric}" for group in ("with_voucher", "without_voucher") for metric in ("listing_count", "mean_monthly_sold_proxy", "median_monthly_sold_proxy")}
        if set(metrics) != required: return False
        country = response.request.country; snapshots = runtime.repo.snapshots.query("country_code == @country").copy(); latest = snapshots.loc[snapshots.date.astype(str) == snapshots.date.astype(str).max()]; valid = latest.loc[latest.monthly_sold_value_num.notna()]
        expected = {}
        for flag, group in valid.groupby("has_structured_voucher", observed=True):
            label = "with_voucher" if bool(flag) else "without_voucher"
            expected.update({f"{label}_listing_count": len(group), f"{label}_mean_monthly_sold_proxy": group.monthly_sold_value_num.mean(), f"{label}_median_monthly_sold_proxy": group.monthly_sold_value_num.median()})
        return all(math.isclose(float(e.value), float(expected[e.metric]), rel_tol=1e-6, abs_tol=1e-6) for e in response.evidence)
    if case["expected_intent"] == "analytical_query":
        kind = response.request.slots.get("analytical_kind")
        country = response.request.country
        gold = INDEPENDENT_GOLDEN.get("results", {}).get(country, {}).get(kind)
        if gold is None:
            return False
        if kind == "highest_revenue_day":
            values = {e.metric: e.value for e in response.evidence}
            return (
                set(values) == {"highest_revenue_proxy_date", "estimated_recent_revenue"}
                and values["highest_revenue_proxy_date"] == gold["date"]
                and math.isclose(float(values["estimated_recent_revenue"]), gold["estimated_recent_revenue"])
            )
        values = {e.metric: e.value for e in response.evidence}
        if kind == "listing_count":
            return set(values) == {"listing_count"} and int(values["listing_count"]) == gold["listing_count"]
        if kind == "highest_price_listing":
            return set(values) == {"product_name", "price"} and values["product_name"] == gold["product_name"] and math.isclose(float(values["price"]), gold["price"])
        if kind == "highest_monthly_sold_listing":
            return set(values) == {"product_name", "monthly_sold"} and values["product_name"] == gold["product_name"] and math.isclose(float(values["monthly_sold"]), gold["monthly_sold"])
        if kind == "top_shop_by_listing_count":
            return (
                set(values) == {"shop_name", "listing_count"}
                and values["shop_name"] == gold["shop_name"]
                and int(values["listing_count"]) == gold["listing_count"]
            )
        return False
    return False


def citation_metrics(response) -> tuple[float, float]:
    if not response.evidence: return 1.0, 1.0
    ids = {e.evidence_id for e in response.evidence}
    cited = set(re.findall(r"ev:[a-f0-9]+:\d{4}", response.answer))
    return div(len(ids & cited), len(ids)), div(len(ids & cited), len(cited)) if cited else 0.0


def run_case(case, runtime):
    response = runtime.run(case["question"])
    intent_action = response.request.intent == case["expected_intent"] and response.gate.action == case["expected_action"]
    gate_rule = not case.get("expected_rule") or response.gate.rule_id == case["expected_rule"]
    entity = not case.get("expected_listing_key") or response.resolved_listing_key == case["expected_listing_key"]
    trajectory = trajectory_correct(case, response, runtime)
    evidence = evidence_correct(case, response, runtime)
    citation_recall, citation_precision = citation_metrics(response)
    verifier = bool(response.verification.get("passed"))
    mutation = verify_numeric_claims(response.answer + " Giá trị kiểm tra 987654.321.", response.evidence)
    mutation_detected = runtime.enable_verifier and not mutation["passed"]
    llm_path = runtime.llm_client is None or (not response.llm.get("parse_fallback") and not response.llm.get("generation", {}).get("fallback"))
    passed = all((intent_action, gate_rule, entity, trajectory, evidence, citation_recall == 1.0, citation_precision == 1.0, verifier, mutation_detected, llm_path))
    return response, {"intent_action": intent_action, "gate_rule": gate_rule, "entity": entity, "trajectory": trajectory, "evidence": evidence, "citation_recall": citation_recall, "citation_precision": citation_precision, "verifier": verifier, "mutation_detected": mutation_detected, "llm_path": llm_path, "passed": passed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="eval/questions.json"); ap.add_argument("--runs", type=int, default=3); ap.add_argument("--output", default="eval/reports")
    ap.add_argument("--mode", choices=["direct", "gated", "full"], default="full"); ap.add_argument("--provider", choices=["offline", "gemini", "huggingface", "groq", "deepseek"], default="offline")
    ap.add_argument("--enable-critic", action="store_true", help="Bật escalation critic; offline dùng deterministic acceptance stub")
    ap.add_argument("--resume", action="store_true", help="Tiếp tục từ checkpoint.json trong output directory")
    args = ap.parse_args(); cases = json.loads(Path(args.suite).read_text(encoding="utf-8"))
    llm = GeminiLLMClient() if args.provider == "gemini" else HuggingFaceLLMClient() if args.provider == "huggingface" else GroqLLMClient() if args.provider == "groq" else None
    critic = llm if llm is not None else FakeLLMClient() if args.enable_critic else None
    runtime = AgentRuntime(
        enable_gate=args.mode != "direct", enable_verifier=args.mode == "full",
        llm_client=llm, critic_client=critic, enable_critic=args.enable_critic,
        use_llm_parser=llm is not None, use_llm_generation=llm is not None,
    )
    checkpoint = Path(args.output) / "checkpoint.json"
    rows = json.loads(checkpoint.read_text(encoding="utf-8")).get("rows", []) if args.resume and checkpoint.exists() else []
    crashes = sum(1 for row in rows if "error" in row); completed_pairs = {(row["id"], row["run"]) for row in rows}; stop_reason = None
    for case in cases:
        passes = [row["passed"] for row in rows if row["id"] == case["id"]]
        for run in range(args.runs):
            if (case["id"], run + 1) in completed_pairs: continue
            try:
                response, checks = run_case(case, runtime)
                row = {
                    "id": case["id"], "run": run + 1, "intent": response.request.intent,
                    "action": response.gate.action, "gate_rule_id": response.gate.rule_id,
                    "trace_id": response.trace_id,
                    "planning_mode": response.planning.get("mode", "none"),
                    "plan_id": response.planning.get("plan_id"),
                    "complexity_level": response.planning.get("complexity_level"),
                    "expected_complexity_level": case.get("complexity_level"),
                    "escalation_mode": response.planning.get("escalation_mode"),
                    "parse_fallback": bool(response.llm.get("parse_fallback")),
                    "generation_fallback": bool(response.llm.get("generation", {}).get("fallback")),
                    **checks,
                }
            except Exception as exc:
                import traceback as _traceback
                crashes += 1
                row = {
                    "id": case["id"], "run": run + 1, "passed": False,
                    "error": type(exc).__name__,
                    "error_message": str(exc)[:500],
                    "traceback": "".join(_traceback.format_exception(exc, limit=6))[-2000:],
                }
            rows.append(row); passes.append(row["passed"])
            if runtime.llm_client and any(key.endswith(":429") for key in runtime.llm_client.telemetry().get("error_counts", {})):
                stop_reason = f"{args.provider}_quota_429"; break
        case["pass_all"] = len(passes) == args.runs and all(passes)
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps({"provider": args.provider, "mode": args.mode, "completed_cases": len({r["id"] for r in rows}), "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        if stop_reason: break
    expected_abstain = {c["id"] for c in cases if c["expected_action"] == "abstain"}; actual_abstain = {r["id"] for r in rows if r["run"] == 1 and r.get("action") == "abstain"}
    tp = len(expected_abstain & actual_abstain); precision = div(tp, len(actual_abstain)); recall = div(tp, len(expected_abstain))
    planned = [
        row for row in rows
        if row.get("planning_mode") in {"deterministic_template", "llm_semantic_plan"}
    ]
    plan_ids_by_case = {
        case["id"]: {row.get("plan_id") for row in rows if row["id"] == case["id"] and row.get("plan_id")}
        for case in cases
    }
    stability_cases = [ids for ids in plan_ids_by_case.values() if ids]
    complexity_rows = [row for row in rows if row.get("expected_complexity_level") and row.get("complexity_level")]
    a19_rows = [row for row in rows if str(row.get("gate_rule_id", "")).startswith("A19")]
    expected_a19_rows = [row for row in rows if any(case["id"] == row["id"] and case.get("expected_rule", "").startswith("A19") for case in cases)]
    metrics = {
        "mode": args.mode, "provider": args.provider, "cases": len(cases), "completed_cases": len({r["id"] for r in rows}), "runs": args.runs, "stop_reason": stop_reason,
        "end_to_end_accuracy": div(sum(r["passed"] for r in rows), len(rows)), "pass_pow_runs": div(sum(c.get("pass_all", False) for c in cases), len(cases)),
        "trajectory_accuracy": div(sum(r.get("trajectory", False) for r in rows), len(rows)), "evidence_accuracy": div(sum(r.get("evidence", False) for r in rows), len(rows)),
        "citation_recall": div(sum(r.get("citation_recall", 0) for r in rows), len(rows)), "citation_precision": div(sum(r.get("citation_precision", 0) for r in rows), len(rows)),
        "verifier_pass_rate": div(sum(r.get("verifier", False) for r in rows), len(rows)), "verifier_mutation_detection": div(sum(r.get("mutation_detected", False) for r in rows), len(rows)),
        "parse_fallback_rate": div(sum(r.get("parse_fallback", False) for r in rows), len(rows)), "generation_fallback_rate": div(sum(r.get("generation_fallback", False) for r in rows), len(rows)),
        "routing_accuracy": div(sum(r.get("intent_action", False) for r in rows), len(rows)),
        "a19_rule_accuracy": div(sum(r.get("gate_rule", False) for r in expected_a19_rows), len(expected_a19_rows)) if expected_a19_rows else None,
        "a19_distribution": dict(Counter(r["gate_rule_id"] for r in a19_rows)),
        "a19_plan_fallback_rate": div(sum(r.get("gate_rule_id") == "A19-PLAN" for r in rows), len(rows)),
        "semantic_plan_success_rate": div(sum(bool(r.get("plan_id")) for r in planned), len(planned)) if planned else None,
        "plan_stability_rate": div(sum(len(ids) == 1 for ids in stability_cases), len(stability_cases)) if stability_cases else None,
        "complexity_classification_accuracy": div(sum(r["complexity_level"] == r["expected_complexity_level"] for r in complexity_rows), len(complexity_rows)) if complexity_rows else None,
        "escalation_rate": div(sum(r.get("escalation_mode") in {"critic", "nversion"} for r in rows), len(rows)),
        "abstention_precision": precision, "abstention_recall": recall, "abstention_f1": div(2 * precision * recall, precision + recall), "crash_rate": div(crashes, len(rows)),
        "failures": Counter(r["id"] for r in rows if not r["passed"]),
    }
    if runtime.llm_client and hasattr(runtime.llm_client, "telemetry"):
        telemetry = runtime.llm_client.telemetry(); metrics["llm_telemetry"] = telemetry
        if args.provider == "gemini":
            metrics["estimated_paid_list_cost_usd"] = round(telemetry["prompt_tokens"] * 1.5 / 1_000_000 + telemetry["output_tokens"] * 9.0 / 1_000_000, 6)
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True); stem = out / str(date.today())
    stem.with_suffix(".json").write_text(json.dumps({"metrics": metrics, "rows": rows}, ensure_ascii=False, indent=2, default=dict), encoding="utf-8")
    stem.with_suffix(".md").write_text("# Báo cáo eval V1 end-to-end\n\n" + "\n".join(f"- **{k}:** {v}" for k, v in metrics.items()) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2, default=dict))


if __name__ == "__main__": main()
