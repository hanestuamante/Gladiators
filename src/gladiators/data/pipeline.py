"""Bước làm sạch dữ liệu — TRÍCH NGUYÊN VĂN từ notebooks/pipeline/data_pipeline.ipynb.

Logic bên dưới **không đổi một dòng nào**. Nó vốn đã đúng và đủ; thứ hỏng là chỗ
nó *sống*: hai cell notebook phải bấm Run All bằng tay, nên không CI nào chạy lại
được, không ai ngoài người viết chạy lại được, và không có gì để rollback về.

Đưa nó vào một module khiến nó thành một **hàm thuần** ``run_pipeline(input, output)``
— gọi được từ CLI, từ test, từ CI, và từ chính notebook cũ. Một bản duy nhất, nên
không có chuyện hai bản trôi khỏi nhau.

Kiểm chứng của phép trích: chạy lại nó phải dựng lại ``data/processed`` **y hệt
từng byte**. Xem ``scripts/build_dataset.py --verify-against``.
"""

from __future__ import annotations

#!/usr/bin/env python3
"""Auditable minimum data pipeline and metric layer for the Shopee snapshots."""


import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DATASETS = {
    "products": "products.csv",
    "shop_info": "shop_info.csv",
    "category_list": "category_list.csv",
    "product_categories": "product_categories.csv",
    "category_platform": "category_platform.csv",
}

KEYS = {
    "products": ["country_code", "shop_id", "item_id", "date"],
    "shop_info": ["country_code", "shop_id"],
    "category_list": ["country_code", "shop_id", "shop_category_id", "date"],
    "product_categories": ["country_code", "shop_id", "item_id", "category_id", "date"],
    "category_platform": ["country_code", "category_id"],
}

NUMERIC_COLUMNS = {
    "products": [
        "ctime", "price", "price_original", "price_before_promo", "discount_percent",
        "promotion_id", "voucher_discount", "voucher_start_time", "voucher_end_time",
        "voucher_min_spend", "history_sold_value", "monthly_sold_value", "rating",
        "rating_count", "brand_id", "catid", "liked_count",
    ],
    "shop_info": [
        "rating_star", "follower_count", "item_count", "response_rate", "response_time",
        "rating_good", "rating_normal", "rating_bad", "cancellation_rate",
    ],
    "category_list": ["shop_category_id", "total", "parent_shop_category_id", "category_type"],
    "product_categories": ["item_id", "category_slug", "category_id"],
    "category_platform": ["client", "category_id", "parent_category_id"],
}

BOOLEAN_COLUMNS = {
    "products": ["is_ad", "is_sold_out", "shopee_verified"],
    "shop_info": ["is_official_shop", "vacation"],
    "category_list": ["is_parent_category", "is_sub_category"],
    "category_platform": ["has_children"],
}

ARRAY_COLUMNS = {
    "products": [
        "images", "seller_flag", "seller_flag_hash", "rating_count_detail", "vouchers",
        "global_catids", "tier_variation_options",
    ]
}

PRICE_SENTINEL = 999_999_999


@dataclass
class Issue:
    severity: str
    code: str
    dataset: str
    source_file: str = ""
    source_row: Any = ""
    entity_key: str = ""
    field: str = ""
    raw_value: str = ""
    message: str = ""


def clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def parse_path(path: Path) -> dict[str, str]:
    result = {"path_country_code": "", "path_dataset": "", "path_shop_id": ""}
    for part in path.parts:
        for prefix, field in (
            ("country_code=", "path_country_code"),
            ("dataset=", "path_dataset"),
            ("shop_id=", "path_shop_id"),
        ):
            if part.startswith(prefix):
                result[field] = part.split("=", 1)[1]
    return result


def entity_key(row: pd.Series, fields: list[str]) -> str:
    return ":".join(clean_text(row.get(field, "")) for field in fields)


