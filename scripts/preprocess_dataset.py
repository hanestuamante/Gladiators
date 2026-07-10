#!/usr/bin/env python3
"""Preprocess Shopee CSV exports into unified, analysis-ready tables.

The script intentionally uses only the Python standard library so it can run in
the current project without installing pandas or other dependencies.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


DATASET_FILES = {
    "products": "products.csv",
    "shop_info": "shop_info.csv",
    "category_list": "category_list.csv",
    "product_categories": "product_categories.csv",
    "category_platform": "category_platform.csv",
}

NUMERIC_COLUMNS = {
    "products": {
        "ctime",
        "price",
        "price_original",
        "price_before_promo",
        "discount_percent",
        "promotion_id",
        "voucher_discount",
        "voucher_start_time",
        "voucher_end_time",
        "voucher_min_spend",
        "history_sold_value",
        "monthly_sold_value",
        "rating",
        "rating_count",
        "brand_id",
        "catid",
        "liked_count",
    },
    "shop_info": {
        "rating_star",
        "follower_count",
        "item_count",
        "response_rate",
        "response_time",
        "rating_good",
        "rating_normal",
        "rating_bad",
        "cancellation_rate",
    },
    "category_list": {
        "shop_category_id",
        "total",
        "parent_shop_category_id",
        "category_type",
    },
    "product_categories": {"item_id", "category_slug", "category_id"},
    "category_platform": {"client", "category_id", "parent_category_id"},
}

BOOLEAN_COLUMNS = {
    "products": {"is_ad", "is_sold_out", "shopee_verified"},
    "shop_info": {"is_official_shop", "vacation"},
    "category_list": {"is_parent_category", "is_sub_category"},
    "category_platform": {"has_children"},
}

ARRAY_COLUMNS = {
    "products": {
        "images",
        "seller_flag",
        "seller_flag_hash",
        "image_overlay",
        "image_overlay_hash",
        "rating_count_detail",
        "vouchers",
        "global_catids",
        "tier_variation_options",
    }
}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def parse_path(path: Path) -> dict[str, str]:
    parsed = {"path_country_code": "", "path_dataset": "", "path_shop_id": ""}
    for part in path.parts:
        if part.startswith("country_code="):
            parsed["path_country_code"] = part.split("=", 1)[1]
        elif part.startswith("dataset="):
            parsed["path_dataset"] = part.split("=", 1)[1]
        elif part.startswith("shop_id="):
            parsed["path_shop_id"] = part.split("=", 1)[1]
    return parsed


def parse_number(value: str) -> float | None:
    value = clean_text(value)
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def format_number(value: float | None) -> str:
    if value is None:
        return ""
    if value.is_integer():
        return str(int(value))
    return f"{value:.12g}"


def parse_bool(value: str) -> str:
    value = clean_text(value).lower()
    if value in {"true", "1", "yes", "y"}:
        return "true"
    if value in {"false", "0", "no", "n"}:
        return "false"
    return ""


def parse_array(value: str) -> list[Any]:
    value = clean_text(value)
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = [{k: clean_text(v) for k, v in row.items()} for row in reader]
        return list(reader.fieldnames or []), rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = list(dict.fromkeys(fieldnames))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ordered, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in ordered})


def normalize_dataset_row(dataset: str, row: dict[str, str], meta: dict[str, str], source: Path) -> dict[str, Any]:
    output: dict[str, Any] = dict(row)
    output["source_file"] = source.as_posix()
    output.update(meta)

    if meta["path_country_code"] and output.get("country_code", "") == "":
        output["country_code"] = meta["path_country_code"]
    if meta["path_shop_id"] and output.get("shop_id", "") == "":
        output["shop_id"] = meta["path_shop_id"]

    for col in NUMERIC_COLUMNS.get(dataset, set()):
        output[f"{col}_num"] = format_number(parse_number(output.get(col, "")))

    for col in BOOLEAN_COLUMNS.get(dataset, set()):
        output[f"{col}_bool"] = parse_bool(output.get(col, ""))

    for col in ARRAY_COLUMNS.get(dataset, set()):
        output[f"{col}_count"] = str(len(parse_array(output.get(col, ""))))

    if dataset == "products":
        output["product_name_clean"] = clean_text(output.get("product_name", ""))
        price = parse_number(output.get("price", ""))
        original = parse_number(output.get("price_original", ""))
        output["discount_amount_num"] = format_number(original - price if original is not None and price is not None else None)

    return output


def collect_input(input_dir: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    rows_by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    schemas: dict[str, Counter[tuple[str, ...]]] = defaultdict(Counter)
    file_rows: list[dict[str, Any]] = []
    path_mismatches: list[dict[str, str]] = []

    for path in sorted(input_dir.rglob("*.csv")):
        meta = parse_path(path)
        dataset = meta["path_dataset"]
        headers, rows = read_csv(path)
        schemas[dataset][tuple(headers)] += 1
        file_rows.append(
            {
                "file": path.as_posix(),
                "dataset": dataset,
                "country_code": meta["path_country_code"],
                "shop_id": meta["path_shop_id"],
                "rows": len(rows),
                "columns": len(headers),
            }
        )
        for row in rows:
            if row.get("country_code") and meta["path_country_code"] and row["country_code"] != meta["path_country_code"]:
                path_mismatches.append({"file": path.as_posix(), "field": "country_code", "row_value": row["country_code"], "path_value": meta["path_country_code"]})
            if row.get("shop_id") and meta["path_shop_id"] and row["shop_id"] != meta["path_shop_id"]:
                path_mismatches.append({"file": path.as_posix(), "field": "shop_id", "row_value": row["shop_id"], "path_value": meta["path_shop_id"]})
            rows_by_dataset[dataset].append(normalize_dataset_row(dataset, row, meta, path))

    report = {
        "input_dir": input_dir.as_posix(),
        "file_count": len(file_rows),
        "files": file_rows,
        "schemas": {dataset: [{"columns": list(schema), "file_count": count} for schema, count in counter.items()] for dataset, counter in schemas.items()},
        "path_mismatches": path_mismatches,
    }
    return rows_by_dataset, report


def unique_join(values: Iterable[str], sep: str = "|") -> str:
    seen = []
    for value in values:
        value = clean_text(value)
        if value and value not in seen:
            seen.append(value)
    return sep.join(seen)


def build_product_ready(rows_by_dataset: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    shops = {(r.get("country_code", ""), r.get("shop_id", "")): r for r in rows_by_dataset.get("shop_info", [])}
    category_names = {
        (r.get("country_code", ""), r.get("shop_id", ""), r.get("shop_category_id", ""), r.get("date", "")): r.get("display_name", "")
        for r in rows_by_dataset.get("category_list", [])
    }
    product_categories: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows_by_dataset.get("product_categories", []):
        key = (row.get("country_code", ""), row.get("shop_id", ""), row.get("item_id", ""), row.get("date", ""))
        product_categories[key].append(row)

    ready = []
    for row in rows_by_dataset.get("products", []):
        output = dict(row)
        country = row.get("country_code", "")
        shop_id = row.get("shop_id", "")
        item_id = row.get("item_id", "")
        date = row.get("date", "")

        shop = shops.get((country, shop_id), {})
        for col in [
            "rating_star",
            "follower_count",
            "item_count",
            "is_official_shop",
            "response_rate",
            "response_time",
            "rating_good",
            "rating_normal",
            "rating_bad",
            "cancellation_rate",
            "created_at",
            "vacation",
        ]:
            output[f"shop_{col}"] = shop.get(col, "")

        cats = product_categories.get((country, shop_id, item_id, date), [])
        cat_ids = [cat.get("category_id", "") for cat in cats]
        output["shop_category_ids"] = unique_join(cat_ids)
        output["shop_category_names"] = unique_join(category_names.get((country, shop_id, cat_id, date), "") for cat_id in cat_ids)
        output["shop_category_count"] = str(len(set(filter(None, cat_ids))))
        ready.append(output)
    return ready


def deduplicate_exact_rows(rows_by_dataset: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int], dict[str, int]]:
    deduped: dict[str, list[dict[str, Any]]] = {}
    raw_counts: dict[str, int] = {}
    removed_counts: dict[str, int] = {}

    for dataset, rows in rows_by_dataset.items():
        raw_counts[dataset] = len(rows)
        seen: set[str] = set()
        output: list[dict[str, Any]] = []
        for row in rows:
            key = json.dumps(row, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            output.append(row)
        deduped[dataset] = output
        removed_counts[dataset] = len(rows) - len(output)

    return deduped, raw_counts, removed_counts


def date_range(rows: list[dict[str, Any]], field: str = "date") -> dict[str, str]:
    dates = sorted({r.get(field, "") for r in rows if r.get(field, "")})
    return {"min": dates[0], "max": dates[-1], "unique_count": len(dates)} if dates else {"min": "", "max": "", "unique_count": 0}


def duplicate_count(rows: list[dict[str, Any]], key_fields: list[str]) -> int:
    keys = [tuple(r.get(field, "") for field in key_fields) for r in rows]
    return sum(count - 1 for count in Counter(keys).values() if count > 1)


def missing_counts(rows: list[dict[str, Any]], fields: list[str]) -> dict[str, int]:
    return {field: sum(1 for row in rows if clean_text(row.get(field, "")) == "") for field in fields}


def build_report(
    rows_by_dataset: dict[str, list[dict[str, Any]]],
    base_report: dict[str, Any],
    raw_counts: dict[str, int],
    removed_counts: dict[str, int],
) -> dict[str, Any]:
    report = dict(base_report)
    dataset_stats: dict[str, Any] = {}

    for dataset, rows in sorted(rows_by_dataset.items()):
        fields = list(dict.fromkeys(field for row in rows for field in row.keys()))
        country_counts = Counter(row.get("country_code", row.get("path_country_code", "")) for row in rows)
        shop_counts = Counter(row.get("shop_id", row.get("path_shop_id", "")) for row in rows if row.get("shop_id", row.get("path_shop_id", "")))
        key_fields = {
            "products": ["country_code", "shop_id", "item_id", "date"],
            "shop_info": ["country_code", "shop_id"],
            "category_list": ["country_code", "shop_id", "shop_category_id", "date"],
            "product_categories": ["country_code", "shop_id", "item_id", "category_id", "date"],
            "category_platform": ["path_country_code", "category_id"],
        }.get(dataset, [])
        dataset_stats[dataset] = {
            "rows": len(rows),
            "columns": len(fields),
            "countries": dict(sorted(country_counts.items())),
            "shops": len(shop_counts),
            "date_range": date_range(rows),
            "duplicate_rows_by_key": duplicate_count(rows, key_fields) if key_fields else 0,
            "missing_counts_core": missing_counts(rows, [f for f in key_fields + ["date", "product_name", "price", "rating"] if f in fields]),
        }

    products = rows_by_dataset.get("products", [])
    report["dataset_stats"] = dataset_stats
    report["raw_rows_by_dataset"] = dict(sorted(raw_counts.items()))
    report["exact_duplicate_rows_removed"] = dict(sorted(removed_counts.items()))
    report["countries"] = sorted({row.get("country_code", "") for rows in rows_by_dataset.values() for row in rows if row.get("country_code", "")})
    report["shop_ids"] = sorted({row.get("shop_id", "") for rows in rows_by_dataset.values() for row in rows if row.get("shop_id", "")})
    report["generated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    if products:
        report["product_checks"] = {
            "unique_platforms": sorted({row.get("platform", "") for row in products if row.get("platform", "")}),
            "unique_top_level_catid": sorted({row.get("catid", "") for row in products if row.get("catid", "")}),
            "sold_out_values": dict(Counter(row.get("is_sold_out", "") for row in products)),
            "ad_values": dict(Counter(row.get("is_ad", "") for row in products)),
            "verified_values": dict(Counter(row.get("shopee_verified", "") for row in products)),
            "price_999999999_count": sum(1 for row in products if row.get("price", "") == "999999999"),
        }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess raw CSV files in Dataset/DataRaw.")
    parser.add_argument("--input", default="Dataset/DataRaw", help="Input raw-data root directory")
    parser.add_argument("--output", default="Dataset/DataProcessed", help="Output processed-data directory")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    rows_by_dataset, base_report = collect_input(input_dir)
    rows_by_dataset, raw_counts, removed_counts = deduplicate_exact_rows(rows_by_dataset)
    product_ready = build_product_ready(rows_by_dataset)

    for dataset, filename in DATASET_FILES.items():
        rows = rows_by_dataset.get(dataset, [])
        if rows:
            fields = list(dict.fromkeys(field for row in rows for field in row.keys()))
            write_csv(output_dir / filename.replace(".csv", "_clean.csv"), rows, fields)

    if product_ready:
        fields = list(dict.fromkeys(field for row in product_ready for field in row.keys()))
        write_csv(output_dir / "product_dataset_ready.csv", product_ready, fields)

    report = build_report(rows_by_dataset, base_report, raw_counts, removed_counts)
    report["outputs"] = sorted(path.as_posix() for path in output_dir.glob("*.csv"))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "data_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(report['outputs'])} CSV files and data_quality_report.json to {output_dir}")


if __name__ == "__main__":
    main()
