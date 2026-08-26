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

from gladiators.agent.llm import (
    DeepSeekLLMClient,
    FakeLLMClient,
    GeminiLLMClient,
    GroqLLMClient,
    HuggingFaceLLMClient,
)
from gladiators.agent.verifier import verify_numeric_claims
from gladiators.agent.workflow import AgentRuntime


INDEPENDENT_GOLDEN = json.loads(
    (Path(__file__).resolve().parents[1] / "eval" / "independent" / "golden_v2.json").read_text(encoding="utf-8")
)


def div(a, b): return a / b if b else 0.0


# --- WP-B1 · chỉ số dự đoán có chọn lọc -----------------------------------
# Một hệ được phép nói "không biết" phải được chấm bằng ĐỘ PHỦ và RỦI RO, không
# phải bằng một tỷ lệ pass duy nhất. Chỉ số từ chối cũ chỉ đếm `abstain`, nên
# `clarify` -- 32% bộ đề chính, 52,5% của DR-40 -- nằm ngoài toàn bộ phép đo:
# một câu TRẢ LỜI ĐƯỢC mà hệ trả `clarify` không rơi vào chỉ số nào cả.

REFUSAL_ACTIONS = frozenset({"clarify", "abstain"})


def majority_action(rows: list[dict], case_id: str) -> str | None:
    """Hành động thắng đa số qua các lần chạy, không phải hành động của run 1.

    Lấy `run == 1` là lấy một mẫu, không phải lấy hành vi. Hoà thì trả hành động
    của lần chạy sớm nhất trong nhóm hoà — có tie-break tất định còn hơn để thứ
    tự dict quyết định.
    """
    actions = [r.get("action") for r in rows if r["id"] == case_id and r.get("action")]
    if not actions:
        return None
    counts = Counter(actions)
    best = max(counts.values())
    for action in actions:                       # thứ tự xuất hiện = tie-break
        if counts[action] == best:
            return action
    return None


def action_stability_rate(rows: list[dict]) -> float:
    """Tỷ lệ case cho cùng một `action` ở MỌI lần chạy.

    Một hệ không ổn định về `action` là một hệ mà mọi chỉ số khác đều mất nghĩa,
    nên con số này phải đứng cạnh chúng chứ không nằm trong phần phụ lục.
    """
    by_case: dict[str, set] = {}
    for row in rows:
        if row.get("action"):
            by_case.setdefault(row["id"], set()).add(row["action"])
    return div(sum(len(v) == 1 for v in by_case.values()), len(by_case))


def _answerable(case: dict) -> bool | None:
    """§B1.2. Khai tường minh thắng luật suy diễn. ``None`` = CHƯA GÁN NHÃN.

    Luật suy diễn đúng THEO ĐỊNH NGHĨA với bộ tự viết, vì chúng được viết cùng
    lúc với bộ luật -- và chính vì thế `over_refusal_rate` trên bộ tự viết LUÔN
    bằng 0. Con số đó chỉ có nghĩa trên bộ đề độc lập (WP-B3).

    DR-40 cố ý để `expected_action = null` ở 19/40 case (nhóm "từ chối là đúng"
    chưa có oracle người duyệt). ``None`` nghĩa là CHƯA BIẾT, không phải "không
    trả lời được" -- gộp chúng vào nhóm không-answerable sẽ bịa ra 19 nhãn.
    """
    if "answerable" in case:
        return bool(case["answerable"])
    expected = case.get("expected_action")
    return None if expected is None else expected == "allow"


