#!/usr/bin/env python3
"""Smoke-test the whole answering surface against a live LLM provider.

Everything else in this repo is verified offline, where any question outside a
certified template fail-closes at ``A19-PLAN``.  That covers the deterministic
path -- which runs *before* the LLM and so is production-real -- but leaves the
LLM parse and P8/P9/P10/P11 planning path unexercised.  Two real defects were
only ever visible here: ``A22-ALIGN-DATE`` was dead code under a provider
because the model fills ``date_range`` with raw text, and the entire
``analytical`` semantic payload was dropped whenever the model's intent label
disagreed with the deterministic one.

Each case declares what must be true of the *answer*, not of the route, so the
expectations stay meaningful as plans move between synthesizer, template and
planner.

    python scripts/smoke_llm.py --provider deepseek
    python scripts/smoke_llm.py --provider deepseek --list-models
"""
from __future__ import annotations

import argparse
import json
import sys
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

ORACLE = {
    record["case_id"]: record["value"]
    for record in json.loads(
        (ROOT / "eval/independent/p0_probe_expected.json").read_text(encoding="utf-8"),
    )
}
BY_DATE = ORACLE["p0_date_point_vn"]["by_date"]
RANK = ORACLE["p0_rank_direction_vn"]
GROUPING = ORACLE["p0_grouping_official_shop"]
SCOPE = ORACLE["p0_scope_listing_count"]["counts"]

# kind:
#   value   -> must allow and the named metric must equal the oracle number
#   refuse  -> must not allow (a wrong answer here would be silent)
#   nowrong -> may allow, but the listed numbers must never appear
CASES = [
    # --- values the system must now get right -----------------------------
    ("Sản phẩm nào có giá cao nhất tại VN?", "value", ("price", RANK["max_price"])),
    ("Sản phẩm nào có giá thấp nhất tại VN?", "value", ("price", RANK["min_price"])),
    ("Có bao nhiêu listing ở VN?", "value", ("listing_count", BY_DATE["2026-07-03"]["listing_count"])),
    ("Có bao nhiêu listing tại VN ngày 01/07?", "value", ("listing_count", BY_DATE["2026-07-01"]["listing_count"])),
    ("Sản phẩm nào có giá cao nhất tại VN ngày 01/07?", "value", ("price", BY_DATE["2026-07-01"]["max_price"])),
    ("Có bao nhiêu listing ở Indonesia?", "value", ("listing_count", SCOPE["id"])),

    # --- restrictions the parser cannot bind: refusing is the correct answer
    ("Có bao nhiêu listing của shop official tại VN?", "refuse", None),
    ("Sản phẩm nào có giá thấp nhất của shop official tại VN?", "refuse", None),
    ("Rating theo brand không tồn tại tại VN", "refuse", None),

    # --- scope and window: answering half of these is a silent wrong answer
    ("Có bao nhiêu listing ở Việt Nam và Indonesia?", "nowrong",
     (BY_DATE["2026-07-03"]["listing_count"],)),
    ("Tính mức giảm doanh số (sales delta) của sản phẩm mã 24710759163 từ ngày 01/07 đến ngày 03/07.",
     "nowrong", (-102.0,)),

    # --- grouping: several rows, never one row passed off as the total ------
    ("Có bao nhiêu listing tại VN theo từng shop?", "nowrong",
     (GROUPING["vn_all_listings"],)),

    # --- capability boundaries: must stay refused ---------------------------
    ("Dự báo doanh số tuần sau tại VN?", "refuse", None),
    ("Lợi nhuận của shop nào cao nhất tại VN?", "refuse", None),
    ("So sánh giá trung bình giữa Việt Nam và Indonesia", "refuse", None),
]


def _check(kind, spec, response) -> tuple[bool, str]:
    action = response.gate.action
    values = {(item.metric, float(item.value))
              for item in response.evidence
              if isinstance(item.value, (int, float)) and not isinstance(item.value, bool)}
    if kind == "refuse":
        return action != "allow", "allowed a question whose restriction was never bound"
    if kind == "nowrong":
        bad = [n for n in spec if any(abs(v - n) < 0.5 for _, v in values)]
        return not bad, f"answered with {bad}, which is the known-wrong number"
    metric, want = spec
    if action != "allow":
        return False, f"refused a question it should answer ({metric}={want:g})"
    got = [v for m, v in values if m == metric]
    return (
        any(abs(v - want) < 0.5 for v in got),
        f"{metric}={got} but oracle says {want:g}",
    )


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
    model = getattr(client, "model", None) or getattr(
        getattr(client, "primary", None), "model", "?",
    )
    print(f"provider={getattr(client, 'provider', '?')} model={model}\n")

    rows, failures = [], 0
    for question, kind, spec in CASES:
        started = time.perf_counter()
        try:
            response = runtime.run(question)
            ok, why = _check(kind, spec, response)
            action, rule = response.gate.action, response.gate.rule_id
            mode = response.planning.get("mode")
            evidence = [(i.metric, i.value) for i in response.evidence][:3]
            error = None
        except Exception as exc:  # a provider or plan failure is a result
            ok, why = False, f"{type(exc).__name__}: {str(exc)[:140]}"
            action = rule = mode = None
            evidence, error = [], why

        failures += not ok
        rows.append({
            "question": question, "kind": kind, "ok": bool(ok), "why": None if ok else why,
            "action": action, "rule_id": rule, "mode": mode,
            "evidence": [[m, v] for m, v in evidence], "error": error,
            "seconds": round(time.perf_counter() - started, 2),
        })
        print(f"{'ok  ' if ok else 'FAIL'} [{str(action):8s}] {str(rule):22s} "
              f"{str(mode):24s} {rows[-1]['seconds']:>5.1f}s  {question[:52]}")
        if not ok:
            print(f"       -> {why}")

    out = ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": getattr(client, "provider", args.provider), "model": model,
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
