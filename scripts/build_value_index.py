#!/usr/bin/env python3
"""Chỉ mục giá trị cho ba chiều — Spec2308 §WP-A4.3.

Chỉ **ba** dimension, vì chỉ chúng có số giá trị đủ nhỏ và ổn định. Khoá theo
``country`` vì cùng một tên có thể chỉ tồn tại ở một thị trường.

    PYTHONPATH=src python scripts/build_value_index.py

A4-R3: file sinh ra **không commit** vào repo — nằm trong ``artifacts/`` đã được
gitignore. CI dựng lại trước khi chạy eval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"

# Ba chiều, và cột vật lý của chúng. Giữ ở đây thay vì suy từ catalog: script
# này cố ý KHÔNG import gladiators, để chỉ mục không thừa hưởng giả định nào của
# hệ bị kiểm.
SOURCES: tuple[tuple[str, str, str], ...] = (
    ("dim.platform_category_name", "category_platform_clean.csv", "display_category_name"),
    ("dim.brand", "products_clean.csv", "brand"),
    ("dim.shop_name", "shop_info_clean.csv", "shop_name"),
)


def build() -> dict:
    products = pd.read_csv(DATA / "products_clean.csv")
    dataset_version = hashlib.sha256(
        ",".join(sorted(products.product_snapshot_key.astype(str))).encode("utf-8"),
    ).hexdigest()[:16]

    values: dict[str, dict[str, list[str]]] = {}
    for ref, artifact, column in SOURCES:
        frame = pd.read_csv(DATA / artifact)
        if column not in frame.columns or "country_code" not in frame.columns:
            continue
        per_country: dict[str, list[str]] = {}
        for country, group in frame.groupby("country_code"):
            names = sorted({
                str(value).strip() for value in group[column].dropna()
                if str(value).strip()
            })
            per_country[str(country)] = names
        values[ref] = per_country
    return {"dataset_version": dataset_version, "values": values}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/value_index.json")
    args = parser.parse_args()

    index = build()
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "dataset_version": index["dataset_version"],
        "refs": {ref: {c: len(v) for c, v in per.items()}
                 for ref, per in index["values"].items()},
        "output": str(out.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
