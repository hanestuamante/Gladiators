#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path

from gladiators.agent.llm import GeminiLLMClient, GroqLLMClient, HuggingFaceLLMClient
from gladiators.agent.verifier import verify_numeric_claims
from gladiators.agent.workflow import AgentRuntime


def div(a, b): return a / b if b else 0.0


def expected_plan(runtime, intent: str) -> list[str]:
    spec = runtime.registry.get(intent)
    return list(spec.tool_plan) if spec else []


def trajectory_correct(case, response, runtime) -> bool:
    actual = [call.name for call in response.tool_calls]
    if case["expected_action"] == "allow":
        return actual == expected_plan(runtime, case["expected_intent"]) and all(call.status == "ok" for call in response.tool_calls)
    if case["expected_action"] == "abstain":
        return actual == []
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
    return False


def citation_metrics(response) -> tuple[float, float]:
    if not response.evidence: return 1.0, 1.0
    ids = {e.evidence_id for e in response.evidence}
    cited = set(re.findall(r"ev:[a-f0-9]+:\d{4}", response.answer))
    return div(len(ids & cited), len(ids)), div(len(ids & cited), len(cited)) if cited else 0.0


def run_case(case, runtime):
    response = runtime.run(case["question"])
    intent_action = response.request.intent == case["expected_intent"] and response.gate.action == case["expected_action"]
    entity = not case.get("expected_listing_key") or response.resolved_listing_key == case["expected_listing_key"]
    trajectory = trajectory_correct(case, response, runtime)
    evidence = evidence_correct(case, response, runtime)
    citation_recall, citation_precision = citation_metrics(response)
    verifier = bool(response.verification.get("passed"))
    mutation = verify_numeric_claims(response.answer + " Giá trị kiểm tra 987654.321.", response.evidence)
    mutation_detected = runtime.enable_verifier and not mutation["passed"]
    llm_path = runtime.llm_client is None or (not response.llm.get("parse_fallback") and not response.llm.get("generation", {}).get("fallback"))
    passed = all((intent_action, entity, trajectory, evidence, citation_recall == 1.0, citation_precision == 1.0, verifier, mutation_detected, llm_path))
    return response, {"intent_action": intent_action, "entity": entity, "trajectory": trajectory, "evidence": evidence, "citation_recall": citation_recall, "citation_precision": citation_precision, "verifier": verifier, "mutation_detected": mutation_detected, "llm_path": llm_path, "passed": passed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="eval/questions.json"); ap.add_argument("--runs", type=int, default=3); ap.add_argument("--output", default="eval/reports")
    ap.add_argument("--mode", choices=["direct", "gated", "full"], default="full"); ap.add_argument("--provider", choices=["offline", "gemini", "huggingface", "groq"], default="offline")
    ap.add_argument("--resume", action="store_true", help="Tiếp tục từ checkpoint.json trong output directory")
    args = ap.parse_args(); cases = json.loads(Path(args.suite).read_text(encoding="utf-8"))
    llm = GeminiLLMClient() if args.provider == "gemini" else HuggingFaceLLMClient() if args.provider == "huggingface" else GroqLLMClient() if args.provider == "groq" else None
    runtime = AgentRuntime(enable_gate=args.mode != "direct", enable_verifier=args.mode == "full", llm_client=llm, use_llm_parser=llm is not None, use_llm_generation=llm is not None)
    checkpoint = Path(args.output) / "checkpoint.json"
    rows = json.loads(checkpoint.read_text(encoding="utf-8")).get("rows", []) if args.resume and checkpoint.exists() else []
    crashes = sum(1 for row in rows if "error" in row); completed_pairs = {(row["id"], row["run"]) for row in rows}; stop_reason = None
    for case in cases:
        passes = [row["passed"] for row in rows if row["id"] == case["id"]]
        for run in range(args.runs):
            if (case["id"], run + 1) in completed_pairs: continue
            try:
                response, checks = run_case(case, runtime)
                row = {"id": case["id"], "run": run + 1, "intent": response.request.intent, "action": response.gate.action, "trace_id": response.trace_id, "parse_fallback": bool(response.llm.get("parse_fallback")), "generation_fallback": bool(response.llm.get("generation", {}).get("fallback")), **checks}
            except Exception as exc:
                crashes += 1; row = {"id": case["id"], "run": run + 1, "passed": False, "error": type(exc).__name__}
            rows.append(row); passes.append(row["passed"])
            if runtime.llm_client and any(key.endswith(":429") for key in runtime.llm_client.telemetry().get("error_counts", {})):
                stop_reason = f"{args.provider}_quota_429"; break
        case["pass_all"] = len(passes) == args.runs and all(passes)
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps({"provider": args.provider, "mode": args.mode, "completed_cases": len({r["id"] for r in rows}), "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        if stop_reason: break
    expected_abstain = {c["id"] for c in cases if c["expected_action"] == "abstain"}; actual_abstain = {r["id"] for r in rows if r["run"] == 1 and r.get("action") == "abstain"}
    tp = len(expected_abstain & actual_abstain); precision = div(tp, len(actual_abstain)); recall = div(tp, len(expected_abstain))
    metrics = {
        "mode": args.mode, "provider": args.provider, "cases": len(cases), "completed_cases": len({r["id"] for r in rows}), "runs": args.runs, "stop_reason": stop_reason,
        "end_to_end_accuracy": div(sum(r["passed"] for r in rows), len(rows)), "pass_pow_runs": div(sum(c.get("pass_all", False) for c in cases), len(cases)),
        "trajectory_accuracy": div(sum(r.get("trajectory", False) for r in rows), len(rows)), "evidence_accuracy": div(sum(r.get("evidence", False) for r in rows), len(rows)),
        "citation_recall": div(sum(r.get("citation_recall", 0) for r in rows), len(rows)), "citation_precision": div(sum(r.get("citation_precision", 0) for r in rows), len(rows)),
        "verifier_pass_rate": div(sum(r.get("verifier", False) for r in rows), len(rows)), "verifier_mutation_detection": div(sum(r.get("mutation_detected", False) for r in rows), len(rows)),
        "parse_fallback_rate": div(sum(r.get("parse_fallback", False) for r in rows), len(rows)), "generation_fallback_rate": div(sum(r.get("generation_fallback", False) for r in rows), len(rows)),
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
