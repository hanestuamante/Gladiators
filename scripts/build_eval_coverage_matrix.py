#!/usr/bin/env python3
"""Build the auditable V2 coverage matrix from executable registries and eval tags."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import get_args

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))

from gladiators.domain.catalog import CATALOG
from gladiators.domain.relations import RELATIONS
from gladiators.planner.query_ir import Op


ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "eval"


def _cases() -> list[dict]:
    cases: list[dict] = []
    for path in sorted(EVAL.glob("questions*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for case in payload:
            cases.append({**case, "suite": path.name})
    mutation_path = EVAL / "planner_mutations.json"
    if mutation_path.exists():
        for case in json.loads(mutation_path.read_text(encoding="utf-8")):
            cases.append({**case, "suite": mutation_path.name})
    semantic_path = EVAL / "semantic_linking.json"
    if semantic_path.exists():
        for case in json.loads(semantic_path.read_text(encoding="utf-8")):
            cases.append({**case, "suite": semantic_path.name})
    operator_path = EVAL / "operator_acceptance.json"
    if operator_path.exists():
        for case in json.loads(operator_path.read_text(encoding="utf-8")):
            cases.append({**case, "suite": operator_path.name})
    relation_path = EVAL / "relation_acceptance.json"
    if relation_path.exists():
        for case in json.loads(relation_path.read_text(encoding="utf-8")):
            cases.append({**case, "suite": relation_path.name})
    for name in ("empty_result_acceptance.json", "l4_acceptance.json"):
        path = EVAL / name
        if path.exists():
            for case in json.loads(path.read_text(encoding="utf-8")):
                cases.append({**case, "suite": path.name})
    return cases


def build() -> dict:
    cases = _cases()
    positive: Counter[tuple[str, str]] = Counter()
    adversarial: Counter[tuple[str, str]] = Counter()
    examples: dict[tuple[str, str], list[str]] = defaultdict(list)
    for case in cases:
        coverage = case.get("coverage", {})
        polarity = adversarial if case.get("kind") == "mutation" or case.get("adversarial") else positive
        for axis in ("ops", "relations", "semantic_refs", "grains", "traps", "scenarios"):
            for value in coverage.get(axis, []):
                key = (axis, str(value))
                polarity[key] += 1
                examples[key].append(case["id"])
        if case.get("kind") != "mutation":
            for axis, field in (
                ("complexity", "complexity_level"),
                ("answerability", "answerability_class"),
                ("language_style", "language_style"),
            ):
                if case.get(field):
                    key = (axis, str(case[field]))
                    positive[key] += 1
                    examples[key].append(case["id"])
        else:
            key = ("scenarios", "invalid_or_unsafe")
            positive[key] += 1
            examples[key].append(case["id"])

    requirements: list[dict] = []

    def add(axis: str, value: str, minimum: int, mode: str = "positive") -> None:
        counter = adversarial if mode == "adversarial" else positive
        count = counter[(axis, value)]
        requirements.append({
            "axis": axis, "value": value, "mode": mode, "minimum": minimum,
            "observed": count, "satisfied": count >= minimum,
            "case_ids": examples[(axis, value)],
        })

    for op in get_args(Op):
        add("ops", op, 3)
        add("ops", op, 1, "adversarial")
    for name, relation in RELATIONS.items():
        add("relations", name, 2)
        if relation.cardinality == "N:M":
            add("relations", name, 1, "adversarial")
    for ref, obj in CATALOG.items():
        if obj.answerability in {"exposed_as_dimension", "exposed_as_measure", "proxy_only", "raw_but_unsafe"}:
            add("semantic_refs", ref, 1)
    for grain in ("listing", "listing_snapshot", "shop", "shelf", "category", "country", "group"):
        add("grains", grain, 2)
    for trap in range(1, 21):
        add("traps", str(trap), 1, "adversarial")
    for level in ("L0", "L1", "L2", "L3", "L4"):
        add("complexity", level, 1)
    for answerability in ("C1", "C2", "C3", "C4"):
        add("answerability", answerability, 1)
    for style in ("vi", "vi_khong_dau", "id", "noisy", "compound"):
        add("language_style", style, 1)
    for scenario, minimum in (
        ("entity_ambiguity", 4), ("empty_result", 3), ("composite_l4", 6),
        ("invalid_or_unsafe", 10),
    ):
        add("scenarios", scenario, minimum)
    legacy_count = sum(case.get("suite") == "questions.json" for case in cases)
    requirements.append({
        "axis": "parity", "value": "legacy_certified_macros", "mode": "positive",
        "minimum": 60, "observed": legacy_count, "satisfied": legacy_count >= 60,
        "case_ids": [case["id"] for case in cases if case.get("suite") == "questions.json"],
    })

    satisfied = sum(item["satisfied"] for item in requirements)
    return {
        "schema_version": "1.0",
        "source": {
            "catalog_objects": len(CATALOG), "relation_edges": len(RELATIONS),
            "ir_operators": len(get_args(Op)), "eval_cases_with_mutations": len(cases),
        },
        "summary": {
            "requirements": len(requirements), "satisfied": satisfied,
            "missing": len(requirements) - satisfied,
            "coverage_ratio": round(satisfied / len(requirements), 6) if requirements else 0,
            "phase_4_5_acceptance_ready": satisfied == len(requirements),
        },
        "requirements": requirements,
    }


def main() -> None:
    output = EVAL / "coverage_matrix.json"
    output.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