def add_issue(issues: list[Issue], severity: str, code: str, dataset: str,
              row: pd.Series | None = None, field: str = "", raw_value: Any = "",
              message: str = "", key_fields: list[str] | None = None) -> None:
    issues.append(Issue(
        severity=severity,
        code=code,
        dataset=dataset,
        source_file=clean_text(row.get("source_file", "")) if row is not None else "",
        source_row=row.get("source_row", "") if row is not None else "",
        entity_key=entity_key(row, key_fields or KEYS.get(dataset, [])) if row is not None else "",
        field=field,
        raw_value=clean_text(raw_value),
        message=message,
    ))


def safe_bool(value: Any) -> Any:
    normalized = clean_text(value).lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return pd.NA


def safe_array(value: Any) -> tuple[list[Any] | None, str | None]:
    raw = clean_text(value)
    if not raw:
        return [], None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, str(exc)
    if not isinstance(parsed, list):
        return None, "JSON value is not an array"
    return parsed, None


def load_raw(input_dir: Path, issues: list[Issue]) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    frames: dict[str, list[pd.DataFrame]] = {name: [] for name in DATASETS}
    files: list[dict[str, Any]] = []
    expected_schema: dict[str, tuple[str, ...]] = {}

    repo_root = input_dir.resolve().parents[1]
    for path in sorted(input_dir.rglob("*.csv")):
        source_path = path.resolve().relative_to(repo_root).as_posix()
        meta = parse_path(path)
        dataset = meta["path_dataset"]
        if dataset not in DATASETS:
            add_issue(issues, "warning", "UNKNOWN_DATASET", dataset or "unknown",
                      message=f"Ignored unsupported CSV: {path.as_posix()}")
            continue
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        schema = tuple(frame.columns)
        if dataset not in expected_schema:
            expected_schema[dataset] = schema
        elif schema != expected_schema[dataset]:
            add_issue(issues, "error", "SCHEMA_MISMATCH", dataset,
                      message=f"Schema differs in {path.as_posix()}")

        frame = frame.apply(lambda col: col.map(clean_text))
        frame["source_file"] = source_path
        frame["source_row"] = np.arange(2, len(frame) + 2)
        for field, value in meta.items():
            frame[field] = value

        for field, path_field in (("country_code", "path_country_code"), ("shop_id", "path_shop_id")):
            if field not in frame:
                frame[field] = ""
            mismatch = frame[field].ne("") & frame[path_field].ne("") & frame[field].ne(frame[path_field])
            for _, row in frame.loc[mismatch].iterrows():
                add_issue(issues, "error", "PATH_VALUE_MISMATCH", dataset, row, field,
                          row[field], f"Value conflicts with {path_field}={row[path_field]}")
            frame[field] = frame[field].mask(frame[field].eq(""), frame[path_field])

        frames[dataset].append(frame)
        files.append({"file": source_path, "dataset": dataset, "rows": len(frame), "columns": len(schema)})

    combined = {
        dataset: pd.concat(parts, ignore_index=True, sort=False) if parts else pd.DataFrame()
        for dataset, parts in frames.items()
    }
    return combined, {"files": files, "file_count": len(files)}


