"""Metadata Binding Layer — Metadata Model & Binding Layer §E1.

Năm registry (table, catalog, relation, metric, invariant) mỗi cái tự nhất quán
nhưng không có ai kiểm chỗ chúng gặp nhau. Catalog sạch tuyệt đối (0/82 mapping
sai) trong khi relation registry vẫn khai một join key không tồn tại ở bất kỳ
bảng nào — cleanliness không lan qua ranh giới registry.

``MetadataBindingSnapshot`` là chỗ ranh giới đó được kiểm một lần, deterministic,
tại startup. Mọi ID phải resolve tới object thật; mọi hash phải phủ toàn bộ
semantics nó tuyên bố ký. Sai binding làm import/startup dừng — không có fallback
suy luận, vì fallback ở tầng này tạo ra con số trôi chảy và sai.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Mapping

from .catalog import CATALOG, CatalogObject
from .invariants import INVARIANTS, InvariantSpec
from .metrics import METRICS, MetricSpec
from .relations import RELATIONS, RelationSpec
from .tables import (
    ArtifactName,
    PhysicalColumnRef,
    TableSpec,
    build_table_registry,
)

DEFAULT_DATA_DIR = "data/processed"
MANIFEST_FILENAME = "semantic_coverage_manifest.json"


class BindingError(ValueError):
    """Raised khi hai registry nói hai điều khác nhau về cùng một thứ."""


def canonical_hash(payload: object, *, length: int = 16) -> str:
    """Hash ổn định: JSON sort-key, UTF-8, không timestamp, không bytes source."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:length]


def quality_check_handlers() -> dict[str, Callable[..., object]]:
    """Handler thật đứng sau mỗi ``QualityCheckRef``.

    Import trễ: ``data.coverage`` đã import ``domain.catalog``, nên nối cạnh này
    ở module level sẽ tạo cycle domain↔data.
    """
    from ..data import contracts, coverage

    return {
        "contracts.validate_artifacts": contracts.validate_artifacts,
        "coverage.validate_manifest": coverage.validate_manifest,
    }


