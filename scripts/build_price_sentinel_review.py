#!/usr/bin/env python3
"""Data-quality review job: noise and outlier candidates — ultimate solution §4.8.

Surfaces two families of values that must not enter an aggregate or a ranking
without a decision.  Both are expressed as *rules* over the distribution, never
as a list of known rows, so they keep working when the data changes and so no
identifier is ever baked into the repository.

**Placeholder-looking prices.**  Marketplaces reuse repeated-nine magnitudes as a
"not really for sale" placeholder.  The pipeline currently recognises a single
exact constant, so any other repeated-nine magnitude reaches a ranking untouched.
The rule here is structural: an all-nines mantissa at or above a digit threshold,
or a value beyond the per-cohort ``p99.9``.

**Capped columns.**  A marketplace often shows a bucketed display value rather
than a measurement.  The tell is distributional -- a large share of a column
sitting exactly at its own maximum.  A median or cross-market comparison over
such a column compares a truncated series against an untruncated one, and
several certified metrics aggregate exactly these columns.

The job only *proposes*.  Which candidates are noise is a data-owner call
(§1.5: the runtime reads only ``approved`` decisions), so every row is written
with ``dr1_status=pending`` and nothing here changes runtime behaviour.  Output
lands under ``artifacts/`` and is not committed: the intended end state is an
approved *rule* in the data contract that the pipeline applies, not a checked-in
list of row identifiers, which would be an answer key rather than a filter.

    python scripts/build_price_sentinel_review.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

ALL_NINES = re.compile(r"9{7,}")
OUTLIER_QUANTILE = 0.999
# A value holding this share of a column's non-null rows, while also being the
# maximum, reads as a display cap rather than a measurement.
CAP_SHARE = 0.20


def _is_all_nines(value) -> bool:
    if value is None or pd.isna(value):
        return False
    return bool(ALL_NINES.fullmatch(str(int(value))))


def price_candidates(snapshots: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for (country, date), cohort in snapshots.groupby(
        ["country_code", snapshots.date.astype(str)], observed=True,
    ):
        prices = cohort.price_num.dropna()
        if prices.empty:
            continue
        threshold = float(prices.quantile(OUTLIER_QUANTILE))
        for row in cohort.itertuples():
            value = row.price_num
            if value is None or pd.isna(value):
                continue
            nines = _is_all_nines(value)
            above = float(value) > threshold
            if not (nines or above):
                continue
            rows.append({
                "candidate_id": f"{row.country_code}:{row.item_id}:{row.date}",
                "country": country,
                "snapshot_date": str(date),
                "item_id": str(row.item_id),
                "product_name": str(row.product_name)[:120],
                "price_num": float(value),
                "reason": "all_nines_ge_7_digits" if nines else "above_p999",
                "cohort": f"country={country},date={date}",
                "cohort_rows": int(len(prices)),
                "cohort_p999": round(threshold, 2),
                "cohort_median": round(float(prices.median()), 2),
                "ratio_to_median": round(float(value) / max(float(prices.median()), 1), 1),
                "pipeline_flagged": bool(row.price_sentinel_flag),
                # §1.5: the runtime may act only on approved decisions.
                "dr1_status": "pending",
                "dr1_decision": "",
                "dr1_reviewer": "",
                "dr1_approved_at": "",
            })
    rows.sort(key=lambda item: (-item["price_num"], item["candidate_id"]))
    return rows


def capped_variables(snapshots: pd.DataFrame, columns: tuple[str, ...]) -> list[dict]:
    rows: list[dict] = []
    for column in columns:
        if column not in snapshots:
            continue
        for country, cohort in snapshots.groupby("country_code", observed=True):
            series = cohort[column].dropna()
            if series.empty:
                continue
            top = float(series.max())
            share = float((series == top).mean())
            if share < CAP_SHARE:
                continue
            rows.append({
                "column": column,
                "country": country,
                "rows": int(len(series)),
                "max_value": top,
                "share_at_max": round(share, 4),
                "distinct_values": int(series.nunique()),
                "median": round(float(series.median()), 2),
                "reason": "value_pile_up_at_maximum_looks_like_display_cap",
                "impact": (
                    "median/mean and any cross-country comparison over this column "
                    "compares a truncated series against an untruncated one"
                ),
                "dr1_status": "pending",
                "dr1_decision": "",
                "dr1_reviewer": "",
                "dr1_approved_at": "",
            })
    return rows


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/processed")
    parser.add_argument("--output-dir", default="artifacts/data_review")
    args = parser.parse_args()

    root = ROOT / args.data_dir
    snapshots = pd.read_csv(root / "product_snapshot_metrics.csv", dtype={"item_id": str, "shop_id": str})

    prices = price_candidates(snapshots)
    capped = capped_variables(
        snapshots, ("monthly_sold_value_num", "history_sold_value_num", "rating_count_num"),
    )

    out = ROOT / args.output_dir
    _write_csv(out / "price_sentinel_review.csv", prices)
    _write_csv(out / "capped_variable_review.csv", capped)

    unflagged_nines = [
        row for row in prices
        if row["reason"] == "all_nines_ge_7_digits" and not row["pipeline_flagged"]
    ]
    manifest = {
        "schema_version": "data-review.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "spec_ref": "docs/ultimate solution.md §4.8",
        "data_contract_hash": hashlib.sha256(
            (root / "product_snapshot_metrics.csv").read_bytes(),
        ).hexdigest()[:32],
        "price_candidates": len(prices),
        "price_candidates_all_nines": sum(
            row["reason"] == "all_nines_ge_7_digits" for row in prices
        ),
        "price_candidates_all_nines_unflagged": len(unflagged_nines),
        "capped_variable_candidates": len(capped),
        "pending_decisions": len(prices) + len(capped),
        "note": (
            "Proposal only. The runtime still uses its existing rule until a data "
            "owner sets dr1_status=approved; nothing here changes behaviour."
        ),
    }
    (out / "data_review_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    # Counts only. Row identifiers stay in the gitignored CSV for the data owner
    # to review; echoing them here would put an answer key into logs and
    # transcripts, which is the opposite of shipping a filter rule.
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"  candidates written to {(out / 'price_sentinel_review.csv').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