def normalize(dataset: str, frame: pd.DataFrame, issues: list[Issue]) -> pd.DataFrame:
    if frame.empty:
        add_issue(issues, "error", "DATASET_EMPTY", dataset, message="No input rows found")
        return frame
    result = frame.copy()

    raw_columns = [c for c in result.columns if c not in {
        "source_file", "source_row", "path_country_code", "path_dataset", "path_shop_id"
    }]
    duplicate_mask = result.duplicated(subset=raw_columns + ["source_file"], keep="first")
    for _, row in result.loc[duplicate_mask].iterrows():
        add_issue(issues, "warning", "EXACT_DUPLICATE_REMOVED", dataset, row,
                  message="Exact duplicate excluded from clean output; raw row remains traceable")
    result = result.loc[~duplicate_mask].copy()

    for field in KEYS[dataset]:
        if field not in result:
            result[field] = ""
        for _, row in result.loc[result[field].eq("")].iterrows():
            add_issue(issues, "error", "MISSING_KEY", dataset, row, field,
                      message="Required key component is missing")

    for field in NUMERIC_COLUMNS.get(dataset, []):
        if field not in result:
            continue
        converted = pd.to_numeric(result[field].replace("", pd.NA), errors="coerce")
        invalid = result[field].ne("") & converted.isna()
        for _, row in result.loc[invalid].iterrows():
            add_issue(issues, "error", "INVALID_NUMBER", dataset, row, field, row[field],
                      "Value cannot be converted safely; numeric output kept null")
        result[f"{field}_num"] = converted.astype("Float64")

    for field in BOOLEAN_COLUMNS.get(dataset, []):
        if field not in result:
            continue
        result[f"{field}_bool"] = result[field].map(safe_bool).astype("boolean")
        invalid = result[field].ne("") & result[f"{field}_bool"].isna()
        for _, row in result.loc[invalid].iterrows():
            add_issue(issues, "error", "INVALID_BOOLEAN", dataset, row, field, row[field],
                      "Value cannot be converted safely; boolean output kept null")

    for field in ARRAY_COLUMNS.get(dataset, []):
        if field not in result:
            continue
        parsed = result[field].map(safe_array)
        result[f"{field}_count"] = parsed.map(lambda pair: len(pair[0]) if pair[0] is not None else pd.NA).astype("Int64")
        invalid = parsed.map(lambda pair: pair[1] is not None)
        for idx, row in result.loc[invalid].iterrows():
            add_issue(issues, "error", "INVALID_JSON_ARRAY", dataset, row, field, row[field], parsed.loc[idx][1])

    if "date" in result:
        parsed_date = pd.to_datetime(result["date"].replace("", pd.NA), errors="coerce")
        invalid = result["date"].ne("") & parsed_date.isna()
        for _, row in result.loc[invalid].iterrows():
            add_issue(issues, "error", "INVALID_DATE", dataset, row, "date", row["date"],
                      "Date must be parseable before snapshot metrics are calculated")

    key_fields = KEYS[dataset]
    duplicate_key = result.duplicated(key_fields, keep=False) & result[key_fields].ne("").all(axis=1)
    for _, row in result.loc[duplicate_key].iterrows():
        add_issue(issues, "error", "DUPLICATE_KEY", dataset, row,
                  message="Logical key is not unique; row retained and reported")

    if dataset == "products":
        result["product_name_clean"] = result.get("product_name", "").map(clean_text)
        result["product_listing_key"] = result[["country_code", "shop_id", "item_id"]].agg(":".join, axis=1)
        result["product_snapshot_key"] = result[["country_code", "shop_id", "item_id", "date"]].agg(":".join, axis=1)
    return result


def check_relationships(tables: dict[str, pd.DataFrame], issues: list[Issue]) -> None:
    products = tables["products"]
    shops = tables["shop_info"]
    mappings = tables["product_categories"]
    categories = tables["category_list"]
    platform = tables["category_platform"]

    shop_keys = set(map(tuple, shops[["country_code", "shop_id"]].astype(str).to_numpy()))
    for _, row in products.iterrows():
        if (row["country_code"], row["shop_id"]) not in shop_keys:
            add_issue(issues, "warning", "ORPHAN_PRODUCT_SHOP", "products", row,
                      message="No shop_info row for country_code + shop_id")

    product_keys = set(map(tuple, products[["country_code", "shop_id", "item_id", "date"]].astype(str).to_numpy()))
    for _, row in mappings.iterrows():
        key = tuple(str(row[c]) for c in ["country_code", "shop_id", "item_id", "date"])
        if key not in product_keys:
            add_issue(issues, "warning", "ORPHAN_CATEGORY_MAPPING_PRODUCT", "product_categories", row,
                      message="Category mapping has no matching product snapshot")

    category_keys = set(map(tuple, categories[["country_code", "shop_id", "shop_category_id", "date"]].astype(str).to_numpy()))
    for _, row in mappings.iterrows():
        key = tuple(str(row[c]) for c in ["country_code", "shop_id", "category_id", "date"])
        if key not in category_keys:
            add_issue(issues, "warning", "ORPHAN_CATEGORY_MAPPING_SHELF", "product_categories", row,
                      message="Category mapping has no matching shop category")

    platform_keys = set(map(tuple, platform[["country_code", "category_id"]].astype(str).to_numpy()))
    for _, row in products.iterrows():
        if (str(row["country_code"]), str(row["catid"])) not in platform_keys:
            add_issue(issues, "warning", "ORPHAN_PLATFORM_CATEGORY", "products", row, "catid", row["catid"],
                      "Top-level platform category is not present for this country")


