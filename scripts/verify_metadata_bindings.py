"""Probe read-only cho Metadata Binding Layer — §E1.7/E2.7/E3.7/E4.7.

Không ghi gì, không sửa registry, không chạm gate. Mục đích duy nhất: in ra con
số mà một người review có thể đối chiếu với tài liệu, và trả exit code khác 0
khi binding không dựng được.

    python scripts/verify_metadata_bindings.py --json
    python scripts/verify_metadata_bindings.py --section relations
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gladiators.domain.bindings import (  # noqa: E402
    BindingError,
    build_binding_snapshot,
)
from gladiators.domain.invariant_handlers import INVARIANT_HANDLERS  # noqa: E402
from gladiators.domain.metrics import METRIC_GRAPH  # noqa: E402
from gladiators.domain.relations import (  # noqa: E402
    INLINE_RELATIONS,
    JOIN_RELATIONS,
    RELATIONS,
)

SECTIONS = ("tables", "catalog", "relations", "metrics", "invariants", "hashes")


def _tables(snapshot) -> dict[str, object]:
    counts = snapshot.counts()
    views = [spec.view_name for spec in snapshot.tables.values()]
    unresolved = [
        check.handler_id
        for spec in snapshot.tables.values()
        for check in spec.quality_checks
        if check.severity == "hard" and check.handler_id not in _handlers()
    ]
    return {
        "tables": counts["tables"],
        "columns": counts["columns"],
        "duplicate_views": len(views) - len(set(views)),
        "unresolved_quality_handlers": len(unresolved),
    }


def _handlers() -> dict[str, object]:
    from gladiators.domain.bindings import quality_check_handlers

    return quality_check_handlers()


def _catalog(snapshot) -> dict[str, object]:
    counts = snapshot.counts()
    errors = [
        str(binding)
        for obj in snapshot.catalog.values()
        for binding in obj.physical_bindings
        if not snapshot.has_column(binding)
    ]
    return {
        "catalog_objects": counts["catalog_objects"],
        "catalog_bindings": counts["catalog_bindings"],
        "errors": len(errors),
        "unresolved": errors,
    }


def _relations(snapshot) -> dict[str, object]:
    invalid = [
        f"{name}:{key.left if not snapshot.has_column(key.left) else key.right}"
        for name, spec in RELATIONS.items()
        for key in (spec.binding.join_keys if spec.binding else ())
        if not snapshot.has_column(key.left) or not snapshot.has_column(key.right)
    ]
    forbidden = [
        name for name, spec in RELATIONS.items()
        if {spec.left, spec.right} == {"ShopCategory", "PlatformCategory"}
    ]
    legacy_match = sum(
        1 for name in JOIN_RELATIONS
        if RELATIONS[name].join_keys == tuple(
            (key.left.column, key.right.column)
            for key in RELATIONS[name].binding.join_keys
        )
    )
    return {
        "relations": len(RELATIONS),
        "join": len(JOIN_RELATIONS),
        "inline": len(INLINE_RELATIONS),
        "invalid_columns": len(invalid),
        "legacy_maps_match": legacy_match,
        "forbidden_category_cross_edge": len(forbidden),
    }


def _metrics(snapshot) -> dict[str, object]:
    specs = snapshot.metrics
    unclassified = 0
    for name, spec in specs.items():
        reachable = set(spec.source_columns) | set(METRIC_GRAPH.ancestors(name))
        for parent in METRIC_GRAPH.ancestors(name):
            reachable |= set(specs[parent].source_columns)
        unclassified += len([t for t in spec.depends_on if t not in reachable])
    unresolved = [
        constraint.constraint_id
        for spec in specs.values()
        for constraint in spec.definition_constraints
        if constraint.ref not in snapshot.catalog
    ]
    return {
        "metrics": len(specs),
        "metric_edges": METRIC_GRAPH.edge_count(),
        "cycles": len(METRIC_GRAPH.cycles),
        "legacy_token_unclassified": unclassified,
        "unresolved_constraints": len(unresolved),
        "constraints": sum(len(s.definition_constraints) for s in specs.values()),
    }


def _invariants(snapshot) -> dict[str, object]:
    specs = snapshot.invariants
    unresolved = [
        spec.invariant_id for spec in specs.values()
        if spec.validator_id not in INVARIANT_HANDLERS
    ]
    uncovered = [
        spec.invariant_id for spec in specs.values()
        if spec.validator_id in INVARIANT_HANDLERS
        and set(spec.applies_to) - INVARIANT_HANDLERS[spec.validator_id].stages
    ]
    return {
        "specs": len(specs),
        "handlers": len(INVARIANT_HANDLERS),
        "unresolved": len(unresolved),
        "uncovered_stages": len(uncovered),
        "hard": sum(1 for s in specs.values() if s.severity == "hard"),
        "warning": sum(1 for s in specs.values() if s.severity == "warning"),
    }


def _hashes(snapshot) -> dict[str, object]:
    return {
        "table_hash": snapshot.table_hash,
        "catalog_hash": snapshot.catalog_hash,
        "relation_hash": snapshot.relation_hash,
        "metric_hash": snapshot.metric_hash,
        "invariant_hash": snapshot.invariant_hash,
        "binding_hash": snapshot.binding_hash,
    }


_BUILDERS = {
    "tables": _tables, "catalog": _catalog, "relations": _relations,
    "metrics": _metrics, "invariants": _invariants, "hashes": _hashes,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/processed")
    parser.add_argument("--section", choices=SECTIONS, action="append")
    parser.add_argument("--json", action="store_true", help="in JSON thay vì key=value")
    args = parser.parse_args()

    try:
        snapshot = build_binding_snapshot(args.data_dir)
    except BindingError as exc:
        print(f"BINDING_ERROR: {exc}", file=sys.stderr)
        return 2

    sections = tuple(args.section) if args.section else SECTIONS
    report = {name: _BUILDERS[name](snapshot) for name in sections}

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for name in sections:
            body = " ".join(
                f"{key}={value}" for key, value in report[name].items()
                if not isinstance(value, list)
            )
            print(f"{name}: {body}")

    failures = sum(
        int(report[name].get(key, 0))
        for name in sections
        for key in ("errors", "duplicate_views", "unresolved_quality_handlers",
                    "invalid_columns", "forbidden_category_cross_edge", "cycles",
                    "legacy_token_unclassified", "unresolved_constraints",
                    "unresolved", "uncovered_stages")
        if isinstance(report[name].get(key), int)
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
