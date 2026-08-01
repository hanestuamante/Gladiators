#!/usr/bin/env python3
"""Three-layer evaluation runner — ultimate solution §4.9.

The existing harness ANDs every check into one ``passed`` flag, so a case that
routed correctly but built the wrong plan is indistinguishable from one that
failed to parse.  §4.9 asks for three verdicts that stand on their own:

1. ``action``      — did the gate decide the right thing;
2. ``plan_or_tool``— does the plan match the structural oracle;
3. ``answer``      — does the answer respect its content constraints.

The rule that matters is the last line of §4.9: *ALLOW + VERIFIED is not a pass
if the plan oracle fails*.  A right-looking number reached the wrong way is a
failure, and only a separate plan verdict can say so.

Cases carry optional ``expected_plan_properties`` (shape only: refs,
aggregation, grouping, scope, output kind — never values, which would make the
fixture an answer key), ``must_not_assert`` and ``forbidden_answer_tokens``.
Layers with nothing declared report ``not_applicable`` rather than a free pass,
so coverage gaps stay visible instead of inflating the score.

    python scripts/run_three_layer_eval.py --suite eval/dr2607.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from gladiators.agent.workflow import AgentRuntime

# Evidence ids embed a uuid4, so a forbidden-token scan over raw answer text can
# collide with a random identifier. Mask before matching.
_EVIDENCE_ID = re.compile(r"ev:[0-9a-f]{12}")

Verdict = tuple[str, str]  # (verdict, reason_code)


def _action_layer(case: dict, response) -> Verdict:
    expected = case.get("expected_action")
    if expected is None:
        return "not_applicable", "no_expected_action"
    if response.gate.action != expected:
        return "fail", f"action_{response.gate.action}_expected_{expected}"
    allowed = case.get("allowed_rule_ids") or []
    if allowed and response.gate.rule_id not in allowed:
        return "fail", f"rule_{response.gate.rule_id}_not_in_allowed"
    if response.gate.rule_id in (case.get("forbidden_rule_ids") or []):
        return "fail", f"rule_{response.gate.rule_id}_forbidden"
    return "pass", "action_matches"


def _plan_layer(case: dict, response) -> Verdict:
    expected = case.get("expected_plan_properties")
    if not expected:
        return "not_applicable", "no_plan_oracle"
    observed = response.planning.get("plan_properties")
    if not observed:
        return "fail", "no_plan_built"
    for key, want in expected.items():
        got = observed.get(key)
        if isinstance(want, list):
            if sorted(map(str, want)) != sorted(map(str, got or [])):
                return "fail", f"plan_{key}_mismatch"
        elif want != got:
            return "fail", f"plan_{key}_mismatch"
    return "pass", "plan_matches_oracle"


def _answer_layer(case: dict, response) -> Verdict:
    forbidden = case.get("forbidden_answer_tokens") or []
    must_not = case.get("must_not_assert") or []
    if not forbidden and not must_not:
        return "not_applicable", "no_answer_constraints"
    visible = _EVIDENCE_ID.sub("ev:MASKED", response.answer)
    for token in forbidden:
        if str(token) in visible:
            return "fail", "forbidden_token_present"
    for claim in must_not:
        if str(claim).lower() in visible.lower():
            return "fail", "forbidden_assertion_present"
    return "pass", "answer_constraints_met"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:32] if path.exists() else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="eval/dr2607.json")
    parser.add_argument("--output", default="artifacts/eval_three_layer")
    args = parser.parse_args()

    suite_path = ROOT / args.suite
    payload = json.loads(suite_path.read_text(encoding="utf-8"))
    # Suites are either a bare list (dr2607) or a wrapper with "cases" (p0 probes).
    cases = payload if isinstance(payload, list) else payload.get("cases", [])
    borrowed = {
        item["id"]: item["question"]
        for item in json.loads((ROOT / "eval/dr2607.json").read_text(encoding="utf-8"))
    }
    with tempfile.TemporaryDirectory(prefix="three-layer-") as traces:
        runtime = AgentRuntime(trace_dir=traces)
        rows = []
        for case in cases:
            question = case.get("question") or borrowed.get(case.get("dr2607_id"))
            if not question:
                continue
            response = runtime.run(question)
            layers = {
                "action": _action_layer(case, response),
                "plan_or_tool": _plan_layer(case, response),
                "answer": _answer_layer(case, response),
            }
            # §4.9: a case passes only when no layer fails. ALLOW + VERIFIED is
            # not enough when the plan oracle fails.
            rows.append({
                "id": case.get("id"),
                "verdicts": {name: v for name, (v, _) in layers.items()},
                "reasons": {name: r for name, (_, r) in layers.items()},
                "passed": all(v != "fail" for v, _ in layers.values()),
                "gate_action": response.gate.action,
                "gate_rule_id": response.gate.rule_id,
            })
        dataset_version = runtime.repo.dataset_version

    def tally(layer: str) -> dict:
        counts = Counter(row["verdicts"][layer] for row in rows)
        denominator = counts["pass"] + counts["fail"]
        return {
            "pass": counts["pass"], "fail": counts["fail"],
            "not_applicable": counts["not_applicable"],
            # Rate over cases that actually declare an oracle: a suite with no
            # plan oracles must not read as 100% plan-correct.
            "denominator": denominator,
            "rate": round(counts["pass"] / denominator, 4) if denominator else None,
        }

    report = {
        "schema_version": "eval-three-layer.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suite": args.suite,
        "fixture_hash": _sha(suite_path),
        "dataset_version": dataset_version,
        "config_hash": _sha(ROOT / "configs/default.yaml"),
        "cases": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "layers": {name: tally(name) for name in ("action", "plan_or_tool", "answer")},
        "reason_codes": dict(Counter(
            f"{layer}:{row['reasons'][layer]}"
            for row in rows for layer in row["reasons"]
            if row["verdicts"][layer] == "fail"
        )),
        "rows": rows,
    }

    out = ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (out / f"{stamp}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(
        {key: report[key] for key in
         ("suite", "cases", "passed", "layers", "fixture_hash", "dataset_version")},
        ensure_ascii=False, indent=2,
    ))
    if report["reason_codes"]:
        print("\nfailing reason codes:")
        for code, count in sorted(report["reason_codes"].items()):
            print(f"  {count:>3}  {code}")
    raise SystemExit(1 if report["passed"] < report["cases"] else 0)


if __name__ == "__main__":
    main()
