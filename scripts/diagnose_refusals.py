#!/usr/bin/env python3
"""Bảng chẩn đoán từ chối oan — SolutionSpec2808 §13.5 (W12.3).

    PYTHONPATH=src python scripts/diagnose_refusals.py \\
      --suite eval/independent/answerable_manual.json --provider offline

Đây là thứ **thay thế phiên đọc code bằng tay** đã sinh ra §1.2 và §1.5 của
spec: với mỗi ca ``answerable=true`` bị từ chối, in chặng chặn + mã từ chối +
nhánh đã thử, rồi gộp theo ``(chặng, mã)``. Bảng đếm đó chính là §1.2, sinh tự
động — ca thứ 20 hỏng thì không ai phải làm lại phiên đọc code nữa.

**Ràng buộc thiết kế:** script chỉ đọc ``AgentResponse``, không import
``planner``/``domain``. Nếu nó phải đọc internal để giải thích thì internal chưa
lộ đủ — và đó là lỗi của W12.1/W12.2, không phải của script này.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def blocking_stage(response) -> tuple[str, str]:
    """(chặng chặn, mã từ chối) — suy từ những gì response TỰ nói.

    Thứ tự kiểm quan trọng: một ca bị risk chặn vẫn mang ``a19_rule=A19-PLAN``,
    nên kiểm rule trước sẽ đổ mọi thứ vào "planner" — đúng cách đọc sai mà ca
    ans031 phơi ra (synthesizer đã thử VÀ plan đúng, thứ chặn là thang leo thang).
    """
    planning = response.planning or {}
    rule = str(response.gate.rule_id or "")

    if rule.startswith("A22"):
        verdict = planning.get("alignment_verdict") or {}
        for key in ("evidence_alignment", "alignment"):
            issues = (planning.get(key) or {}).get("issues") or []
            if issues:
                return "alignment", str(issues[0].get("code", rule))
        return "alignment", str(verdict.get("rule_id", rule))

    if planning.get("escalation_mode") == "blocked":
        return "risk", f"escalation_blocked:{planning.get('requested_escalation')}"

    attempts = planning.get("attempts") or []
    if attempts:
        declined = [
            code for attempt in attempts for code in attempt.get("declined", [])
        ]
        synthesizer = next(
            (a for a in attempts if a.get("branch") == "synthesizer"), None,
        )
        if synthesizer is not None and not synthesizer.get("tried"):
            return "planner", "beats_template=False"
        if declined:
            return "planner", declined[0]
        return "planner", str(planning.get("a19_rule", rule))

    if planning.get("mode") in (None, "none", "blocked") and not response.evidence:
        return "gate", rule
    return "unknown", rule


def branch_summary(response) -> str:
    attempts = (response.planning or {}).get("attempts") or []
    if not attempts:
        return "—"
    parts = []
    for attempt in attempts:
        name = attempt.get("branch", "?")
        if not attempt.get("tried"):
            parts.append(f"{name}:KHÔNG THỬ")
        elif attempt.get("declined"):
            parts.append(f"{name}:{','.join(attempt['declined'])}")
        else:
            parts.append(f"{name}:OK")
    return " · ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="eval/independent/answerable_manual.json")
    parser.add_argument("--provider", default="offline")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    from gladiators.runtime_factory import create_runtime

    cases = json.loads((ROOT / args.suite).read_text(encoding="utf-8"))
    if isinstance(cases, dict):
        cases = cases.get("cases", [])
    runtime = create_runtime(args.provider)

    rows: list[dict] = []
    for case in cases:
        if case.get("answerable") is not True or not case.get("question"):
            continue
        response = runtime.run(case["question"])
        if response.gate.action == "allow":
            continue
        stage, code = blocking_stage(response)
        rows.append({
            "id": case["id"], "action": response.gate.action,
            "rule_id": response.gate.rule_id,
            "stage": stage, "code": code,
            "branches": branch_summary(response),
        })

    header = f"{'ca':<8}| {'action':<8}| {'rule_id':<22}| {'chặng chặn':<11}| {'mã từ chối':<32}| nhánh đã thử"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(f"{row['id']:<8}| {row['action']:<8}| {row['rule_id']:<22}| "
              f"{row['stage']:<11}| {row['code']:<32}| {row['branches']}")

    counts = Counter((row["stage"], row["code"]) for row in rows)
    print()
    print(f"{'lần':>4}  {'chặng':<11} mã")
    for (stage, code), count in counts.most_common():
        print(f"{count:>4}  {stage:<11} {code}")
    print(f"\nTổng: {len(rows)} ca từ chối oan")

    if args.out:
        (ROOT / args.out).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
