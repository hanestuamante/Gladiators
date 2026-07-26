"""Independent DR2607 data oracle.

This module deliberately imports no ``gladiators`` code.  It reads governed CSV
artifacts directly and emits denotations for the historical premises that were
verified as stale on 26/07.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def build(data_dir: str | Path = "data/processed") -> list[dict]:
    root = Path(data_dir)
    products = pd.read_csv(root / "products_clean.csv", dtype={"item_id": str, "shop_id": str})
    snapshots = pd.read_csv(
        root / "product_snapshot_metrics.csv", dtype={"item_id": str, "shop_id": str},
    )

    records: list[dict] = []

    promotion = products.loc[
        products.promotion_id.astype(str).str.replace(r"\.0$", "", regex=True)
        == "473502013010049"
    ]
    records.append({
        "case_id": "dr2607_tc26",
        "metric": "promotion_observation_profile",
        "value": {
            "raw_rows": int(len(promotion)),
            "distinct_listings": int(promotion.product_listing_key.nunique()),
            "dates": sorted(promotion.date.astype(str).unique().tolist()),
            "shops": sorted(promotion.shop_id.astype(str).unique().tolist()),
        },
        "unit": "profile",
        "grain": "listing_snapshot",
        "scope": "promotion_id=473502013010049",
        "method_note": "Direct CSV filter; no campaign identity inference.",
    })

    promo_zero = products.loc[
        products.promotion_id.fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
        == "0"
    ]
    vn_zero = promo_zero.loc[promo_zero.country_code == "vn"]
    latest = str(vn_zero.date.astype(str).max()) if not vn_zero.empty else None
    records.append({
        "case_id": "dr2607_tc30",
        "metric": "promotion_zero_profile",
        "value": {
            "all_raw_rows": int(len(promo_zero)),
            "vn_raw_rows": int(len(vn_zero)),
            "vn_distinct_listings": int(vn_zero.product_listing_key.nunique()),
            "vn_latest_rows": int((vn_zero.date.astype(str) == latest).sum()) if latest else 0,
        },
        "unit": "profile",
        "grain": "listing_snapshot",
        "scope": "promotion_id=0",
        "method_note": "Separates raw rows, distinct listings and latest snapshot.",
    })

    item19 = snapshots.loc[snapshots.item_id == "56061511146"].sort_values("date")
    records.append({
        "case_id": "dr2607_tc19",
        "metric": "price_sentinel_flag",
        "value": item19[["date", "price_num", "price_sentinel_flag"]].to_dict("records"),
        "unit": "profile",
        "grain": "listing_snapshot",
        "scope": "item_id=56061511146",
        "method_note": "Flag is governed artifact output; product-name semantics require human policy.",
    })

    gap_rows = products.loc[products.snapshot_gap_flag.astype(bool)].copy()
    records.append({
        "case_id": "dr2607_tc34",
        "metric": "verified_gap_fixture_candidates",
        "value": (
            gap_rows[["product_listing_key", "item_id", "date"]]
            .drop_duplicates()
            .head(10)
            .to_dict("records")
        ),
        "unit": "fixtures",
        "grain": "listing_snapshot",
        "scope": "snapshot_gap_flag=True",
        "method_note": "Use one of these rows instead of stale item 24710759163.",
    })

    voucher = snapshots.groupby("country_code", observed=True)["has_structured_voucher"].sum()
    records.append({
        "case_id": "dr2607_tc23",
        "metric": "structured_voucher_rows",
        "value": {str(country): int(value) for country, value in voucher.items()},
        "unit": "rows",
        "grain": "listing_snapshot",
        "scope": "all snapshots",
        "method_note": "Counts governed has_structured_voucher, not UI voucher labels.",
    })

    item39 = snapshots.loc[snapshots.item_id == "26663401389"].sort_values("date")
    records.append({
        "case_id": "dr2607_tc39",
        "metric": "item_snapshot_series",
        "value": item39[
            ["date", "monthly_sold_value_num", "history_sold_value_num", "rating_num"]
        ].to_dict("records"),
        "unit": "profile",
        "grain": "listing_snapshot",
        "scope": "item_id=26663401389",
        "method_note": "monthly_sold is a recent-window snapshot proxy and must not be summed across snapshots.",
    })
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/processed")
    parser.add_argument("--output", default="eval/independent/dr2607_expected.json")
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build(args.data_dir), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
