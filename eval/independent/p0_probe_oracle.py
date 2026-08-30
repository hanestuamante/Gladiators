"""Independent P0 regression-lock oracle.

Like :mod:`dr2607_oracle`, this module deliberately imports no ``gladiators``
code.  It reads the governed CSV artifacts directly so that every number pinned
by ``tests/test_p0_regression_lock.py`` has a denotation a reviewer can check
against ``source_file`` / ``source_row`` without trusting the runtime.

The records cover the six P0 probes: three genuine ALLOW-sai contracts that are
red today (TC34 date-window narrowing, multi-country scope drop, plural ranking
collapsed to top-1) and three baselines that are safe today and are locked so a
later change cannot silently move them.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

LATEST_SNAPSHOT = "2026-07-03"
WINDOW_START = "2026-07-01"

# TC34's item.  DR TASK 1407 claimed this listing was missing the 02/07
# snapshot; it is not.  See ``p0_tc34_window.method_note``.
TC34_ITEM = "24710759163"

# The only true snapshot-gap listing whose sold values move across the gap,
# which is what makes a wrong answer distinguishable from a right one.
GAP_ITEM = "42955556831"


def _rows(frame: pd.DataFrame, columns: list[str]) -> list[dict]:
    return frame[columns].to_dict("records")


def build(data_dir: str | Path | None = None) -> list[dict]:
    # Oracle NÀY mô tả bộ đóng băng 3 ngày — cùng bản mà denotation trong
    # `p0_probe_expected.json` được tính trên đó. Để nó chạy theo "bản nào đang
    # phục vụ" là để một phép so sánh hai vế đứng trên hai bản dữ liệu khác nhau,
    # và kết quả không nói được gì về hệ.
    #
    # Đọc THẲNG biến môi trường, KHÔNG import `gladiators.data.repository`: cả
    # giá trị của file này nằm ở chỗ nó không chạm vào hệ đang bị kiểm — một
    # oracle mượn hằng số của hệ thì nó không còn là bên thứ hai nữa. Phép kiểm
    # ở `test_p0_regression_lock` chặn đúng chuyện đó bằng cách quét cây AST.
    root = Path(data_dir if data_dir is not None
                else os.environ.get("GLADIATORS_DATA_DIR") or "data/processed")
    dtype = {"item_id": str, "shop_id": str}
    products = pd.read_csv(root / "products_clean.csv", dtype=dtype)
    snapshots = pd.read_csv(root / "product_snapshot_metrics.csv", dtype=dtype)
    transitions = pd.read_csv(root / "product_transition_metrics.csv", dtype=dtype)

    records: list[dict] = []

    # ---------------------------------------------------------------- tc34 --
    # RED contract: the question asks 01/07 -> 03/07 but the runtime answers the
    # 02/07 -> 03/07 leg only.  Because monthly_sold moves 193 -> 306 -> 204 the
    # answered value is not merely narrower, it has the opposite sign to the
    # window that was asked for.
    tc34_transitions = transitions.loc[transitions.item_id == TC34_ITEM].sort_values("date")
    tc34_snapshots = snapshots.loc[snapshots.item_id == TC34_ITEM].sort_values("date")
    monthly_by_date = {
        str(row.date): float(row.monthly_sold_value_num)
        for row in tc34_snapshots.itertuples()
    }
    window_delta = monthly_by_date[LATEST_SNAPSHOT] - monthly_by_date[WINDOW_START]
    last_leg = tc34_transitions.iloc[-1]
    records.append({
        "case_id": "p0_tc34_window",
        "metric": "asked_window_vs_answered_leg",
        "value": {
            "item_id": TC34_ITEM,
            "asked_window": [WINDOW_START, LATEST_SNAPSHOT],
            "monthly_sold_by_date": monthly_by_date,
            "window_delta": window_delta,
            "answered_window": [str(last_leg.previous_date), str(last_leg.date)],
            "answered_delta": float(last_leg.monthly_sold_delta),
            "transitions": _rows(tc34_transitions, [
                "previous_date", "date", "days_since_previous",
                "transition_metric_eligible", "monthly_sold_delta",
                "source_file", "source_row",
            ]),
        },
        "unit": "items",
        "grain": "transition",
        "scope": f"item_id={TC34_ITEM}, {WINDOW_START}..{LATEST_SNAPSHOT}",
        "method_note": (
            "Corrects dr2607_tc34: item 24710759163 has all three snapshot dates and two "
            "eligible transitions, so the DR premise of a missing 02/07 snapshot is false. "
            "The real defect is date-window narrowing - the asked 2-day window has "
            f"delta {window_delta:+g} but the runtime reports the last 1-day leg "
            f"({float(last_leg.monthly_sold_delta):+g}), inverting the sign."
        ),
    })

    # ---------------------------------------------------------------- tc23 --
    # ORACLE LOCK.  dr2607_tc23 pins 1580 = sum of has_structured_voucher rows
    # over all three snapshots.  The runtime answers 577, the deduped listing
    # count at the latest snapshot.  Both are correct under their own scope;
    # this record exists so a reviewer comparing them does not read the runtime
    # as wrong.
    latest_snapshots = snapshots.loc[snapshots.date.astype(str) == LATEST_SNAPSHOT]
    voucher_latest = (
        latest_snapshots.loc[latest_snapshots.has_structured_voucher.astype(bool)]
        .groupby("country_code", observed=True)["product_listing_key"]
        .nunique()
    )
    voucher_all = snapshots.groupby("country_code", observed=True)["has_structured_voucher"].sum()
    records.append({
        "case_id": "p0_tc23_voucher_latest",
        "metric": "structured_voucher_listings_latest",
        "value": {
            "snapshot_date": LATEST_SNAPSHOT,
            "counts": {
                str(country): int(voucher_latest.get(country, 0))
                for country in sorted(snapshots.country_code.astype(str).unique())
            },
        },
        "unit": "listings",
        "grain": "listing",
        "scope": f"date={LATEST_SNAPSHOT}, deduped by product_listing_key",
        "method_note": (
            "Cross-reference dr2607_tc23: that record's "
            f"{ {str(k): int(v) for k, v in voucher_all.items()} } counts has_structured_voucher "
            "rows across all three snapshots. This record pins the latest-snapshot deduped "
            "listing denotation the runtime actually answers with. Neither supersedes the "
            "other; they answer different scopes."
        ),
    })

    # ------------------------------------------------------------ scope drop --
    # RED contract: "Có bao nhiêu listing ở Việt Nam và Indonesia?" resolves both
    # countries into the digest but the evidence covers vn only.
    listing_counts = (
        latest_snapshots.groupby("country_code", observed=True)["product_listing_key"].nunique()
    )
    records.append({
        "case_id": "p0_scope_listing_count",
        "metric": "listing_count_by_country_latest",
        "value": {
            "snapshot_date": LATEST_SNAPSHOT,
            "counts": {str(k): int(v) for k, v in listing_counts.items()},
            "total": int(listing_counts.sum()),
        },
        "unit": "listings",
        "grain": "listing",
        "scope": f"date={LATEST_SNAPSHOT}, deduped by product_listing_key",
        "method_note": (
            "Cross-reference eval/independent/golden_v2.json results.{vn,id}.listing_count. "
            "A multi-country question must cover both keys; answering one and reporting "
            "'Phạm vi: Thị trường VN' drops half the asked scope."
        ),
    })

    # -------------------------------------------------------------- plurality --
    # RED contract: a plural question ("Những sản phẩm nào ...") is answered with
    # a single listing.  This record proves more than one candidate exists.
    vn_latest = latest_snapshots.loc[latest_snapshots.country_code == "vn"]
    top_prices = (
        vn_latest.sort_values("price_num", ascending=False)
        .drop_duplicates("product_listing_key")
        .head(5)
    )
    records.append({
        "case_id": "p0_plurality_top_prices",
        "metric": "top_price_listings_vn_latest",
        "value": {
            "snapshot_date": LATEST_SNAPSHOT,
            "candidates": _rows(top_prices, ["item_id", "product_name", "price_num"]),
        },
        "unit": "listings",
        "grain": "listing",
        "scope": f"country=vn, date={LATEST_SNAPSHOT}, top 5 by price_num",
        "method_note": (
            "At least five distinct listings exist, so collapsing a plural question to "
            "top_k=1 is a shape decision the runtime makes, not a data limitation."
        ),
    })

    # -------------------------------------------------------------- gap item --
    # GUARD RAIL.  The runtime abstains today.  The trap for a later 'fix' is
    # that monthly_sold is flat across the gap, so computing the delta anyway
    # yields a confident 0 that reads as 'no decline'.
    gap_transition = transitions.loc[transitions.item_id == GAP_ITEM]
    gap_snapshots = snapshots.loc[snapshots.item_id == GAP_ITEM].sort_values("date")
    records.append({
        "case_id": "p0_gap_item_42955556831",
        "metric": "snapshot_gap_transition",
        "value": {
            "item_id": GAP_ITEM,
            "transitions": _rows(gap_transition, [
                "previous_date", "date", "days_since_previous",
                "transition_metric_eligible", "stock_status",
                "source_file", "source_row",
            ]),
            "snapshots": _rows(gap_snapshots, [
                "date", "monthly_sold_value_num", "history_sold_value_num",
                "snapshot_gap_flag", "source_file", "source_row",
            ]),
        },
        "unit": "profile",
        "grain": "transition",
        "scope": f"item_id={GAP_ITEM}",
        "method_note": (
            "transition_metric_eligible is False because days_since_previous=2 (02/07 is "
            "absent). monthly_sold is flat 4000 -> 4000 across the gap while history_sold "
            "moves 4000 -> 5000, so a naive 'compute it anyway' change returns delta 0, a "
            "plausible-looking wrong answer. The guard rail must forbid emitting a "
            "monthly_sold_delta at all, not merely forbid a non-zero one."
        ),
    })

    # ------------------------------------------------------------ grouping --
    # GUARD RAIL (added P1).  "bao nhiêu listing của shop official / thương hiệu
    # NESCAFÉ / theo từng shop tại VN" all used to compile to the bare
    # listing_count template and return the same unfiltered 668.
    shops = pd.read_csv(root / "shop_info_clean.csv", dtype=dtype)
    official = set(
        shops.loc[
            (shops.country_code == "vn") & shops.is_official_shop_bool.astype(bool)
        ].shop_id.astype(str)
    )
    vn_latest_all = latest_snapshots.loc[latest_snapshots.country_code == "vn"]
    official_listings = vn_latest_all.loc[
        vn_latest_all.shop_id.astype(str).isin(official)
    ]
    records.append({
        "case_id": "p0_grouping_official_shop",
        "metric": "listing_count_by_shop_flag_latest",
        "value": {
            "snapshot_date": LATEST_SNAPSHOT,
            "vn_all_listings": int(vn_latest_all.product_listing_key.nunique()),
            "vn_official_shop_listings": int(official_listings.product_listing_key.nunique()),
            "vn_official_shops": len(official),
        },
        "unit": "listings",
        "grain": "listing",
        "scope": f"country=vn, date={LATEST_SNAPSHOT}",
        "method_note": (
            "The dropped-dimension answer returned the unfiltered 668 for a question "
            "whose true answer is 465 -- a 203-listing overcount, not a rounding "
            "difference. Three differently-scoped questions all returned the same 668, "
            "which is what makes this a silent wrong answer rather than an imprecise one."
        ),
    })

    # ----------------------------------------------------------- date point --
    # GUARD RAIL (added P1).  Analytical templates hardcode the latest snapshot,
    # so a question naming 01/07 was answered with 03/07 data and the evidence
    # was labelled observed_date=2026-07-03.
    by_date = {}
    for date in sorted(snapshots.date.astype(str).unique()):
        day = snapshots.loc[
            (snapshots.date.astype(str) == date) & (snapshots.country_code == "vn")
        ]
        by_date[date] = {
            "listing_count": int(day.product_listing_key.nunique()),
            "max_price": float(day.price_num.max()),
        }
    records.append({
        "case_id": "p0_date_point_vn",
        "metric": "listing_count_and_max_price_by_date",
        "value": {"country": "vn", "by_date": by_date},
        "unit": "profile",
        "grain": "listing",
        "scope": "country=vn, each snapshot date",
        "method_note": (
            "Every snapshot has a different answer: 581/670/668 listings and a max price "
            "of 2,959,200 on 01/07 versus 3,033,180 later. Substituting the latest "
            "snapshot for a named date is therefore a wrong answer (87 listings off), "
            "not a defensible default."
        ),
    })

    # ---------------------------------------------------------- rank order --
    # GUARD RAIL (added P1).  Every certified ranking template is a "highest"
    # template, and infer_deterministic_template never read ranking.direction,
    # so an ascending question was answered with the descending result.
    vn_latest_prices = vn_latest.price_num.dropna()
    records.append({
        "case_id": "p0_rank_direction_vn",
        "metric": "price_extremes_vn_latest",
        "value": {
            "snapshot_date": LATEST_SNAPSHOT,
            "min_price": float(vn_latest_prices.min()),
            "max_price": float(vn_latest_prices.max()),
            "min_price_product": str(
                vn_latest.loc[vn_latest_prices.idxmin()].product_name,
            ),
        },
        "unit": "local_currency",
        "grain": "listing",
        "scope": f"country=vn, date={LATEST_SNAPSHOT}",
        "method_note": (
            "The ascending answer differs from the descending one by roughly 3000x "
            "(1,000 versus 3,033,180), and the answer sentence still read 'Listing có "
            "giá cao nhất là', so the output contradicted the question it answered."
        ),
    })

    # ------------------------------------------------------------------ tc19 --
    # GUARD RAIL only.  The sentinel policy for this listing is an unapproved
    # DR1 decision, so no expected answer may be pinned (see ultimate solution
    # §1.5: runtime reads only approved decisions).
    item19 = snapshots.loc[snapshots.item_id == "56061511146"].sort_values("date")
    records.append({
        "case_id": "p0_tc19_sentinel_ref",
        "metric": "price_sentinel_policy_pending",
        "value": {
            "see": "dr2607_tc19",
            "dr1_status": "pending",
            "observed": _rows(item19, ["date", "price_num", "price_sentinel_flag"]),
        },
        "unit": "profile",
        "grain": "listing_snapshot",
        "scope": "item_id=56061511146",
        "method_note": (
            "price_sentinel_flag is False for all three snapshots, but the listing is named "
            "'Quà tặng không bán' (not-for-sale gift). Whether its 410000 price may anchor a "
            "±20% competitor comparison is a data-owner decision that is still pending, so "
            "this record pins no expected answer - only that allow is forbidden meanwhile."
        ),
    })

    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--output", default="eval/independent/p0_probe_expected.json")
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build(args.data_dir), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
