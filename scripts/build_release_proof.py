#!/usr/bin/env python3
"""Generate the §17 release proof pack for the P0 regression lock.

Writes ``artifacts/release/<run_id>/`` containing:

``test_summary.txt``
    Provenance header (command, commit SHA, config hash, dataset version) plus
    the verbatim pytest output.
``baseline_red_proof.json``
    One record per probe in ``eval/p0_probes.json``: what the runtime actually
    did, whether the contract holds, and the independent-oracle rows — each
    carrying ``source_file``/``source_row`` back into ``data/raw/`` so that
    §17's *"reviewer độc lập đối chiếu oracle/source row"* is a mechanical check
    rather than an assertion of good faith.

The script never recomputes a denotation; it loads
``eval/independent/p0_probe_expected.json``, which is produced by a module that
imports no gladiators code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gladiators.agent.workflow import AgentRuntime

SCHEMA_VERSION = "baseline-red-proof.v1"
EVIDENCE_ID_MASK = re.compile(r"ev:[0-9a-f]{12}")
SUMMARY_LINE = re.compile(r"^=+ .*(passed|failed|error).* =+$", re.MULTILINE)
COUNT = re.compile(r"(\d+) (passed|failed|xfailed|xpassed|errors?|skipped)")

# P1 must fix these together or CI goes red for a correct change.
KNOWN_CODEPENDENCIES = [
    {
        "probe_id": "p0-tc34-date-window-narrowing",
        "site": "scripts/run_evaluation.py:50",
        "detail": (
            "The eval harness recomputes expected sales_decline evidence with "
            "rows.iloc[-1], the same trailing-leg rule as AnalyticsTools.sales_decline, "
            "so it currently scores the narrowed -102 answer as correct. Fixing the "
            "tool without fixing the harness will turn the harness red on a correct "
            "change. No question in eval/questions.json names a date window today, "
            "which is the only reason this is latent."
        ),
    },
]


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _normalize_answer(answer: str) -> str:
    """Mask the uuid4 half of evidence ids so answers hash reproducibly."""
    return EVIDENCE_ID_MASK.sub("ev:XXXXXXXXXXXX", answer)


def _counts(output: str) -> dict[str, int]:
    match = SUMMARY_LINE.findall(output)
    tail = output.strip().splitlines()[-1] if output.strip() else ""
    counts = {key if not key.startswith("error") else "errors": int(value)
              for value, key in COUNT.findall(tail)}
    counts.setdefault("passed", 0)
    for key in ("failed", "xfailed", "xpassed", "errors", "skipped"):
        counts.setdefault(key, 0)
    return counts, tail, bool(match)


def _observe(runtime: AgentRuntime, case: dict, dr2607: dict) -> dict:
    question = case["question"] or dr2607[case["dr2607_id"]]["question"]
    response = runtime.run(question)
    answer = _normalize_answer(response.answer)
    return {
        "question": question,
        "action": response.gate.action,
        "rule_id": response.gate.rule_id,
        "request_countries": list(response.request.countries),
        "planning": {
            key: response.planning.get(key)
            for key in ("mode", "macro", "macro_version", "plan_id", "a19_rule")
            if response.planning.get(key) is not None
        },
        "semantic_refs": sorted(response.planning.get("semantic_refs", [])),
        "evidence": [
            {
                "metric": item.metric,
                "value": item.value,
                "unit": item.unit,
                "attrs": {k: v for k, v in item.attrs.items() if k != "plan_hash"},
            }
            for item in response.evidence
        ],
        "claims": len(response.claims),
        "answer_normalized": answer,
        "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
    }


def _contract_holds(case: dict, observed: dict) -> bool:
    """Mirror of the three red contracts in tests/test_p0_regression_lock.py."""
    if observed["action"] != "allow":
        return True
    evidence = observed["evidence"]
    if case["id"] == "p0-tc34-date-window-narrowing":
        window = {
            (str(item["attrs"].get("previous_date")), str(item["attrs"].get("date")))
            for item in evidence if item["metric"] == "monthly_sold_delta"
        }
        return bool(window) and min(s for s, _ in window) == "2026-07-01" \
            and max(d for _, d in window) == "2026-07-03"
    if case["id"] == "p0-scope-dropped-vn-id":
        covered = {str(i["attrs"]["country"]) for i in evidence if i["attrs"].get("country")}
        return covered >= set(observed["request_countries"])
    if case["id"] == "p0-plurality-top-k":
        # Count distinct listings in both shapes the pipeline emits: the
        # certified template carries the name in attrs, the synthesizer emits it
        # as its own Evidence row. Reading only attrs made this proof report a
        # correct 5-listing answer as still-broken, because the shape moved and
        # this copy of the rule did not follow.
        listings = {
            str(i["attrs"]["product_name"]) for i in evidence if i["attrs"].get("product_name")
        } | {
            str(i["value"]) for i in evidence if i["metric"] == "product_name"
        }
        return len(listings) > 1
    if case["id"] == "p0-gap-item-42955556831":
        return not any(i["metric"] == "monthly_sold_delta" for i in evidence)
    if case["id"] == "p0-tc19-sentinel-premise":
        return False  # allow is forbidden while DR1 is pending
    return True


def build(run_id: str, out_dir: Path, skip_pytest: bool) -> dict:
    probes = json.loads((ROOT / "eval/p0_probes.json").read_text(encoding="utf-8"))
    dr2607 = {
        case["id"]: case
        for case in json.loads((ROOT / "eval/dr2607.json").read_text(encoding="utf-8"))
    }
    oracle = {
        record["case_id"]: record
        for record in json.loads(
            (ROOT / "eval/independent/p0_probe_expected.json").read_text(encoding="utf-8"),
        )
    }

    command = "python -m pytest -q"
    pytest_output, exit_code = "", None
    if not skip_pytest:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=ROOT, capture_output=True, text=True,
        )
        pytest_output = result.stdout + result.stderr
        exit_code = result.returncode
    counts, summary_line, _ = _counts(pytest_output)

    runtime = AgentRuntime(trace_dir=out_dir / "traces")
    cases: list[dict] = []
    for case in probes["cases"]:
        observed = _observe(runtime, case, dr2607)
        holds = _contract_holds(case, observed)
        oracle_key = case["oracle_ref"].split("#")[-1]
        cases.append({
            "id": case["id"],
            "kind": case["kind"],
            "expected_state": case["expected_state"],
            "status": (
                "red_confirmed" if case["kind"] == "red" and not holds
                else "red_resolved" if case["kind"] == "red"
                else "locked"
            ),
            "question": observed["question"],
            "question_source": case["source"],
            "spec_ref": case["spec_ref"],
            "test_ref": "tests/test_p0_regression_lock.py",
            "observed": observed,
            "expected_contract": {"statement": case["contract"]["statement"], "holds": holds},
            "oracle": {
                "module": "eval/independent/p0_probe_oracle.py",
                "record": oracle_key,
                "metric": oracle[oracle_key]["metric"],
                "scope": oracle[oracle_key]["scope"],
                "value": oracle[oracle_key]["value"],
                "method_note": oracle[oracle_key]["method_note"],
                "reviewer": {"name": None, "approved_at": None, "signature": None},
            },
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "commit_sha": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "config_hash": _sha256(ROOT / "configs/default.yaml"),
        "dataset_version": runtime.repo.dataset_version,
        "pinned_dataset_version": probes["dataset_version"],
        "data_dir": "data/processed",
        "pytest": {
            "exit_code": exit_code,
            "raw_summary_line": summary_line,
            "counts": counts,
            "skipped": skip_pytest,
        },
        "known_oracle_codependencies": KNOWN_CODEPENDENCIES,
        "cases": cases,
    }, pytest_output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", default="artifacts/release")
    parser.add_argument("--skip-pytest", action="store_true")
    args = parser.parse_args()

    if os.environ.get("PYTEST_CURRENT_TEST"):
        raise SystemExit("build_release_proof.py must not run inside pytest")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or f"{stamp}-{_git('rev-parse', '--short', 'HEAD') or 'nogit'}"
    out_dir = ROOT / args.output_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    report, pytest_output = build(run_id, out_dir, args.skip_pytest)

    header = [
        f"run_id: {run_id}",
        f"generated_at: {report['generated_at']}",
        f"command: {report['command']}",
        f"commit_sha: {report['commit_sha']}",
        f"git_dirty: {report['git_dirty']}",
        f"config_hash: {report['config_hash']}",
        f"dataset_version: {report['dataset_version']}",
        f"pinned_dataset_version: {report['pinned_dataset_version']}",
        f"python: {sys.version.split()[0]}",
        f"platform: {sys.platform}",
        f"pytest_exit_code: {report['pytest']['exit_code']}",
        f"counts: {report['pytest']['counts']}",
        "--- raw pytest output ---",
    ]
    (out_dir / "test_summary.txt").write_text(
        "\n".join(header) + "\n" + pytest_output, encoding="utf-8",
    )
    (out_dir / "baseline_red_proof.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    red_expected = sum(
        1 for case in report["cases"]
        if case["kind"] == "red" and case["expected_state"] == "red"
    )
    red_confirmed = sum(1 for case in report["cases"] if case["status"] == "red_confirmed")
    print(json.dumps({
        "run_id": run_id,
        "out_dir": str(out_dir.relative_to(ROOT)),
        "cases": len(report["cases"]),
        "red_expected": red_expected,
        "red_confirmed": red_confirmed,
        "counts": report["pytest"]["counts"],
    }, ensure_ascii=False))

    if report["dataset_version"] != report["pinned_dataset_version"]:
        raise SystemExit("dataset_version drifted from eval/p0_probes.json")
    if red_confirmed != red_expected:
        raise SystemExit(
            f"expected {red_expected} confirmed-red probes, observed {red_confirmed}",
        )
    if not args.skip_pytest:
        if report["pytest"]["counts"]["xfailed"] != red_expected:
            raise SystemExit(
                f"pytest reported {report['pytest']['counts']['xfailed']} xfailed, "
                f"expected {red_expected}",
            )
        if report["pytest"]["exit_code"] != 0:
            raise SystemExit("pytest did not pass")


if __name__ == "__main__":
    main()
