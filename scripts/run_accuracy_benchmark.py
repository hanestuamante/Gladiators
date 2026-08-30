#!/usr/bin/env python3
"""Harness + scorer nghiêm ngặt cho benchmark accuracy v1 (TC_formulation §8-§10).

Nguyên tắc chấm — không có "một số khớp là pass":
- một case allow chỉ strict-pass khi action đúng, MỌI expected fact khớp đúng
  metric/type/value-tolerance/unit/country/date, fact hiển thị trong câu trả
  lời cuối, verifier pass, không crash;
- metric khác nhưng tình cờ cùng số là FAIL (map ngữ nghĩa tường minh, không
  đoán theo giá trị);
- clarify phải hỏi ĐÚNG slot thiếu; unanswerable phải từ chối đúng NHÓM lý do;
- mẫu số rỗng ⇒ null, không phải 0.0; báo tử số/mẫu số và Wilson 95% CI.

    PYTHONPATH=src python scripts/run_accuracy_benchmark.py --split dev
    PYTHONPATH=src python scripts/run_accuracy_benchmark.py --split holdout --runs 3
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
BENCH = REPO / "eval" / "accuracy" / "v1"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCORER_VERSION = "accuracy-scorer.v1"

# ── adapter: metric benchmark → tên metric evidence của runtime ──────────────
# Map NGỮ NGHĨA khai tường minh (Giai đoạn B được đọc impl); không map theo giá
# trị. Một fact không tìm thấy metric đã map là FAIL, kể cả khi con số xuất
# hiện ở một metric khác.
METRIC_MAP: dict[str, tuple[str, ...]] = {
    "listing_count": ("listing_count",),
    "shop_count": ("shop_count",),
    "brand_count": ("brand_count",),
    "median_price": ("price",),
    "median_rating": ("rating",),
    "mean_images": ("images_count",),
    "total_likes": ("liked_count",),
    "max_price": ("price",),
    "min_price": ("price",),
    "max_price_excl_placeholder": ("price",),
    "max_likes": ("liked_count",),
    "max_rating_count": ("rating_count",),
    "max_images": ("images_count",),
    "tie_count": ("tie_count",),          # thường không có — xử riêng bên dưới
    "product_name": ("product_name",),
    "shop_name": ("shop_name",),
    "brand": ("brand",),
    "discounted_ratio_percent": ("discounted_listing_rate",),
    "count_start": ("product_count_start", "listing_count_start"),
    "count_end": ("product_count_end", "listing_count_end"),
    "count_delta": ("product_count_delta", "listing_count_delta"),
    "price": ("price",),
    "rating": ("rating",),
    "rating_count": ("rating_count",),
    "count_a": ("listing_count",),
    "count_b": ("listing_count",),
    "winner": ("shop_name", "brand"),
    "discounted_count": ("discounted_listing_count",),
}

# Aggregate benchmark metric → aggregation mà evidence PHẢI khai (W5.1 ghi
# attrs["aggregation"]) — median trả cho câu mean là sai metric, không phải sai số.
REQUIRED_AGGREGATION = {
    "median_price": "median", "median_rating": "median",
    "mean_images": "mean", "total_likes": "sum",
}

# rule_id runtime → nhóm lý do từ chối của benchmark.
REFUSAL_CLASS_BY_RULE = {
    "A-MISSING-PROFIT": "missing_field",
    "A-MISSING-INVENTORY": "missing_field",
    "A-MISSING-ADS": "missing_field",
    "A-MISSING-CONVERSION": "missing_field",
    "A-MISSING-TRAFFIC": "missing_field",
    "A-DATA-ABSENT": "missing_field",
    "A19-CAT": "missing_field",
    "A-MISSING-SKU": "missing_grain",
    "A-MISSING-ORDERS": "missing_grain",
    "A19-GRAIN": "missing_grain",
    "A-MISSING-FORECAST": "forecast_unsupported",
    "A16-CROSS-CURRENCY": "cross_currency",
    "A-CROSS-CURRENCY-SCOPE": "cross_currency",
    "A-MISSING-REFERENCE": "cross_currency",
    "A22-ALIGN-DATE": "date_out_of_range",
    "A-SNAPSHOT-SCOPE": "date_out_of_range",
    "A-INSUFFICIENT-SNAPSHOTS": "date_out_of_range",
    "A22-ALIGN-PREMISE": "false_premise",
    "A14-EXT": "external_data",
    "A-MISSING-EXTERNAL": "external_data",
    "A19-VALUE-CLASS": "data_quality_suspect",
}

# slot clarify → từ khoá mà câu hỏi lại PHẢI chạm tới (đo clarification_precision).
SLOT_CUES = {
    "country": ("thị trường", "quốc gia", "việt nam", "indonesia", "vn", "id",
                "country", "nước", "negara"),
    "voucher_definition": ("voucher",),
    "ranking_metric": ("theo", "tiêu chí", "metric", "chỉ số", "listing",
                       "follower", "doanh"),
    "entity_disambiguation": ("nào", "cụ thể", "which", "chọn", "listing",
                              "sản phẩm", "shop"),
    "definition_threshold": ("định nghĩa", "ngưỡng", "thế nào là", "tiêu chí",
                             "bán chạy"),
    "group_dimension": ("nhóm", "theo", "chiều", "group"),
    "metric": ("chỉ số", "số liệu", "metric", "giá", "rating", "listing",
               "muốn biết"),
}


def _norm_text(text: str) -> str:
    import unicodedata

    lowered = str(text).lower().replace("đ", "d")
    stripped = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in stripped if unicodedata.category(ch) != "Mn")


def _number_in_text(value: float, text: str) -> bool:
    """Giá trị có HIỂN THỊ trong câu trả lời không — chấp nhận mọi kiểu nhóm
    nghìn/thập phân và làm tròn hiển thị tới 2 chữ số."""
    cleaned = re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", text)
    tokens = re.findall(r"-?\d+(?:[.,]\d+)?", cleaned)
    for token in tokens:
        try:
            shown = float(token.replace(",", "."))
        except ValueError:
            continue
        decimals = len(token.split(",")[-1].split(".")[-1]) if ("." in token or "," in token) else 0
        if abs(shown - round(float(value), decimals)) < 10 ** (-decimals) / 2 + 1e-9:
            return True
        if abs(shown - float(value)) < 1e-9:
            return True
    return False


def _fact_matches(fact: dict, response) -> tuple[bool, str]:
    """Một expected fact khớp evidence + câu trả lời theo TOÀN BỘ chiều ngữ nghĩa."""
    metric = fact["metric"]
    candidates = METRIC_MAP.get(metric)
    if candidates is None:
        return False, f"scorer chưa map metric {metric}"
    # Map NGỮ CẢNH: đếm listing có voucher cấu trúc có thể được trả qua macro
    # promo dưới tên with_voucher_listing_count — cùng đại lượng, khác tên; chỉ
    # chấp nhận khi fact THẬT SỰ khai bộ lọc structured_voucher.
    if metric == "listing_count" and "structured_voucher=true" in (
        fact.get("filters") or ()
    ):
        candidates = candidates + ("with_voucher_listing_count",)
    matched = [item for item in response.evidence if item.metric in candidates]
    required_aggregation = REQUIRED_AGGREGATION.get(metric)
    if required_aggregation:
        matched = [
            item for item in matched
            if item.attrs.get("aggregation") == required_aggregation
        ]
        if not matched:
            return False, (
                f"{metric}: không evidence nào mang aggregation="
                f"{required_aggregation} (median-trả-cho-mean là sai metric)"
            )
    if not matched:
        return False, f"{metric}: không có evidence metric ∈ {candidates}"

    expected = fact["value"]
    tolerance = fact.get("tolerance") or {"kind": "exact", "value": 0}

    def value_ok(actual) -> bool:
        if fact["value_type"] == "string":
            return _norm_text(str(actual)) == _norm_text(str(expected))
        try:
            actual_number = float(actual)
        except (TypeError, ValueError):
            return False
        if tolerance["kind"] == "exact":
            return actual_number == float(expected)
        if tolerance["kind"] == "absolute":
            return abs(actual_number - float(expected)) <= tolerance["value"]
        return abs(actual_number - float(expected)) <= abs(float(expected)) * tolerance["value"]

    scoped = []
    for item in matched:
        if fact.get("country") and item.attrs.get("country") not in (
            fact["country"], None,
        ):
            continue
        observed = str(item.attrs.get("observed_date") or item.attrs.get("date") or "")
        if observed and not (fact["date_start"] <= observed <= fact["date_end"]):
            continue
        scoped.append(item)
    if not scoped:
        return False, f"{metric}: evidence đúng tên nhưng sai country/date scope"
    hit = next((item for item in scoped if value_ok(item.value)), None)
    if hit is None:
        got = [item.value for item in scoped][:3]
        return False, f"{metric}: kỳ vọng {expected!r}, evidence có {got!r}"
    # Fact phải HIỂN THỊ trong câu trả lời cuối, không chỉ nằm trong evidence.
    if fact["value_type"] == "string":
        if _norm_text(str(expected)) not in _norm_text(response.answer or ""):
            return False, f"{metric}: giá trị chuỗi không xuất hiện trong answer"
    else:
        if not _number_in_text(float(expected), response.answer or ""):
            return False, f"{metric}: con số không hiển thị trong answer"
    # Citation: evidence khớp phải được trích dẫn trong answer.
    if hit.evidence_id and f"[{hit.evidence_id}]" not in (response.answer or ""):
        return False, f"{metric}: evidence khớp không được trích dẫn trong answer"
    return True, ""


def score_case(case: dict, responses: list, tables=None) -> dict:
    """Chấm một case trên MỘT run (danh sách response theo lượt)."""
    response = responses[-1]
    action = response.gate.action
    rule_id = response.gate.rule_id
    # Case có turns: hành vi của TỪNG lượt chấm theo kỳ vọng của lượt đó (lượt
    # một của case clarify phải clarify; lượt cuối sau bổ sung phải allow) —
    # action cấp case chỉ áp cho case một lượt. Thiếu nhánh này, một case
    # clarify-rồi-phục-hồi bị chấm "allow ∉ [clarify]" ở lượt cuối: scorer tự
    # bịa một lỗi không tồn tại.
    turns_spec = case.get("turns")
    if turns_spec:
        first_expected = turns_spec[0].get("expected_action")
        final_expected = turns_spec[-1].get("expected_action") or case["expected_action"]
        effective_accepted = [final_expected]
    else:
        effective_accepted = case.get("accepted_actions", [case["expected_action"]])
    row = {
        "id": case["id"], "split": case["split"],
        "answerability": case["answerability"],
        "action": action, "rule_id": rule_id,
        "expected_action": case["expected_action"],
        "strict_pass": False, "reasons": [], "crash": False,
    }
    reasons = row["reasons"]

    if action not in effective_accepted:
        reasons.append(f"action {action} ∉ accepted {effective_accepted}")
        return row
    if turns_spec and first_expected and responses[0].gate.action != first_expected:
        reasons.append(
            f"lượt một ra {responses[0].gate.action} ≠ {first_expected}"
        )
        return row

    if case["answerability"] == "directly_answerable":
        if action == "allow":
            if not (response.verification or {}).get("passed"):
                reasons.append("verifier không pass")
            for fact in case["expected_facts"]:
                if fact["metric"] == "tie_count":
                    continue  # hoà xử riêng bên dưới
                ok, why = _fact_matches(fact, response)
                if not ok:
                    reasons.append(why)
            for forbidden in case.get("forbidden_values", ()):
                if _number_in_text(float(forbidden), response.answer or "") or any(
                    isinstance(item.value, (int, float))
                    and float(item.value) == float(forbidden)
                    for item in response.evidence
                ):
                    reasons.append(f"giá trị bị cấm {forbidden} xuất hiện")
            tie_fact = next(
                (f for f in case["expected_facts"] if f["metric"] == "tie_count"), None,
            )
            if tie_fact and tie_fact["value"] and int(tie_fact["value"]) > 1:
                # Hoà thật: answer không được nêu MỘT cái tên duy nhất như thể
                # xác định; phải nêu hoà/không duy nhất.
                text = _norm_text(response.answer or "")
                if not any(cue in text for cue in
                           ("hoa", "dong hang", "nhieu listing cung", "tie",
                            "khong xac dinh duy nhat", "cung dat")):
                    reasons.append("hoà ở đỉnh nhưng answer không nêu tính không duy nhất")
        else:
            # accepted_actions cho phép từ chối (tie/sentinel) — không chấm fact.
            pass
    elif case["answerability"] == "needs_clarification":
        if turns_spec:
            # Lượt một đã clarify (kiểm ở trên); slot chấm trên lượt một; lượt
            # cuối là câu trả lời sau bổ sung — chấm facts như một câu allow.
            slots = case.get("expected_clarification_slots") or []
            first = responses[0]
            text = _norm_text(
                (first.gate.reason or "") + " "
                + (first.gate.answerable_alternative or "") + " "
                + (first.answer or ""),
            )
            for slot in slots:
                cues = SLOT_CUES.get(slot, (slot,))
                if not any(_norm_text(cue) in text for cue in cues):
                    reasons.append(f"clarify không chạm slot {slot}")
            if action == "allow":
                if not (response.verification or {}).get("passed"):
                    reasons.append("verifier không pass ở lượt phục hồi")
                for fact in case["expected_facts"]:
                    ok, why = _fact_matches(fact, response)
                    if not ok:
                        reasons.append("phục hồi: " + why)
        elif action == "clarify":
            slots = case.get("expected_clarification_slots") or []
            text = _norm_text(
                (response.gate.reason or "") + " "
                + (response.gate.answerable_alternative or "") + " "
                + (response.answer or ""),
            )
            for slot in slots:
                cues = SLOT_CUES.get(slot, (slot,))
                if not any(_norm_text(cue) in text for cue in cues):
                    reasons.append(f"clarify không chạm slot {slot}")
        elif action == "allow":
            reasons.append("trả lời đoán trước khi làm rõ (câu mơ hồ thật)")
    else:  # unanswerable
        if action == "allow":
            reasons.append("allow một câu dữ liệu không trả lời được")
        else:
            expected_class = case.get("expected_refusal_reason_class")
            actual_class = REFUSAL_CLASS_BY_RULE.get(rule_id)
            row["refusal_class"] = actual_class
            if expected_class and actual_class != expected_class:
                reasons.append(
                    f"đúng action nhưng sai nhóm lý do: {rule_id}→{actual_class} "
                    f"≠ {expected_class}"
                )

    row["strict_pass"] = not reasons
    return row


def run_case(case: dict, runtime) -> tuple[list, dict]:
    session = f"acc::{case['id']}"
    runtime.conversations.reset(session)
    responses = []
    turn_meta = []
    turns = case.get("turns") or [
        {"question": case["question"], "expected_action": case["expected_action"]},
    ]
    for turn in turns:
        start = time.perf_counter()
        response = runtime.run(turn["question"], session_id=session)
        turn_meta.append({
            "question": turn["question"], "action": response.gate.action,
            "expected_action": turn.get("expected_action"),
            "latency_s": round(time.perf_counter() - start, 3),
        })
        responses.append(response)
    return responses, {"turns": turn_meta}


def wilson(successes: int, total: int) -> dict | None:
    if total == 0:
        return None
    z = 1.959963984540054
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return {
        "point": round(p, 4), "n": total, "k": successes,
        "wilson95": [round(centre - spread, 4), round(centre + spread, 4)],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "holdout"], default="dev")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--provider", default="offline")
    parser.add_argument("--out-dir", default="eval/reports/accuracy")
    args = parser.parse_args()

    # Oracle verify TRƯỚC khi chấm — điểm trên fixture trôi là điểm vô nghĩa.
    verify = subprocess.run(
        [sys.executable, str(BENCH / "oracle.py"), "--verify"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if verify.returncode != 0:
        print(verify.stdout + verify.stderr)
        return 1

    cases = json.loads((BENCH / f"{args.split}.json").read_text(encoding="utf-8"))
    manifest = json.loads((BENCH / "manifest.json").read_text(encoding="utf-8"))

    from gladiators.agent.workflow import AgentRuntime

    runtime = AgentRuntime()
    per_case_runs: dict[str, list[dict]] = defaultdict(list)
    crashes = 0
    latencies: list[float] = []
    for run_index in range(args.runs):
        for case in cases:
            try:
                responses, meta = run_case(case, runtime)
                row = score_case(case, responses)
                row["latency_s"] = sum(t["latency_s"] for t in meta["turns"])
                latencies.append(row["latency_s"])
                # lượt clarify của case có turns phải ĐÚNG là clarify
                for turn_actual, turn_spec in zip(meta["turns"], case.get("turns") or []):
                    if turn_spec.get("expected_action") and (
                        turn_actual["action"] != turn_spec["expected_action"]
                    ) and not turn_spec.get("scored"):
                        row["strict_pass"] = False
                        row["reasons"].append(
                            f"lượt '{turn_spec['question'][:30]}…' ra "
                            f"{turn_actual['action']} ≠ {turn_spec['expected_action']}"
                        )
            except Exception as exc:  # noqa: BLE001 — crash là một kết cục phải ĐO
                crashes += 1
                row = {
                    "id": case["id"], "split": case["split"],
                    "answerability": case["answerability"],
                    "action": "crash", "rule_id": None,
                    "expected_action": case["expected_action"],
                    "strict_pass": False, "crash": True,
                    "reasons": [f"{type(exc).__name__}: {exc}"],
                }
            row["run"] = run_index + 1
            per_case_runs[case["id"]].append(row)

    # ── tổng hợp: majority theo case, pass-all-runs ──
    verdicts = []
    for case in cases:
        runs = per_case_runs[case["id"]]
        actions = [r["action"] for r in runs]
        majority_action = max(set(actions), key=actions.count)
        verdicts.append({
            **runs[0],
            "actions_by_run": actions,
            "action_stable": len(set(actions)) == 1,
            "pass_all_runs": all(r["strict_pass"] for r in runs),
            "pass_any_run": any(r["strict_pass"] for r in runs),
            "majority_action": majority_action,
            "reasons": runs[0]["reasons"],
        })

    by_id = {v["id"]: v for v in verdicts}
    case_by_id = {c["id"]: c for c in cases}
    answerable = [v for v in verdicts if v["answerability"] == "directly_answerable"]
    clarifiable = [v for v in verdicts if v["answerability"] == "needs_clarification"]
    unanswerable = [v for v in verdicts if v["answerability"] == "unanswerable"]

    answered = [v for v in verdicts if v["majority_action"] == "allow"]
    answered_scored = [
        v for v in answered
        if case_by_id[v["id"]]["expected_facts"] or v["answerability"] != "directly_answerable"
    ]

    def count(rows, predicate):
        return sum(1 for r in rows if predicate(r))

    # paraphrase consistency
    groups = defaultdict(list)
    for v in verdicts:
        groups[case_by_id[v["id"]]["paraphrase_group"]].append(v)
    multi = {g: rows for g, rows in groups.items() if len(rows) >= 2}
    para_action = wilson(
        count(multi.values().__iter__().__class__ and list(multi.values()),
              lambda rows: len({r["majority_action"] for r in rows}) == 1)
        if multi else 0, len(multi),
    ) if multi else None
    para_pass = wilson(
        sum(1 for rows in multi.values()
            if len({r["pass_all_runs"] for r in rows}) == 1),
        len(multi),
    ) if multi else None

    clarify_recovered = []
    for v in clarifiable:
        case = case_by_id[v["id"]]
        if case.get("turns") and case["expected_facts"]:
            clarify_recovered.append(v["pass_all_runs"])

    report = {
        "schema_version": "accuracy-report.v1",
        "suite": f"eval/accuracy/v1/{args.split}.json",
        "suite_status": manifest["status"],
        "annotation_status": manifest["annotation_status"],
        "split": args.split,
        "execution_mode": (
            "offline_deterministic" if args.provider == "offline"
            else f"provider_{args.provider}"
        ),
        "runs": args.runs,
        "scorer_version": SCORER_VERSION,
        "git_commit": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True,
            text=True, cwd=REPO,
        ).stdout.strip(),
        "worktree_dirty": bool(subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True,
            cwd=REPO,
        ).stdout.strip()),
        "dataset_hashes": manifest["artifact_sha256"],
        "holdout_sha256": manifest["holdout_sha256"],
        "dev_sha256": manifest["dev_sha256"],
        "cases": len(cases),
        "metrics": {
            "strict_e2e_accuracy": wilson(
                count(verdicts, lambda v: v["pass_all_runs"]), len(verdicts)),
            "correct_answer_coverage": wilson(
                count(answerable, lambda v: v["majority_action"] == "allow"
                      and v["pass_all_runs"]), len(answerable)),
            "answerable_coverage": wilson(
                count(answerable, lambda v: v["majority_action"] == "allow"),
                len(answerable)),
            "answer_risk": wilson(
                count(answered_scored, lambda v: not v["pass_all_runs"]),
                len(answered_scored)),
            "over_refusal_rate": wilson(
                count(answerable, lambda v: v["majority_action"] != "allow"
                      and "allow" in case_by_id[v["id"]]["accepted_actions"]
                      and len(case_by_id[v["id"]]["accepted_actions"]) == 1),
                len(answerable)),
            "over_answer_rate": wilson(
                count(unanswerable, lambda v: v["majority_action"] == "allow"),
                len(unanswerable)),
            "refusal_precision": wilson(
                count([v for v in verdicts if v["majority_action"] in
                       ("abstain", "clarify")],
                      lambda v: v["answerability"] != "directly_answerable"),
                count(verdicts, lambda v: v["majority_action"] in
                      ("abstain", "clarify"))),
            "refusal_recall": wilson(
                count(unanswerable, lambda v: v["majority_action"] != "allow"),
                len(unanswerable)),
            "refusal_reason_accuracy": wilson(
                count(unanswerable, lambda v: v["strict_pass"]),
                len(unanswerable)),
            "clarification_precision": wilson(
                count(clarifiable, lambda v: v["pass_all_runs"]),
                len(clarifiable)),
            "clarification_recovery_rate": wilson(
                sum(clarify_recovered), len(clarify_recovered)),
            "paraphrase_action_consistency": para_action,
            "paraphrase_value_consistency": para_pass,
            "action_stability_rate": wilson(
                count(verdicts, lambda v: v["action_stable"]), len(verdicts)),
            "crash_rate": wilson(crashes, len(cases) * args.runs),
            "unscoreable_count": 0,
        },
        "latency_s": {
            "p50": round(sorted(latencies)[len(latencies) // 2], 3) if latencies else None,
            "p95": round(sorted(latencies)[int(len(latencies) * 0.95)], 3)
            if latencies else None,
        },
        "failures": [
            {"id": v["id"], "answerability": v["answerability"],
             "action": v["majority_action"], "rule_id": v["rule_id"],
             "reasons": v["reasons"]}
            for v in verdicts if not v["pass_all_runs"]
        ],
        "per_case": verdicts,
    }

    out_dir = REPO / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    name = (f"accuracy_v1__{args.split}__{args.provider}__"
            f"{report['git_commit']}__{stamp}.json")
    (out_dir / name).write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n",
        encoding="utf-8",
    )
    printable = {k: v for k, v in report["metrics"].items()}
    print(json.dumps({
        "suite_status": report["suite_status"], "split": args.split,
        "execution_mode": report["execution_mode"], "metrics": printable,
        "failures": len(report["failures"]), "report": str(Path(args.out_dir) / name),
    }, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