def add_snapshot_checks(products: pd.DataFrame, issues: list[Issue]) -> pd.DataFrame:
    result = products.copy()
    result["snapshot_gap_flag"] = False
    dates = sorted(pd.to_datetime(result["date"], errors="coerce").dropna().unique())
    if not dates:
        add_issue(issues, "error", "NO_VALID_SNAPSHOT_DATE", "products", message="No valid date available")
        return result
    expected = set(pd.date_range(min(dates), max(dates), freq="D"))
    listing_fields = ["country_code", "shop_id", "item_id"]
    for _, group in result.groupby(listing_fields, dropna=False):
        observed = set(pd.to_datetime(group["date"], errors="coerce").dropna())
        missing = sorted(expected - observed)
        if not missing:
            continue
        internal = [d for d in missing if min(observed) < d < max(observed)] if observed else []
        code = "INTERNAL_SNAPSHOT_GAP" if internal else "EDGE_SNAPSHOT_MISSING"
        message = "Missing dates: " + ", ".join(pd.Timestamp(d).strftime("%Y-%m-%d") for d in missing)
        first = group.iloc[0]
        add_issue(issues, "warning", code, "products", first, message=message, key_fields=listing_fields)
        if internal:
            result.loc[group.index, "snapshot_gap_flag"] = True
    return result