def selective_metrics(cases: list[dict], rows: list[dict]) -> dict[str, float]:
    labelled = {c["id"]: _answerable(c) for c in cases if _answerable(c) is not None}
    answerable = {cid for cid, flag in labelled.items() if flag}
    unanswerable = {cid for cid, flag in labelled.items() if not flag}
    unlabelled = len(cases) - len(labelled)

    answered, refused, correct = set(), set(), set()
    unscored_answered: set[str] = set()
    for case in cases:
        cid = case["id"]
        action = majority_action(rows, cid)
        if action in REFUSAL_ACTIONS:
            refused.add(cid)
            continue
        if action != "allow":
            continue
        allow_rows = [r for r in rows if r["id"] == cid and r.get("action") == "allow"]
        # `allow` mà không có evidence thì chưa trả lời được gì.
        if not any(r.get("evidence_count", 0) for r in allow_rows):
            continue
        answered.add(cid)
        scored = [r for r in allow_rows if r.get("passed") is not None]
        if scored and all(r["passed"] for r in scored):
            correct.add(cid)
        elif not scored:
            unscored_answered.add(cid)   # không biết đúng/sai, không được tính là sai

    def rate(numerator: int, denominator: int) -> float | None:
        """``None`` khi mẫu số rỗng — KHÔNG phải 0.0.

        `CLAUDE.md` §3.1: điền 0 làm "không đo được" trông giống hệt "đo được và
        bằng 0". Một suite không có case answerable (`questions_a19`,
        `questions_ambiguity`) mà báo `coverage = 0.0` sẽ đọc thành "hệ không
        phủ được gì", trong khi sự thật là không có gì để phủ.
        """
        return numerator / denominator if denominator else None

    # Mọi chỉ số chỉ tính trên case CÓ NHÃN. Để case chưa gán nhãn nằm trong mẫu
    # số của `refusal_precision` làm con số đó tụt mà không có nghĩa gì: 19 case
    # DR-40 bị từ chối nhưng chưa ai nói chúng đáng lẽ trả lời được hay không.
    answered &= labelled.keys()
    refused &= labelled.keys()
    correct &= labelled.keys()
    unscored_answered &= labelled.keys()

    return {
        "selective_unlabelled_cases": unlabelled,
        "coverage": rate(len(answered & answerable), len(answerable)),
        # Chỉ chấm rủi ro trên câu đã trả lời VÀ chấm được đúng/sai. Gộp câu
        # chưa chấm được vào tử số là biến "chưa biết" thành "sai".
        "risk": rate(len(answered - correct - unscored_answered),
                     len(answered - unscored_answered)),
        "over_refusal_rate": rate(len(refused & answerable), len(answerable)),
        "over_answer_rate": rate(len(answered & unanswerable), len(unanswerable)),
        "refusal_precision": rate(len(refused & unanswerable), len(refused)),
        "refusal_recall": rate(len(refused & unanswerable), len(unanswerable)),
    }


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
    # Oracle declared in the fixture, for capabilities the branches below do not
    # enumerate (open_analytical had no scoring path at all and fell through to
    # the fail-closed ``return False``). Cases without the key are unaffected.
    if "expected_evidence" in case:
        actual = {e.metric: e.value for e in response.evidence}
        expected = case["expected_evidence"]
        return set(actual) == set(expected) and all(
            math.isclose(float(actual[metric]), float(value), rel_tol=1e-6, abs_tol=1e-6)
            for metric, value in expected.items()
        )
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
        country = response.request.country; snapshots = runtime.repo.snapshots.query("country_code == @country").copy(); latest = snapshots.loc[snapshots.date.astype(str) == snapshots.date.astype(str).max()].drop_duplicates("product_listing_key")
        # Theme C: the count covers the whole scope, the aggregates only the rows
        # where the sold proxy is measurable. The oracle used one filtered frame
        # for both, so it certified 551/77 -- the answer to a question with an
        # extra condition nobody asked for.
        expected = {}
        for flag, group in latest.groupby("has_structured_voucher", observed=True):
            label = "with_voucher" if bool(flag) else "without_voucher"
            measurable = group.loc[group.monthly_sold_value_num.notna()]
            expected.update({f"{label}_listing_count": len(group), f"{label}_mean_monthly_sold_proxy": measurable.monthly_sold_value_num.mean(), f"{label}_median_monthly_sold_proxy": measurable.monthly_sold_value_num.median()})
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
    # DR-40 dùng schema khác (`legacy_expected_intent`, `expected_action` nullable
    # ở 19/40 case chưa có oracle người duyệt). Trước đây `case["expected_intent"]`
    # ném KeyError, bị nuốt thành `passed: false`, và harness in ra
    # `end_to_end_accuracy = 0.0` -- một con số TRÔNG NHƯ phép đo trong khi thật
    # ra là 120/120 row lỗi đọc suite. Đúng bẫy `CLAUDE.md` §5.1 luật 2.
    #
    # Case không đủ nhãn thì KHÔNG chấm, chứ không chấm trượt.
    expected_intent = case.get("expected_intent") or case.get("legacy_expected_intent")
    expected_action = case.get("expected_action")
    if expected_action is None:
        return response, {
            "scoreable": False, "passed": None,
            "unscoreable_reason": "expected_action chưa gán nhãn",
        }
    if expected_intent is None:
        # Suite kiểu DR-40: có `expected_action` + `allowed_rule_ids` nhưng KHÔNG
        # có nhãn intent. Chấm theo hành động và mã rule -- đó là hợp đồng mà
        # suite này thật sự khai. Bỏ qua nó vì thiếu một nhãn KHÁC là vứt đi 21
        # case đo được.
        allowed = case.get("allowed_rule_ids") or []
        forbidden = case.get("forbidden_rule_ids") or []
        rule_id = response.gate.rule_id
        action_ok = response.gate.action == expected_action
        rule_ok = (rule_id in allowed if allowed else True) and rule_id not in forbidden
        return response, {
            "scoreable": True, "scoring_mode": "action_rule_only",
            "intent_action": action_ok, "gate_rule": rule_ok,
            "passed": action_ok and rule_ok,
        }
    case = {**case, "expected_intent": expected_intent}
    intent_action = response.request.intent == expected_intent and response.gate.action == expected_action
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
    return response, {"scoreable": True, "intent_action": intent_action, "gate_rule": gate_rule, "entity": entity, "trajectory": trajectory, "evidence": evidence, "citation_recall": citation_recall, "citation_precision": citation_precision, "verifier": verifier, "mutation_detected": mutation_detected, "llm_path": llm_path, "passed": passed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="eval/questions.json"); ap.add_argument("--runs", type=int, default=3); ap.add_argument("--output", default="eval/reports")
    ap.add_argument("--mode", choices=["direct", "gated", "full"], default="full"); ap.add_argument("--provider", choices=["offline", "gemini", "huggingface", "groq", "deepseek"], default="offline")
    ap.add_argument("--enable-critic", action="store_true", help="Bật escalation critic; offline dùng deterministic acceptance stub")
    ap.add_argument("--resume", action="store_true", help="Tiếp tục từ checkpoint.json trong output directory")
    args = ap.parse_args(); cases = json.loads(Path(args.suite).read_text(encoding="utf-8"))
    # `deepseek` nằm trong --provider choices nhưng trước đây không có nhánh nào
    # dựng client, nên nó rơi vào `else None`: runner chạy 100% offline rồi ghi
    # report mang nhãn "provider": "deepseek". Một phép đo trông như đã đo mà
    # không gọi model lần nào là thứ tệ hơn không đo (§5.1 luật 2).
    _CLIENTS = {
        "gemini": GeminiLLMClient, "huggingface": HuggingFaceLLMClient,
        "groq": GroqLLMClient, "deepseek": DeepSeekLLMClient,
    }
    llm = _CLIENTS[args.provider]() if args.provider in _CLIENTS else None
    if args.provider != "offline" and llm is None:
        raise SystemExit(f"Provider {args.provider} không dựng được client; từ chối chạy offline dưới nhãn đó.")
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
                    "evidence_count": len(response.evidence),
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
    # Row không chấm được không được lẫn vào mẫu số của accuracy: chia cho
    # chúng là biến "chưa đo" thành "đo được và trượt".
    scoreable_rows = [r for r in rows if r.get("scoreable") is not False and "error" not in r]
    metrics = {
        "mode": args.mode, "provider": args.provider, "cases": len(cases), "completed_cases": len({r["id"] for r in rows}), "runs": args.runs, "stop_reason": stop_reason,
        "end_to_end_accuracy": (sum(bool(r["passed"]) for r in scoreable_rows) / len(scoreable_rows)) if scoreable_rows else None, "pass_pow_runs": div(sum(c.get("pass_all", False) for c in cases), len(cases)),
        "unscoreable_rows": len(rows) - len(scoreable_rows),
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
        # WP-B1: cặp abstention_* ở trên chỉ đếm `abstain` nên mù hoàn toàn
        # với `clarify`. Giữ chúng để so chuỗi thời gian (B1-R1), thêm sáu
        # chỉ số dưới đây để đo đúng thứ hệ đang làm.
        **selective_metrics(cases, rows),
        "action_stability_rate": action_stability_rate(rows),
        "selective_metrics_caveat": (
            "over_refusal_rate tren bo tu viet LUON bang 0 vi nhan answerable "
            "duoc suy ra tu expected_action (Spec2308 B1.2). Chi so nay chi co "
            "nghia tren bo de doc lap (WP-B3)."
        ),
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
