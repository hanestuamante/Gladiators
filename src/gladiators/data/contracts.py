from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pandera.pandas as pa

from .coverage import validate_manifest


SCHEMAS: dict[str, pa.DataFrameSchema] = {
    "products_clean.csv": pa.DataFrameSchema({
        "product_listing_key": pa.Column(str, nullable=False),
        "product_snapshot_key": pa.Column(str, nullable=False),
        "country_code": pa.Column(str, pa.Check.isin(["vn", "id"])),
        "date": pa.Column(str), "shop_id": pa.Column(object), "item_id": pa.Column(object),
        "product_name": pa.Column(str), "product_name_clean": pa.Column(str),
        "price_num": pa.Column(float, nullable=True, coerce=True),
        "monthly_sold_value_num": pa.Column(float, nullable=True, coerce=True),
    }, strict=False, coerce=True),
    "product_snapshot_metrics.csv": pa.DataFrameSchema({
        "product_listing_key": pa.Column(str), "product_snapshot_key": pa.Column(str),
        "country_code": pa.Column(str, pa.Check.isin(["vn", "id"])), "date": pa.Column(str),
        "product_name": pa.Column(str), "price_num": pa.Column(float, nullable=True, coerce=True),
        "monthly_sold_value_num": pa.Column(float, nullable=True, coerce=True),
    }, strict=False, coerce=True),
    "product_transition_metrics.csv": pa.DataFrameSchema({
        "product_listing_key": pa.Column(str), "country_code": pa.Column(str),
        "previous_date": pa.Column(str), "date": pa.Column(str),
        "transition_metric_eligible": pa.Column(bool, coerce=True),
        "monthly_sold_delta": pa.Column(float, nullable=True, coerce=True),
    }, strict=False, coerce=True),
}


def validate_artifacts(data_dir: str | Path) -> dict[str, dict[str, object]]:
    root = Path(data_dir)
    coverage = validate_manifest(root)
    report_path = root / "pipeline_report.json"
    if not report_path.exists():
        raise FileNotFoundError(f"Thiếu {report_path}")
    pipeline = json.loads(report_path.read_text(encoding="utf-8"))
    result: dict[str, dict[str, object]] = {}
    for name, schema in SCHEMAS.items():
        path = root / name
        frame = pd.read_csv(path)
        missing = sorted(set(schema.columns) - set(frame.columns))
        if missing:
            raise ValueError(f"{name} thiếu cột theo contract: {missing}")
        schema.validate(frame, lazy=True)
        result[name] = {"rows": len(frame), "columns": list(frame.columns)}
    result["pipeline_report.json"] = {"status": pipeline.get("status", "unknown")}
    result["semantic_coverage_manifest.json"] = coverage
    return result
