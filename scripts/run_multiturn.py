#!/usr/bin/env python3
"""Harness multiturn — W15.1 (SolutionSpec2808 §16.2).

Suite này có một hợp đồng mà ``run_evaluation.py`` không diễn đạt được: mỗi ca
là một CHUỖI lượt chung ``session_id``, và lượt sau khai HAI kỳ vọng. Bộ nhớ
hội thoại chỉ chứng minh được điều gì đó khi CẢ HAI nhánh cùng được chạy: có
``session_id`` thì kế thừa được country/date; không có thì phải hỏi lại. Chấm
một nhánh là không chấm A3 — một hệ bỏ qua ``session_id`` hoàn toàn vẫn xanh
nếu chỉ chạy nhánh có bộ nhớ.

    PYTHONPATH=src python scripts/run_multiturn.py
    PYTHONPATH=src python scripts/run_multiturn.py --suite eval/questions_multiturn.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _turn_passes(response, turn: dict) -> tuple[bool, str]:
    """(đạt, lý do) cho một lượt CÓ bộ nhớ."""
    if response.gate.action != turn.get("expected_action"):
        return False, f"action {response.gate.action} != {turn.get('expected_action')}"
    allowed = turn.get("allowed_rule_ids") or []
    if allowed and response.gate.rule_id not in allowed:
        return False, f"rule {response.gate.rule_id} ∉ {allowed}"
    expected_value = turn.get("expected_value") or {}
    if expected_value and response.gate.action == "allow":
        # Chấm bằng số học trên evidence, không so chuỗi (§16.2). Một bộ nhớ
        # điền BỪA cũng làm lượt cuối thành allow; chỉ oracle phân biệt được
        # điền đúng với điền bừa.
        values = {
            float(item.value) for item in response.evidence
            if isinstance(item.value, (int, float)) and not isinstance(item.value, bool)
        }
        for metric, expected in expected_value.items():
            if expected is None:
                continue
            if not any(abs(value - float(expected)) < 0.5 for value in values):
                return False, f"{metric}: không thấy {expected} trong evidence"
    return True, "ok"


def run(suite_path: str) -> dict:
    from gladiators.agent.workflow import AgentRuntime

    suite = json.loads((REPO / suite_path).read_text(encoding="utf-8"))
    runtime = AgentRuntime()

    turn_rows: list[dict] = []
    stateless_rows: list[dict] = []
    leak_probes: list[dict] = []
    for case in suite:
        # session_id reset GIỮA các ca, và harness chứng minh điều đó bên dưới
        # bằng leak probe — hai ca liên tiếp cùng thị trường mà rò state sẽ cho
        # cùng một kết quả và không ai thấy.
        runtime.conversations.reset(case["session_id"])
        for index, turn in enumerate(case["turns"]):
            with_memory = runtime.run(turn["question"], session_id=case["session_id"])
            passed, reason = _turn_passes(with_memory, turn)
            turn_rows.append({
                "case": case["id"], "turn": index,
                "question": turn["question"],
                "expected_action": turn.get("expected_action"),
                "action": with_memory.gate.action,
                "rule_id": with_memory.gate.rule_id,
                "passed": passed, "reason": reason,
            })
            if "expected_action_without_memory" in turn:
                stateless = runtime.run(turn["question"])  # session_id=None
                stateless_rows.append({
                    "case": case["id"], "turn": index,
                    "expected_action": turn["expected_action_without_memory"],
                    "action": stateless.gate.action,
                    "passed": stateless.gate.action
                    == turn["expected_action_without_memory"],
                })
        follow_up = next(
            (turn for turn in case["turns"][1:]
             if "expected_action_without_memory" in turn), None,
        )
        if follow_up is not None:
            # Leak probe: cùng câu lượt-2 trên một session MỚI TINH phải hành xử
            # như nhánh stateless — nếu state của ca trước rò sang, nó sẽ allow.
            probe_session = f"__leak_probe__{case['id']}"
            runtime.conversations.reset(probe_session)
            probe = runtime.run(follow_up["question"], session_id=probe_session)
            leak_probes.append({
                "case": case["id"],
                "expected": follow_up["expected_action_without_memory"],
                "action": probe.gate.action,
                "leaked": probe.gate.action
                != follow_up["expected_action_without_memory"],
            })

    # Cùng bộ chỉ số của W9.1 — không phát minh một tỷ lệ pass thứ ba (§1.3 đã
    # ghi cái giá của hai công thức cùng tên). Mẫu số là LƯỢT; số ca báo kèm.
    answerable = [row for row in turn_rows if row["expected_action"] == "allow"]
    answered = [row for row in turn_rows if row["action"] == "allow"]
    wrong = [row for row in answered if not row["passed"]]
    refused_answerable = [row for row in answerable if row["action"] != "allow"]
    cases_failed = sorted({row["case"] for row in turn_rows if not row["passed"]})
    report = {
        "suite": suite_path,
        "measured_on": date.today().isoformat(),
        "cases": len(suite),
        "turns": len(turn_rows),
        "turns_failed": sum(not row["passed"] for row in turn_rows),
        "cases_failed": cases_failed,
        "coverage": round(
            sum(row["passed"] for row in answerable) / len(answerable), 4,
        ) if answerable else None,
        "risk": round(len(wrong) / len(answered), 4) if answered else None,
        "over_refusal_rate": round(
            len(refused_answerable) / len(answerable), 4,
        ) if answerable else None,
        "stateless_turns": len(stateless_rows),
        "stateless_failed": sum(not row["passed"] for row in stateless_rows),
        "session_leaks": [row for row in leak_probes if row["leaked"]],
        "failures": [row for row in turn_rows if not row["passed"]],
        "stateless_failures": [row for row in stateless_rows if not row["passed"]],
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="eval/questions_multiturn.json")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    report = run(args.suite)
    output = args.output or f"eval/reports/{date.today().isoformat()}-multiturn.json"
    (REPO / output).parent.mkdir(parents=True, exist_ok=True)
    (REPO / output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps({key: report[key] for key in (
        "cases", "turns", "turns_failed", "coverage", "risk",
        "over_refusal_rate", "stateless_turns", "stateless_failed",
        "session_leaks",
    )}, ensure_ascii=False, indent=2))
    print(f"Report: {output}")
    failed = (
        report["turns_failed"] or report["stateless_failed"]
        or report["session_leaks"]
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
