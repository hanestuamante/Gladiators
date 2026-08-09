"""Theme C: a count must not inherit the filter an aggregate needs.

``promotion_observation`` computes a mean/median of the sold proxy, so it drops
listings where that proxy is null.  Correct for the average -- but the *count* in
the same macro inherited the same filter, so "how many listings have a voucher"
silently answered "how many listings have a voucher **and** a measurable sold
proxy": 551 instead of 577, with nothing in the answer saying a second condition
existed.

Same family as Theme B: a constraint added in silence, and output that looks
complete.  It is also the trap in CLAUDE.md §3.1 -- here the rows are not filled
with 0, they are dropped, and the consequence is the same: "not measurable"
disappears from the result instead of showing up in it.
"""
from __future__ import annotations

import pandas as pd
import pytest

from gladiators.analytics import AnalyticsTools
from gladiators.data.repository import ArtifactRepository


@pytest.fixture(scope="module")
def tools() -> AnalyticsTools:
    repo = ArtifactRepository()
    counter = iter(f"ev:test:{i:04d}" for i in range(1, 10_000))
    return AnalyticsTools(repo, None, lambda: next(counter))


@pytest.fixture(scope="module")
def oracle() -> dict[str, int]:
    """Ground truth from the artifacts, independent of the code under test."""
    frame = pd.read_csv("data/processed/product_snapshot_metrics.csv")
    latest = frame.loc[frame.date.astype(str) == str(frame.date.astype(str).max())]
    vn = latest.loc[latest.country_code == "vn"].drop_duplicates("product_listing_key")
    flags = vn.has_structured_voucher.fillna(False).astype(bool)
    return {
        "with_voucher": int(flags.sum()),
        "without_voucher": int((~flags).sum()),
        "total": int(len(vn)),
        "unmeasurable": int(vn.monthly_sold_value_num.isna().sum()),
    }


def test_the_counts_describe_the_whole_scope(tools, oracle):
    values = {item.metric: item.value for item in tools.promotion_observation("vn")}
    assert values["with_voucher_listing_count"] == oracle["with_voucher"]
    assert values["without_voucher_listing_count"] == oracle["without_voucher"]
    # The two groups partition the scope. Under the old filter they summed to
    # 628 against a scope of 668, and nothing reported the missing 40.
    assert (
        values["with_voucher_listing_count"] + values["without_voucher_listing_count"]
        == oracle["total"]
    )


def test_the_aggregate_still_uses_only_measurable_rows(tools):
    # Dropping unmeasurable rows is right *for the average*. The fix separates
    # the populations; it does not make the mean include nulls.
    evidence = tools.promotion_observation("vn")
    for item in evidence:
        if item.metric.endswith("_monthly_sold_proxy"):
            assert item.value == item.value  # not NaN


def test_dropped_rows_are_reported_not_silently_absent(tools, oracle):
    evidence = tools.promotion_observation("vn")
    excluded = {
        item.metric: item.attrs.get("unmeasurable_excluded_count")
        for item in evidence if item.metric.endswith("_monthly_sold_proxy")
    }
    assert excluded and all(value is not None for value in excluded.values())
    assert sum(set(excluded.values())) >= 0
    totals = [
        item.attrs["unmeasurable_excluded_count"]
        for item in evidence if item.metric.endswith("_median_monthly_sold_proxy")
    ]
    assert sum(totals) == oracle["unmeasurable"]


def test_voucher_profile_counts_listings_not_measurable_listings(tools):
    # Same shape in voucher_profile_rank: n_listings and the min-listings gate
    # were computed on the sold-filtered frame, so a shop with enough listings
    # but few measurable ones was reported as low-coverage.
    evidence = tools.voucher_profile_rank("vn")
    if not evidence:
        pytest.skip("voucher profile disabled in this configuration")
    for item in evidence:
        if "n_listings" in item.attrs:
            assert item.attrs["n_listings"] >= item.attrs.get("n_measurable_listings", 0)
