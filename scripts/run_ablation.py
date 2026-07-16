#!/usr/bin/env python3
"""Run reproducible component ablations; reports measurements, never novelty claims."""
import argparse, json, subprocess, sys
from pathlib import Path

ap=argparse.ArgumentParser(); ap.add_argument("--suite", default="eval/questions.json"); ap.add_argument("--runs", type=int, default=3); args=ap.parse_args()
modes = {
    "direct": {"entity_resolver":"rapidfuzz", "gate":False, "numeric_verifier":False},
    "gated": {"entity_resolver":"rapidfuzz", "gate":True, "numeric_verifier":False},
    "full": {"entity_resolver":"rapidfuzz", "gate":True, "numeric_verifier":True},
}
results={}
for mode, components in modes.items():
    run=subprocess.run([sys.executable,"scripts/run_evaluation.py","--suite",args.suite,"--runs",str(args.runs),"--mode",mode,"--output",f"artifacts/ablation/{mode}"],capture_output=True,text=True,check=True)
    report=sorted(Path(f"artifacts/ablation/{mode}").glob("*.json"))[-1]
    results[mode]={"components":components,"metrics":json.loads(report.read_text())["metrics"]}
Path("artifacts/ablation").mkdir(parents=True,exist_ok=True)
Path("artifacts/ablation/summary.json").write_text(json.dumps(results,ensure_ascii=False,indent=2,default=dict))
print(json.dumps(results,indent=2,default=dict))
