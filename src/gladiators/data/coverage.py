"""Semantic Coverage Manifest builder/validator theo V2 mục 4.5."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, TypedDict

import pandas as pd

from gladiators.domain.catalog import CATALOG, physical_index

CoverageStatus = Literal[
    "exposed_as_dimension", "exposed_as_measure", "identifier_only", "provenance_only",
    "raw_but_unsafe", "uninterpretable", "zero_variance", "proxy_only", "absent",
    "intentionally_hidden",
]

ARTIFACTS = (
    "products_clean.csv", "shop_info_clean.csv", "category_list_clean.csv",
    "product_categories_clean.csv", "category_platform_clean.csv",
    "product_snapshot_metrics.csv", "product_transition_metrics.csv",
)

PROVENANCE_COLUMNS = {"source_file", "source_row", "path_country_code", "path_dataset", "path_shop_id"}
IDENTIFIER_COLUMNS = {
    "product_listing_key", "product_snapshot_key", "shop_id", "item_id", "category_id",
    "shop_category_id", "parent_shop_category_id", "category_slug", "catid", "global_catids",
    "promotion_id_num", "voucher_code", "key",
}
UNINTERPRETABLE_COLUMNS = {"category_type", "category_type_num", "seller_flag", "seller_flag_hash"}
ZERO_VARIANCE_COLUMNS = {"is_ad_bool", "is_sold_out_bool"}


class ManifestEntry(TypedDict):
    table: str
    column: str
    status: CoverageStatus
    catalog_ref: str | None
    reviewed_by: str
    notes: str


def _classify(table: str, column: str) -> ManifestEntry:
    key = f"{table}.{column}"
    obj = physical_index().get(key)
    if obj is not None:
        status: CoverageStatus = obj.answerability
        return {"table": table, "column": column, "status": status, "catalog_ref": obj.ref,
                "reviewed_by": "pending:DR1", "notes": "; ".join(obj.caveats)}
    if column in PROVENANCE_COLUMNS or column.startswith("path_"):
        status = "provenance_only"
        notes = "Pipeline provenance; không expose cho planner."
    elif column in ZERO_VARIANCE_COLUMNS:
        status = "zero_variance"
        notes = "Không có phương sai trong artifact hiện hành; route qua Gate A6/A7."
    elif column in UNINTERPRETABLE_COLUMNS:
        status = "uninterpretable"
        notes = "Không có bảng giải mã/ngữ nghĩa đủ tin cậy."
    elif column in IDENTIFIER_COLUMNS or column.endswith("_key") or column.endswith("_id"):
        status = "identifier_only"
        notes = "Chỉ dùng định danh/join exact; không aggregate."
    else:
        status = "intentionally_hidden"
        notes = "Không nằm trong contract projection vòng hiện tại; cần review trước khi expose."
    return {"table": table, "column": column, "status": status, "catalog_ref": None,
            "reviewed_by": "pending:DR1", "notes": notes}


def build_manifest(data_dir: str | Path) -> dict[str, object]:
    root = Path(data_dir)
    entries: list[ManifestEntry] = []
    for table in ARTIFACTS:
        path = root / table
        if not path.exists():
            raise FileNotFoundError(f"Thiếu artifact bắt buộc: {path}")
        for column in pd.read_csv(path, nrows=0).columns:
            entries.append(_classify(table, str(column)))
    return {"schema_version": "1.0", "review_status": "pending_dr1", "entries": entries}


def validate_manifest(data_dir: str | Path, manifest_path: str | Path | None = None) -> dict[str, int]:
    root = Path(data_dir)
    path = Path(manifest_path) if manifest_path else root / "semantic_coverage_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    keys = [(entry.get("table"), entry.get("column")) for entry in entries]
    if len(keys) != len(set(keys)):
        raise ValueError("Semantic coverage manifest có entry trùng table+column")

    actual = {(table, str(column)) for table in ARTIFACTS for column in pd.read_csv(root / table, nrows=0).columns}
    declared = set(keys)
    if actual != declared:
        missing = sorted(actual - declared)
        unknown = sorted(declared - actual)
        raise ValueError(f"SCHEMA_DRIFT: missing_manifest={missing}; unknown_manifest={unknown}")

    valid_statuses = set(CoverageStatus.__args__)
    for entry in entries:
        status = entry.get("status")
        ref = entry.get("catalog_ref")
        if status not in valid_statuses:
            raise ValueError(f"Coverage status không hợp lệ: {status}")
        if status in {"exposed_as_dimension", "exposed_as_measure", "raw_but_unsafe", "proxy_only"}:
            if ref not in CATALOG:
                raise ValueError(f"Coverage entry thiếu catalog_ref hợp lệ: {entry}")
        elif ref is not None:
            raise ValueError(f"Status {status} không được tự expose catalog_ref: {entry}")
    return {"artifacts": len(ARTIFACTS), "columns": len(entries)}


def write_manifest(data_dir: str | Path, output: str | Path | None = None) -> Path:
    root = Path(data_dir)
    path = Path(output) if output else root / "semantic_coverage_manifest.json"
    path.write_text(json.dumps(build_manifest(root), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
