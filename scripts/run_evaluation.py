#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))


def _pin_dataset_early() -> str:
    """Ghim bản dữ liệu TRƯỚC khi import gladiators, hoặc từ chối chạy.

    Phải ở đây, không ở trong ``main()``: ``data.repository.DEFAULT_DATA_DIR``
    đọc môi trường lúc NẠP MODULE. Đặt biến sau khi import thì nó không có tác
    dụng gì, và lượt chạy im lặng dùng bản đang phục vụ — đúng cái bẫy file này
    sinh ra để đóng. `tests/conftest.py` đã phải làm cùng một việc, cùng lý do.

    Vì sao phải khai: cùng một mã nguồn, cùng ngày 01/09/2026, `questions_v2`
    cho **0.455** trên bộ 20 ngày và **1.000** trên bộ 3 ngày. Chênh lệch đó
    không phải năng lực đổi — nó là bộ đề đang mô tả một bản dữ liệu khác với
    bản đang chạy. Trước khi ghim, 0.455 bị đọc thành "hệ kém đi", và nó che
    một `over_answer_rate = 0.125` THẬT suốt một phiên.
    """
    import json as _json
    import os as _os

    argv = sys.argv[1:]

    def _flag(name: str) -> str | None:
        if name in argv:
            index = argv.index(name)
            return argv[index + 1] if index + 1 < len(argv) else None
        for item in argv:
            if item.startswith(name + "="):
                return item.split("=", 1)[1]
        return None

    override = _flag("--data-dir")
    if override:
        _os.environ["GLADIATORS_DATA_DIR"] = override
        return f"[dataset] ghi đè: {override}"

    root = _Path(__file__).resolve().parents[1]
    registry = _json.loads(
        (root / "eval" / "suite_datasets.json").read_text(encoding="utf-8"),
    )
    name = _Path(_flag("--suite") or "eval/questions.json").name
    root_name = registry["suites"].get(name)
    if root_name is None:
        raise SystemExit(
            f"Bộ đề {name!r} chưa khai bản dữ liệu nó mô tả. Thêm vào "
            "eval/suite_datasets.json — một phép kiểm không nói rõ nó nói về "
            "cái gì thì không phải một phép kiểm.",
        )
    spec = registry["roots"][root_name]
    data_dir = root / spec["data_dir"]
    if not data_dir.exists():
        raise SystemExit(f"Bản dữ liệu {data_dir} không tồn tại.")
    _os.environ["GLADIATORS_DATA_DIR"] = str(data_dir)
    index_path = root / spec["value_index"] if spec.get("value_index") else None
    if index_path is not None and index_path.exists():
        _os.environ["GLADIATORS_VALUE_INDEX"] = str(index_path)
    return f"[dataset] {name} mô tả bản {root_name!r} → {data_dir}"


_DATASET_BANNER = _pin_dataset_early()

