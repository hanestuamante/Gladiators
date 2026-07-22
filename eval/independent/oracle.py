"""Independent denotation oracle for certified analytical cases.

This module intentionally imports no ``gladiators`` code. It reads frozen artifact
bytes directly and recomputes gold answers with plain pandas operations.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


def _canonical_csv_bytes(path: Path) -> bytes:
    """Hash CSV content independent of checkout CRLF/LF conversion."""
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _sha256(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(_canonical_csv_bytes(path))
    return digest.hexdigest()[:16]


def build_oracle(data_dir: str | Path = "data/processed") -> dict:
    root = Path(data_dir)
    product_path = root / "products_clean.csv"
    snapshot_path = root / "product_snapshot_metrics.csv"
    shop_path = root / "shop_info_clean.csv"
    products = pd.read_csv(product_path, low_memory=False)
    snapshots = pd.read_csv(snapshot_path, low_memory=False)
    shops = pd.read_csv(shop_path, low_memory=False)
    latest_date = "2026-07-03"
    results: dict[str, dict] = {}
    for country in ("vn", "id"):
        country_snapshots = snapshots.loc[snapshots.country_code == country].copy()
        revenue = country_snapshots.groupby(country_snapshots.date.astype(str))["estimated_recent_revenue"].sum()
        revenue_date = str(revenue.idxmax())
        latest = products.loc[
            (products.country_code == country) & (products.date.astype(str) == latest_date)
        ].copy()
        price_rows = latest.loc[latest.price_num.ge(0) & latest.price_num.lt(999999999)]
        price_row = price_rows.loc[price_rows.price_num.idxmax()]
        sold_rows = latest.loc[latest.monthly_sold_value_num.ge(0)]
        sold_row = sold_rows.loc[sold_rows.monthly_sold_value_num.idxmax()]
        counts = latest.groupby(latest.shop_id.astype(str)).product_listing_key.nunique()
        top_shop_id = str(counts.idxmax())
        shop_row = shops.loc[
            (shops.country_code == country) & (shops.shop_id.astype(str) == top_shop_id)
        ].iloc[0]
        results[country] = {
            "highest_revenue_day": {
                "date": revenue_date,
                "estimated_recent_revenue": float(revenue.loc[revenue_date]),
            },
            "listing_count": {"listing_count": int(latest.product_listing_key.nunique())},
            "highest_price_listing": {
                "product_name": str(price_row.product_name), "price": float(price_row.price_num),
            },
            "highest_monthly_sold_listing": {
                "product_name": str(sold_row.product_name),
                "monthly_sold": float(sold_row.monthly_sold_value_num),
            },
            "top_shop_by_listing_count": {
                "shop_id": top_shop_id, "shop_name": str(shop_row.shop_name),
                "listing_count": int(counts.loc[top_shop_id]),
            },
        }
    return {
        "schema_version": "1.0", "latest_date": latest_date,
        "artifact_hash": _sha256((product_path, snapshot_path, shop_path)),
        "results": results,
    }