def build_metrics(products: pd.DataFrame, issues: list[Issue]) -> tuple[pd.DataFrame, pd.DataFrame]:
    p = products.copy()
    p["date_parsed"] = pd.to_datetime(p["date"], errors="coerce")
    p["price_sentinel_flag"] = p["price_num"].eq(PRICE_SENTINEL)
    for _, row in p.loc[p["price_sentinel_flag"]].iterrows():
        add_issue(issues, "warning", "PRICE_SENTINEL", "products", row, "price", row["price"],
                  "Excluded from price and revenue metrics, but row is retained")

    usable_price = p["price_num"].mask(p["price_sentinel_flag"])
    usable_original = p["price_original_num"].mask(p["price_original_num"].eq(PRICE_SENTINEL))
    p["estimated_recent_revenue"] = usable_price * p["monthly_sold_value_num"]
    p["discount_amount"] = usable_original - usable_price
    p["discount_percent_analysis"] = p["discount_percent_num"]
    fill_zero = p["discount_percent_analysis"].isna() & usable_price.eq(usable_original)
    p.loc[fill_zero, "discount_percent_analysis"] = 0
    bad_missing_discount = p["discount_percent_analysis"].isna() & usable_price.notna() & usable_original.notna() & usable_price.ne(usable_original)
    for _, row in p.loc[bad_missing_discount].iterrows():
        add_issue(issues, "warning", "MISSING_DISCOUNT_INCONSISTENT_PRICE", "products", row, "discount_percent",
                  message="Discount remains null because price differs from original price")
    denominator_ok = usable_original.notna() & usable_original.ne(0)
    p["pre_final_reduction_proxy"] = np.where(
        denominator_ok,
        100 * (usable_original - p["price_before_promo_num"]) / usable_original,
        np.nan,
    )
    p["has_displayed_discount"] = p["discount_percent_analysis"].gt(0).astype("boolean")
    p["has_structured_voucher"] = p["voucher_discount_num"].fillna(0).gt(0).astype("boolean")
    p["promotion_id_clean"] = p["promotion_id_num"].mask(p["promotion_id_num"].eq(0))

    snapshot_columns = [
        "product_listing_key", "product_snapshot_key", "country_code", "shop_id", "item_id", "date",
        "product_name", "snapshot_gap_flag", "price_sentinel_flag", "price_num", "price_original_num",
        "monthly_sold_value_num", "history_sold_value_num", "rating_num", "rating_count_num",
        "liked_count_num", "estimated_recent_revenue", "discount_amount", "discount_percent_analysis",
        "pre_final_reduction_proxy", "has_displayed_discount", "has_structured_voucher",
        "promotion_id_clean", "voucher_discount_num", "is_sold_out_bool", "source_file", "source_row",
    ]
    snapshots = p[snapshot_columns].copy()

    ordered = p.sort_values(["country_code", "shop_id", "item_id", "date_parsed"])
    group = ordered.groupby(["country_code", "shop_id", "item_id"], dropna=False)
    previous_fields = [
        "date_parsed", "price_num", "discount_percent_analysis", "monthly_sold_value_num",
        "history_sold_value_num", "rating_num", "rating_count_num", "liked_count_num", "is_sold_out_bool",
        "has_structured_voucher",
    ]
    for field in previous_fields:
        ordered[f"previous_{field}"] = group[field].shift(1)
    transitions = ordered.loc[ordered["previous_date_parsed"].notna()].copy()
    transitions["days_since_previous"] = (transitions["date_parsed"] - transitions["previous_date_parsed"]).dt.days
    transitions["transition_metric_eligible"] = transitions["days_since_previous"].eq(1)

    eligible = transitions["transition_metric_eligible"]
    valid_price = eligible & ~transitions["price_num"].eq(PRICE_SENTINEL) & ~transitions["previous_price_num"].eq(PRICE_SENTINEL)
    transitions["price_change"] = (transitions["price_num"] - transitions["previous_price_num"]).where(valid_price)
    transitions["price_change_percent"] = (
        100 * transitions["price_change"] / transitions["previous_price_num"]
    ).where(valid_price & transitions["previous_price_num"].ne(0))
    transitions["discount_point_change"] = (
        transitions["discount_percent_analysis"] - transitions["previous_discount_percent_analysis"]
    ).where(eligible)
    transitions["monthly_sold_delta"] = (
        transitions["monthly_sold_value_num"] - transitions["previous_monthly_sold_value_num"]
    ).where(eligible)
    transitions["history_sold_delta_raw"] = (
        transitions["history_sold_value_num"] - transitions["previous_history_sold_value_num"]
    ).where(eligible)
    transitions["history_sold_decrease_flag"] = transitions["history_sold_delta_raw"].lt(0).fillna(False)
    transitions["snapshot_sales_delta_clean"] = transitions["history_sold_delta_raw"].mask(
        transitions["history_sold_decrease_flag"]
    )
    for _, row in transitions.loc[transitions["history_sold_decrease_flag"]].iterrows():
        add_issue(issues, "warning", "HISTORY_SOLD_DECREASE", "products", row, "history_sold_value",
                  row["history_sold_value"], "Raw delta retained; clean incremental-sales metric set null")

    transitions["rating_change"] = (transitions["rating_num"] - transitions["previous_rating_num"]).where(eligible)
    transitions["new_rating_count"] = (transitions["rating_count_num"] - transitions["previous_rating_count_num"]).where(eligible)
    transitions["like_delta"] = (transitions["liked_count_num"] - transitions["previous_liked_count_num"]).where(eligible)
    previous_stock = transitions["previous_is_sold_out_bool"].astype("boolean")
    current_stock = transitions["is_sold_out_bool"].astype("boolean")
    transitions["stock_status"] = np.select(
        [~previous_stock.fillna(False) & current_stock.fillna(False),
         previous_stock.fillna(False) & ~current_stock.fillna(False),
         previous_stock.fillna(False) & current_stock.fillna(False)],
        ["newly_sold_out", "restocked", "still_sold_out"],
        default="available",
    )
    transitions.loc[~eligible, "stock_status"] = "not_comparable_snapshot_gap"
    transitions["previous_date"] = transitions["previous_date_parsed"].dt.strftime("%Y-%m-%d")

    transition_columns = [
        "product_listing_key", "country_code", "shop_id", "item_id", "previous_date", "date",
        "days_since_previous", "transition_metric_eligible", "price_change", "price_change_percent",
        "discount_point_change", "monthly_sold_delta", "history_sold_delta_raw",
        "history_sold_decrease_flag", "snapshot_sales_delta_clean", "rating_change",
        "new_rating_count", "like_delta", "previous_has_structured_voucher",
        "has_structured_voucher", "stock_status", "source_file", "source_row",
    ]
    return snapshots, transitions[transition_columns].copy()