from gladiators.evalkit.metrics import compute_selective_metrics  # noqa: E402

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

    # W9.1: MỘT hàm chung cho cả hai script — hai bản là lý do hai công thức
    # trôi khỏi nhau, và cùng cái tên "coverage" từng mang hai mẫu số (§1.3).
    metrics = compute_selective_metrics(
        answerable=answerable, unanswerable=unanswerable,
        answered=answered, refused=refused, correct=correct,
        unscored_answered=unscored_answered,
    )
    return {
        "selective_unlabelled_cases": unlabelled,
        **metrics,
        # Một chu kỳ tương thích cho consumer đọc khoá cũ; giá trị LÀ
        # answerable_coverage (nghĩa cũ của script này).
        "coverage": metrics["answerable_coverage"],
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
    # Intent KHÔNG sinh evidence theo thiết kế: câu trả lời là một phát biểu về
    # REGISTRY, không phải về dữ liệu, nên không có con số nào cần chống lưng
    # (A7-R2). Đòi nó có evidence là đòi một thứ nó cố ý không tạo ra, và cả 8
    # ca của `questions_schema` trượt vì luật chấm rơi thẳng xuống nhánh
    # fail-closed cuối hàm.
    if case["expected_intent"] in {"schema_relation_explain"}:
        return response.evidence == []
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


def run_multiturn_case(case, runtime):
    """Case nhiều lượt — WP-A3. Mọi lượt dùng CÙNG session_id.

    Trả về lượt CUỐI cùng, vì đó là lượt mang câu trả lời đang được đo; các lượt
    trước chỉ xác lập ngữ cảnh. Verdict từng lượt vẫn được ghi lại để phân biệt
    "lượt 2 đúng" với "lượt 1 đã đúng sẵn nên lượt 2 chẳng chứng minh gì".
    """
    runtime.conversations.reset(case["session_id"])
    responses = [
        runtime.run(turn["question"], session_id=case["session_id"])
        for turn in case["turns"]
    ]
    final_turn, final = case["turns"][-1], responses[-1]
    recovered = (
        final_turn.get("expected_action_without_memory") == "clarify"
        and final.gate.action == "allow"
        and bool(final.evidence)
    )
    if recovered and final_turn.get("expected_value"):
        # Một bộ nhớ điền BỪA cũng làm lượt cuối thành allow. Chỉ oracle mới phân
        # biệt được điền đúng với điền bừa, nên giá trị sai KHÔNG tính là cứu.
        values = {float(item.value) for item in final.evidence
                  if isinstance(item.value, (int, float)) and not isinstance(item.value, bool)}
        recovered = any(
            any(abs(value - float(expected)) < 0.5 for value in values)
            for expected in final_turn["expected_value"].values()
            if expected is not None
        )
    checks = {
        "scoreable": True,
        "passed": final.gate.action == final_turn.get("expected_action"),
        "turn_actions": [item.gate.action for item in responses],
        "clarify_without_memory": final_turn.get("expected_action_without_memory"),
        "clarify_recovered": recovered,
    }
    return final, checks



PRICING_PATH = Path(__file__).resolve().parents[1] / "eval" / "pricing.json"


def load_pricing() -> dict:
    if not PRICING_PATH.exists():
        return {}
    try:
        return json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _flatten_telemetry(telemetry: dict | None) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from run_cost_report import flatten_telemetry

    return flatten_telemetry(telemetry)


def estimate_cost(provider: str, telemetry: dict) -> float | str:
    """USD ước tính, hoặc ``"n/a"`` khi chưa có đơn giá được xác nhận.

    B10-R2: không đoán. Một con số chi phí bịa ra còn tệ hơn không có con số nào,
    vì nó sẽ được trích dẫn.
    """
    telemetry = _flatten_telemetry(telemetry)
    entry = load_pricing().get(provider) or {}
    prompt_rate, output_rate = entry.get("prompt_usd_per_1m"), entry.get("output_usd_per_1m")
    if prompt_rate is None or output_rate is None or not entry.get("as_of"):
        return "n/a"
    return round(
        telemetry.get("prompt_tokens", 0) * float(prompt_rate) / 1_000_000
        + telemetry.get("output_tokens", 0) * float(output_rate) / 1_000_000,
        6,
    )


def run_case(case, runtime):
    if case.get("turns"):
        return run_multiturn_case(case, runtime)
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
    ap.add_argument("--data-dir", default=None, help="Ghi đè bản dữ liệu; mặc định lấy theo khai báo ở eval/suite_datasets.json")
    args = ap.parse_args(); cases = json.loads(Path(args.suite).read_text(encoding="utf-8"))
    # Một số bộ đề (p0_probes, dr2607) gói case trong {"cases": [...]} kèm
    # schema_version. Trước đây harness đọc thẳng và chết bằng TypeError ở tận
    # vòng lặp, cách xa nguyên nhân.
    if isinstance(cases, dict):
        cases = cases.get("cases", [])
    # Case chưa có câu hỏi là một CHỖ TRỐNG chờ người quyết (p0-tc19/tc23/tc34),
    # không phải một phép đo thất bại. Chấm nó thành crash làm crash_rate 0.333
    # trên một bộ mà hệ thống không hề hỏng — và một chỉ số báo hỏng khi không
    # hỏng sẽ bị bỏ qua đúng lúc nó báo thật.
    placeholders = [
        case["id"] for case in cases
        if not case.get("question") and not case.get("turns")
    ]
    cases = [case for case in cases if case.get("question") or case.get("turns")]
    # `deepseek` nằm trong --provider choices nhưng trước đây không có nhánh nào
    # dựng client, nên nó rơi vào `else None`: runner chạy 100% offline rồi ghi
    # report mang nhãn "provider": "deepseek". Một phép đo trông như đã đo mà
    # không gọi model lần nào là thứ tệ hơn không đo (§5.1 luật 2).
    _CLIENTS = {
        "gemini": GeminiLLMClient, "huggingface": HuggingFaceLLMClient,
        "groq": GroqLLMClient, "deepseek": DeepSeekLLMClient,
    }
    print(_DATASET_BANNER)
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
                    # Ba vòng lặp rẻ của WP-A5. Không có ba khoá này thì "vòng
                    # nào cứu được bao nhiêu câu" không đo được, và một vòng
                    # không bao giờ bắn trông giống hệt một vòng bắn mà vô ích.
                    "loop_value_probe": bool(response.planning.get("value_probe")),
                    "loop_context_relax": bool(
                        (response.planning.get("context_relax") or {}).get("attempted"),
                    ),
                    "loop_wording_repair": bool(
                        (response.planning.get("wording_repair") or {}).get("passed"),
                    ),
                    "loop_empty_result": bool(response.planning.get("empty_result")),
                    # W13.3: nếu W13.1 đúng thì cột này bằng 0 trên mọi suite —
                    # và một số 0 ĐO ĐƯỢC khác hẳn một nhánh không ai biết có
                    # chạy hay không.
                    "execution_failed": bool(response.planning.get("execution_error")),
                    # WP-B10 cần "? giây" cạnh "? USD"; timing đã có từ WP-A6 nên
                    # đây chỉ là chuyển nó ra tới bảng chi phí.
                    "seconds": round(
                        float((response.planning.get("timing") or {}).get("total", 0.0)) / 1000, 4,
                    ),
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
    # .get, không [] — bộ đề kiểu scenario_acceptance cố ý không khai
    # expected_action (xem run_case: scoring_mode="action_rule_only").
    expected_abstain = {c["id"] for c in cases if c.get("expected_action") == "abstain"}; actual_abstain = {r["id"] for r in rows if r["run"] == 1 and r.get("action") == "abstain"}
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
    first_run = [row for row in rows if row["run"] == 1]
    # WP-A3: trong số case mà lượt cuối RA clarify khi hỏi một mình, tỷ lệ case
    # mà bộ nhớ lật được nó thành allow kèm evidence ĐÚNG ORACLE.
    recovery_rows = [
        row for row in first_run if row.get("clarify_without_memory") == "clarify"
    ]
    clarify_recovery_rate = div(
        sum(1 for row in recovery_rows if row.get("clarify_recovered")),
        len(recovery_rows),
    )
    cheap_loops = {
        name: sum(1 for row in first_run if row.get(f"loop_{name}"))
        for name in ("value_probe", "context_relax", "wording_repair", "empty_result")
    }
    execution_error_fired = sum(1 for row in first_run if row.get("execution_failed"))
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
        "abstention_precision": precision, "abstention_recall": recall, "abstention_f1": div(2 * precision * recall, precision + recall), "crash_rate": div(crashes, len(rows)), "cheap_loops_fired": cheap_loops, "execution_error_fired": execution_error_fired,
        "provider": args.provider,
        "median_seconds": (
            round(statistics.median([row["seconds"] for row in first_run if row.get("seconds")]), 4)
            if any(row.get("seconds") for row in first_run) else None
        ),
        "clarify_recovery_rate": clarify_recovery_rate,
        "clarify_recovery_cases": len(recovery_rows),
        "placeholder_cases": placeholders,
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
        # B10-R1/B10-R2: đơn giá đọc từ eval/pricing.json, và provider không có
        # đơn giá thì KHÔNG ước lượng. Trước đây hai con số 1.5/9.0 nằm thẳng
        # trong dòng này và chỉ áp cho gemini — một đơn giá hard-code không có
        # as_of sẽ âm thầm sai sau lần đổi giá đầu tiên.
        metrics["estimated_paid_list_cost_usd"] = estimate_cost(
            args.provider, telemetry,
        )
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True); stem = out / str(date.today())
    stem.with_suffix(".json").write_text(json.dumps({"metrics": metrics, "rows": rows}, ensure_ascii=False, indent=2, default=dict), encoding="utf-8")
    stem.with_suffix(".md").write_text("# Báo cáo eval V1 end-to-end\n\n" + "\n".join(f"- **{k}:** {v}" for k, v in metrics.items()) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2, default=dict))


if __name__ == "__main__": main()
