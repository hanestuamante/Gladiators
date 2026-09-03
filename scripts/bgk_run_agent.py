"""Run the agent on the 20 BGK questions with the LLM path fully enabled.

Uses create_runtime("deepseek") so parse and generation both go through the
model -- the branch an enterprise would actually run, and the one the six eval
suites never exercise because they all pass --provider offline.

Writes after every case so a timeout cannot lose paid-for calls.
"""
import io
import json
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
sys.path.insert(0, "src")

from collections import Counter

from gladiators.runtime_factory import create_runtime

cases = json.load(open("artifacts/bgk_groundtruth.json", encoding="utf-8"))
runtime = create_runtime("deepseek")
print(f"provider={runtime.llm_client.provider} model={runtime.llm_client.model}", flush=True)
print(f"llm_parser={runtime.use_llm_parser} llm_generation={runtime.use_llm_generation}\n",
      flush=True)

out = []
for index, case in enumerate(cases, 1):
    started = time.perf_counter()
    try:
        response = runtime.run(case["question"])
        record = {
            "id": case["id"],
            "group": case["group"],
            "verdict_expected": case["verdict"],
            "question": case["question"],
            "ground_truth": case["ground_truth"],
            "action": response.gate.action,
            "rule": response.gate.rule_id,
            "answer": response.answer or "",
            "evidence": [(e.metric, e.value) for e in response.evidence][:8],
            "evidence_count": len(response.evidence),
            "verified": (response.verification or {}).get("passed"),
            "unsupported": (response.verification or {}).get("unsupported") or [],
            "intent": response.request.intent,
            "planning_mode": (response.planning or {}).get("mode"),
            "shadow_routing": ((response.planning or {}).get("shadow") or {}).get("routing_mode"),
            "seconds": round(time.perf_counter() - started, 1),
        }
    except Exception as error:  # noqa: BLE001 - a crash is a result
        record = {
            "id": case["id"], "group": case["group"],
            "verdict_expected": case["verdict"], "question": case["question"],
            "ground_truth": case["ground_truth"], "action": "CRASH",
            "rule": type(error).__name__, "answer": str(error)[:200],
            "evidence": [], "evidence_count": 0, "verified": False, "unsupported": [],
            "intent": None, "planning_mode": None, "shadow_routing": None,
            "seconds": round(time.perf_counter() - started, 1),
        }
    out.append(record)
    print(f"{index:3d}/{len(cases)} {record['id']} [{record['action']:8s}] "
          f"{record['rule']:24s} {record['seconds']:6.1f}s  ev={record['evidence_count']}",
          flush=True)
    json.dump(out, open("artifacts/bgk_agent_run.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

print("\n=== tổng hợp ===", flush=True)
print("  action :", dict(Counter(r["action"] for r in out)), flush=True)
print("  intent :", dict(Counter(r["intent"] for r in out)), flush=True)
times = sorted(r["seconds"] for r in out)
print(f"  latency: p50 {times[len(times)//2]}s  p95 {times[int(len(times)*0.95)]}s  "
      f"max {times[-1]}s", flush=True)
