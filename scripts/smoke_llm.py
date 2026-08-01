#!/usr/bin/env python3
"""Smoke-test the LLM planner path against a live provider.

Everything committed so far was verified offline, where any question outside a
certified template fail-closes at ``A19-PLAN``.  That covers the deterministic
templates -- which run *before* the LLM and so are production-real -- but leaves
the whole P8/P9/P10/P11 path unexercised.

This script targets the gap, in particular the three questions that the ranking
direction guard newly pushes off the template path and into the planner.

    python scripts/smoke_llm.py --provider deepseek
    python scripts/smoke_llm.py --provider deepseek --list-models
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Vietnamese question text hits UnicodeEncodeError on the Windows cp1252 console.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from gladiators.runtime_factory import create_runtime

# expect: "planner" = must reach the LLM (no certified template covers it)
#         "template" = must stay on the deterministic path, LLM or not
#         "blocked"  = must not answer at all
CASES = [
    # Pushed onto the planner by the P1 ranking-direction guard. Offline these
    # abstain; with a provider they will actually generate a plan nobody has seen.
    ("Sản phẩm nào có giá thấp nhất tại VN?", "planner"),
    ("Sản phẩm nào có lượt bán thấp nhất tại VN?", "planner"),
    ("Sản phẩm nào có rating cao nhất tại VN?", "planner"),
    # Fixed in P1 -- must stay fixed once a planner is available, i.e. the
    # planner must not become a way around the alignment gates.
    ("Có bao nhiêu listing ở Việt Nam và Indonesia?", "blocked"),
    ("Có bao nhiêu listing tại VN ngày 01/07?", "blocked"),
    ("Có bao nhiêu listing của shop official tại VN?", "blocked"),
    # Certified templates: must not regress now that an LLM exists.
    ("Sản phẩm nào có giá cao nhất tại VN?", "template"),
    ("Có bao nhiêu listing ở VN?", "template"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--output", default="artifacts/smoke_llm")
    args = parser.parse_args()

    if args.list_models:
        from gladiators.agent.llm import DeepSeekLLMClient

        for name in DeepSeekLLMClient.available_models():
            print(name)
        return

    runtime = create_runtime(args.provider)
    client = runtime.llm_client
    print(f"provider={getattr(client, 'provider', '?')} "
          f"model={getattr(client, 'model', getattr(getattr(client, 'primary', None), 'model', '?'))}")

    rows, failures = [], 0
    for question, expect in CASES:
        started = time.perf_counter()
        try:
            response = runtime.run(question)
            action, rule = response.gate.action, response.gate.rule_id
            mode = response.planning.get("mode")
            evidence = [(item.metric, item.value) for item in response.evidence][:3]
            error = None
        except Exception as exc:  # provider/plan failure is a result, not a crash
            action = rule = mode = None
            evidence, error = [], f"{type(exc).__name__}: {str(exc)[:160]}"

        if expect == "blocked":
            ok = action is not None and action != "allow"
        elif expect == "template":
            ok = action == "allow" and mode == "deterministic_template"
        else:  # planner
            ok = error is None and mode not in {"deterministic_template", None}

        failures += not ok
        rows.append({
            "question": question, "expect": expect, "ok": bool(ok),
            "action": action, "rule_id": rule, "mode": mode,
            "evidence": [[m, v] for m, v in evidence], "error": error,
            "seconds": round(time.perf_counter() - started, 2),
        })
        print(f"{'ok  ' if ok else 'FAIL'} [{str(action):8s}] {str(rule):22s} "
              f"mode={str(mode):24s} {rows[-1]['seconds']:>5.1f}s  {question[:46]}")
        if error:
            print(f"      {error}")

    out = ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": getattr(client, "provider", args.provider),
        "cases": len(rows), "failures": failures, "rows": rows,
        "telemetry": client.telemetry() if hasattr(client, "telemetry") else {},
    }
    path = out / f"{stamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(rows) - failures}/{len(rows)} ok -> {path.relative_to(ROOT)}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