def load_coverage_manifest(data_dir: str | Path = DEFAULT_DATA_DIR) -> dict[str, object]:
    path = Path(data_dir) / MANIFEST_FILENAME
    if not path.exists():
        raise BindingError(f"Thiếu coverage manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


# --- hash payloads --------------------------------------------------------
# Mỗi payload phải phủ TOÀN BỘ semantics của registry tương ứng. Hash bỏ sót một
# field nghĩa là field đó đổi được mà cache/gate/proof pack vẫn coi là cùng một
# thế giới — đúng lỗi mà `invariants.REGISTRY_HASH` cũ mắc phải (§E3.1).

def _table_payload(tables: Mapping[ArtifactName, TableSpec]) -> list[dict[str, object]]:
    return [
        {
            "name": spec.name.value, "view": spec.view_name, "storage": spec.storage,
            "grain": list(spec.grain), "version_policy": spec.version_policy,
            "columns": [
                {"name": column.name, "type": column.physical_type,
                 "status": column.coverage_status, "catalog_ref": column.catalog_ref,
                 "partition": column.partition}
                for column in spec.columns
            ],
            "quality_checks": [
                {"check_id": check.check_id, "handler_id": check.handler_id,
                 "severity": check.severity}
                for check in spec.quality_checks
            ],
        }
        for spec in sorted(tables.values(), key=lambda item: item.name.value)
    ]


def _catalog_payload(catalog: Mapping[str, CatalogObject]) -> list[dict[str, object]]:
    return [
        {
            "ref": obj.ref, "kind": obj.kind, "aliases": list(obj.aliases),
            "physical": [str(binding) for binding in obj.physical_bindings],
            "type": obj.type, "unit": obj.unit, "grain": obj.grain,
            "valid_aggregations": list(obj.valid_aggregations),
            "time_semantics": obj.time_semantics,
            "allowed_filters": list(obj.allowed_filters),
            "cardinality": obj.cardinality, "caveats": list(obj.caveats),
            "traps": list(obj.traps), "provenance": obj.provenance,
            "value_index": list(obj.value_index) if obj.value_index else None,
            "answerability": obj.answerability, "source_tier": obj.source_tier,
            "analysis_role": obj.analysis_role, "counting_key": obj.counting_key,
            "counts_unit": obj.counts_unit,
        }
        for obj in sorted(catalog.values(), key=lambda item: item.ref)
    ]


def _relation_payload(relations: Mapping[str, RelationSpec]) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for spec in sorted(relations.values(), key=lambda item: item.name):
        binding = spec.binding
        payload.append({
            "name": spec.name, "left": spec.left, "right": spec.right,
            "source": spec.source, "scope": list(spec.scope),
            "interpretation": spec.interpretation, "traps": list(spec.traps),
            "cardinality": spec.cardinality, "direction": spec.direction,
            "input_grain": spec.input_grain, "output_grain": spec.output_grain,
            "fanout_effect": spec.fanout_effect, "dedupe_strategy": spec.dedupe_strategy,
            "temporal_validity": spec.temporal_validity, "coverage": spec.coverage,
            "path_cost": spec.path_cost, "risk": spec.risk,
            "binding": None if binding is None else {
                "mode": binding.mode,
                "left_sources": [name.value for name in binding.left_sources],
                "right_source": None if binding.right_source is None else binding.right_source.value,
                "join_keys": [[str(key.left), str(key.right)] for key in binding.join_keys],
                "projection_id": binding.projection_id,
            },
        })
    return payload


def _metric_payload(metrics: Mapping[str, MetricSpec]) -> list[dict[str, object]]:
    return [
        {
            "name": spec.name, "grain": spec.grain, "unit": spec.unit,
            "dedupe": spec.dedupe, "caveats": list(spec.caveats),
            "traps": list(spec.traps), "depends_on": list(spec.depends_on),
            "valid_aggregations": list(spec.valid_aggregations), "formula": spec.formula,
            "source_columns": list(spec.source_columns),
            "source_metrics": list(spec.source_metrics),
            "owner": spec.owner, "tags": list(spec.tags),
            "definition_constraints": [
                {"constraint_id": constraint.constraint_id, "ref": constraint.ref,
                 "op": constraint.op, "values": list(constraint.values),
                 "null_policy": constraint.null_policy, "decision_id": constraint.decision_id}
                for constraint in spec.definition_constraints
            ],
        }
        for spec in sorted(metrics.values(), key=lambda item: item.name)
    ]


def _invariant_payload(invariants: Mapping[str, InvariantSpec]) -> dict[str, object]:
    """Spec + handler. Đổi cách một rule được THI HÀNH cũng là đổi rule, nên
    handler version phải invalidate execution context và proof pack như spec."""
    from .invariant_handlers import HANDLER_PAYLOAD

    return {
        "specs": [
            spec.model_dump(mode="json")
            for spec in sorted(invariants.values(), key=lambda item: item.invariant_id)
        ],
        "handlers": list(HANDLER_PAYLOAD),
    }


# --- snapshot -------------------------------------------------------------

@dataclass(frozen=True)
class MetadataBindingSnapshot:
    tables: Mapping[ArtifactName, TableSpec]
    catalog: Mapping[str, CatalogObject]
    relations: Mapping[str, RelationSpec]
    metrics: Mapping[str, MetricSpec]
    invariants: Mapping[str, InvariantSpec]

    table_hash: str
    catalog_hash: str
    relation_hash: str
    metric_hash: str
    invariant_hash: str
    binding_hash: str

    # Index tra cứu, sinh một lần để consumer không tự dựng lại (mỗi bản dựng
    # lại là một cơ hội để hai consumer bất đồng).
    view_by_artifact: Mapping[ArtifactName, str]
    artifact_by_view: Mapping[str, ArtifactName]
    columns_by_artifact: Mapping[ArtifactName, frozenset[str]]
    catalog_by_physical: Mapping[str, str]

    def has_column(self, ref: PhysicalColumnRef) -> bool:
        return ref.column in self.columns_by_artifact.get(ref.table, frozenset())

    def require_column(self, ref: PhysicalColumnRef, context: str) -> None:
        if not self.has_column(ref):
            raise BindingError(f"{context}: cột không tồn tại: {ref}")

    def counts(self) -> dict[str, int]:
        return {
            "tables": len(self.tables),
            "columns": sum(len(spec.columns) for spec in self.tables.values()),
            "catalog_objects": len(self.catalog),
            "catalog_bindings": sum(len(obj.physical_bindings) for obj in self.catalog.values()),
            "relations": len(self.relations),
            "metrics": len(self.metrics),
            "invariants": len(self.invariants),
        }


def _check_tables(tables: Mapping[ArtifactName, TableSpec]) -> None:
    if set(tables) != set(ArtifactName):
        raise BindingError(
            f"Table registry không phủ đủ artifact: thiếu "
            f"{sorted(n.value for n in set(ArtifactName) - set(tables))}"
        )
    views = [spec.view_name for spec in tables.values()]
    if len(views) != len(set(views)):
        raise BindingError(f"View name trùng trong table registry: {sorted(views)}")


def _check_catalog(
    tables: Mapping[ArtifactName, TableSpec], catalog: Mapping[str, CatalogObject]
) -> dict[str, str]:
    by_physical: dict[str, str] = {}
    for obj in catalog.values():
        for binding in obj.physical_bindings:
            table = tables.get(binding.table)
            if table is None:
                raise BindingError(f"{obj.ref}: bind tới artifact ngoài registry: {binding}")
            if not table.has_column(binding.column):
                raise BindingError(f"{obj.ref}: cột không tồn tại trong manifest: {binding}")
            key = str(binding)
            if key in by_physical:
                raise BindingError(
                    f"Physical column {key} thuộc cả {by_physical[key]} và {obj.ref}"
                )
            by_physical[key] = obj.ref
        # Lặp lại kiểm của catalog ở tầng binding: catalog chỉ biết chuỗi, ở đây
        # mới biết cột có thật, nên "physical_dimension mà không có cột" phải
        # được chặn bằng binding đã resolve chứ không bằng chuỗi.
        if obj.analysis_role == "physical_dimension" and not obj.physical_bindings:
            raise BindingError(f"{obj.ref} khai physical_dimension nhưng không có binding")
    return by_physical


def validate_metadata_bindings(
    tables: Mapping[ArtifactName, TableSpec],
    catalog: Mapping[str, CatalogObject] = CATALOG,
    relations: Mapping[str, RelationSpec] = RELATIONS,
    metrics: Mapping[str, MetricSpec] = METRICS,
    invariants: Mapping[str, InvariantSpec] = INVARIANTS,
) -> MetadataBindingSnapshot:
    _check_tables(tables)
    catalog_by_physical = _check_catalog(tables, catalog)
    _check_relations(tables, relations)
    _check_metrics(tables, catalog, metrics)
    _check_invariants(catalog, invariants)

    table_hash = canonical_hash(_table_payload(tables))
    catalog_hash = canonical_hash(_catalog_payload(catalog))
    relation_hash = canonical_hash(_relation_payload(relations))
    metric_hash = canonical_hash(_metric_payload(metrics))
    invariant_hash = canonical_hash(_invariant_payload(invariants))
    binding_hash = canonical_hash({
        "table": table_hash, "catalog": catalog_hash, "relation": relation_hash,
        "metric": metric_hash, "invariant": invariant_hash,
    })

    return MetadataBindingSnapshot(
        tables=dict(tables), catalog=dict(catalog), relations=dict(relations),
        metrics=dict(metrics), invariants=dict(invariants),
        table_hash=table_hash, catalog_hash=catalog_hash, relation_hash=relation_hash,
        metric_hash=metric_hash, invariant_hash=invariant_hash, binding_hash=binding_hash,
        view_by_artifact={name: spec.view_name for name, spec in tables.items()},
        artifact_by_view={spec.view_name: name for name, spec in tables.items()},
        columns_by_artifact={
            name: frozenset(column.name for column in spec.columns)
            for name, spec in tables.items()
        },
        catalog_by_physical=catalog_by_physical,
    )


def _check_relations(
    tables: Mapping[ArtifactName, TableSpec], relations: Mapping[str, RelationSpec]
) -> None:
    """Relation binding là nguồn executable duy nhất (§E2).

    Mọi cột trong binding phải tồn tại ở đúng bảng nó khai; ``inline`` không được
    có right source hay join key. Không kiểm ở đây thì `raw_brand` (không tồn tại
    ở bất kỳ bảng nào) tiếp tục sống trong registry cho tới khi đổi adapter.
    """
    for spec in relations.values():
        binding = spec.binding
        if binding is None:
            raise BindingError(f"Relation thiếu binding: {spec.name}")
        for source in binding.left_sources:
            if source not in tables:
                raise BindingError(f"{spec.name}: left source ngoài registry: {source}")
        if binding.mode == "inline":
            if binding.right_source is not None or binding.join_keys:
                raise BindingError(
                    f"{spec.name}: inline relation không được khai right source/join key"
                )
            continue
        if binding.right_source is None:
            raise BindingError(f"{spec.name}: left_join thiếu right source")
        if binding.right_source not in tables:
            raise BindingError(f"{spec.name}: right source ngoài registry: {binding.right_source}")
        if not binding.join_keys:
            raise BindingError(f"{spec.name}: left_join thiếu join key")
        for key in binding.join_keys:
            if key.left.table not in binding.left_sources:
                raise BindingError(
                    f"{spec.name}: join key trái thuộc bảng không phải left source: {key.left}"
                )
            if key.right.table != binding.right_source:
                raise BindingError(
                    f"{spec.name}: join key phải thuộc bảng không phải right source: {key.right}"
                )
            if not tables[key.left.table].has_column(key.left.column):
                raise BindingError(f"{spec.name}: cột không tồn tại: {key.left}")
            if not tables[key.right.table].has_column(key.right.column):
                raise BindingError(f"{spec.name}: cột không tồn tại: {key.right}")


def _check_metrics(
    tables: Mapping[ArtifactName, TableSpec],
    catalog: Mapping[str, CatalogObject],
    metrics: Mapping[str, MetricSpec],
) -> None:
    """Lineage phải resolve; constraint ref phải có catalog binding (§E4)."""
    from .metrics import build_metric_graph

    graph = build_metric_graph(metrics)
    all_columns = {column.name for spec in tables.values() for column in spec.columns}
    for spec in metrics.values():
        unknown = [column for column in spec.source_columns if column not in all_columns]
        if unknown:
            raise BindingError(f"{spec.name}: source column không tồn tại: {unknown}")
        for constraint in spec.definition_constraints:
            if constraint.ref not in catalog:
                raise BindingError(
                    f"{spec.name}: constraint {constraint.constraint_id} trỏ semantic ref "
                    f"không tồn tại: {constraint.ref}"
                )
    if graph.cycles:
        raise BindingError(f"Metric graph có cycle: {graph.cycles}")


def _check_invariants(
    catalog: Mapping[str, CatalogObject], invariants: Mapping[str, InvariantSpec]
) -> None:
    """Mọi ref phải resolve VÀ mọi validator_id phải trỏ tới handler thật (§E3).

    Import ``invariant_handlers`` chính là phép kiểm: module đó chạy
    ``_check_dispatch`` ở import time và fail nếu một spec không resolve, nên
    binding snapshot không thể build trên một registry chỉ-có-prose.
    """
    from . import invariant_handlers

    for spec in invariants.values():
        missing = [ref for ref in spec.semantic_refs if ref not in catalog]
        if missing:
            raise BindingError(f"{spec.invariant_id}: semantic ref không tồn tại: {missing}")
        if spec.validator_id not in invariant_handlers.INVARIANT_HANDLERS:
            raise BindingError(
                f"{spec.invariant_id}: validator_id không có handler: {spec.validator_id}"
            )


def build_binding_snapshot(data_dir: str | Path = DEFAULT_DATA_DIR) -> MetadataBindingSnapshot:
    tables = build_table_registry(
        load_coverage_manifest(data_dir), quality_handlers=quality_check_handlers()
    )
    return validate_metadata_bindings(tables)


@lru_cache(maxsize=4)
def default_binding_snapshot(data_dir: str = DEFAULT_DATA_DIR) -> MetadataBindingSnapshot:
    """Snapshot dùng ở startup và bởi mọi consumer runtime.

    Cache theo data_dir: snapshot bất biến và build lại tốn một lần đọc manifest
    219 dòng; cache giữ cho mọi consumer thấy cùng một hash.
    """
    return build_binding_snapshot(data_dir)