def write_outputs(output_dir: Path, tables: dict[str, pd.DataFrame], snapshots: pd.DataFrame,
                  transitions: pd.DataFrame, issues: list[Issue], metadata: dict[str, Any]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[str] = []
    for dataset, frame in tables.items():
        path = output_dir / f"{dataset}_clean.csv"
        frame.to_csv(path, index=False)
        outputs.append(path.name)
    for name, frame in (("product_snapshot_metrics", snapshots), ("product_transition_metrics", transitions)):
        path = output_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        outputs.append(path.name)

    issue_frame = pd.DataFrame([asdict(issue) for issue in issues], columns=list(Issue.__annotations__))
    issue_path = output_dir / "data_quality_issues.csv"
    issue_frame.to_csv(issue_path, index=False)
    outputs.append(issue_path.name)
    counts = issue_frame.groupby(["severity", "code"]).size().to_dict() if not issue_frame.empty else {}
    key_checks = {}
    for dataset, frame in tables.items():
        keys = KEYS[dataset]
        key_checks[dataset] = {
            "key": keys,
            "missing_key_rows": int(frame[keys].eq("").any(axis=1).sum()),
            "duplicate_key_rows": int(frame.duplicated(keys, keep=False).sum()),
        }
    products = tables["products"]
    snapshot_dates = sorted(products["date"].dropna().astype(str).unique())
    listing_count = int(products["product_listing_key"].nunique())
    balanced_cells = listing_count * len(snapshot_dates)
    snapshot_checks = {
        "dates": snapshot_dates,
        "rows_by_date": {str(k): int(v) for k, v in products.groupby("date").size().items()},
        "listing_count": listing_count,
        "balanced_panel_cells": balanced_cells,
        "observed_cells": len(products),
        "missing_cells": balanced_cells - len(products),
        "internal_gap_listings": sum(issue.code == "INTERNAL_SNAPSHOT_GAP" for issue in issues),
        "edge_incomplete_listings": sum(issue.code == "EDGE_SNAPSHOT_MISSING" for issue in issues),
    }
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "input_file_count": metadata["file_count"],
        "rows": {name: len(frame) for name, frame in tables.items()},
        "metric_rows": {"snapshot": len(snapshots), "transition": len(transitions)},
        "key_checks": key_checks,
        "snapshot_checks": snapshot_checks,
        "numeric_conversion_error_count": sum(issue.code == "INVALID_NUMBER" for issue in issues),
        "issue_counts": {f"{severity}:{code}": int(count) for (severity, code), count in counts.items()},
        "severity_counts": issue_frame["severity"].value_counts().to_dict() if not issue_frame.empty else {},
        "status": "failed" if any(issue.severity == "error" for issue in issues) else "passed_with_warnings" if issues else "passed",
        "outputs": outputs,
    }
    (output_dir / "pipeline_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def run_pipeline(input_dir: Path, output_dir: Path) -> dict[str, Any]:
    issues: list[Issue] = []
    raw, metadata = load_raw(input_dir, issues)
    tables = {name: normalize(name, frame, issues) for name, frame in raw.items()}
    check_relationships(tables, issues)
    tables["products"] = add_snapshot_checks(tables["products"], issues)
    snapshots, transitions = build_metrics(tables["products"], issues)
    return write_outputs(output_dir, tables, snapshots, transitions, issues, metadata)
