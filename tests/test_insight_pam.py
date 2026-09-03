"""PAM scoring — ultimate solution §12.2.

Three of these tests exist because the real build produced a plausible wrong
answer: a fallback cohort smaller than the threshold that triggered it, an
activity window read from the wrong transition, and a voided score labelled
"Steady". None of the three would have shown up as an error.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from gladiators.insights.pam import (
    DEFAULT_WEIGHTS,
    PamConfig,
    assign_cohorts,
    percentile,
    score_frame,
    score_from_percentile,
    segment_for,
)


def listing_frame(n_vn: int = 30, n_id: int = 30, small_category: int = 5) -> pd.DataFrame:
    rows = []
    for i in range(n_vn):
        rows.append(dict(
            product_listing_key=f"vn:{i}", country_code="vn", shop_id="s1", item_id=str(i),
            platform_category_id="100629", activity_days=float(i % 10),
            latest_monthly_sold=float(i * 3), latest_clean_sales_delta=float(i - 5),
            latest_estimated_recent_revenue=float(i * 1000),
        ))
    for i in range(small_category):
        rows.append(dict(
            product_listing_key=f"vn-small:{i}", country_code="vn", shop_id="s2",
            item_id=str(i), platform_category_id="999999", activity_days=float(i),
            latest_monthly_sold=float(i * 2), latest_clean_sales_delta=1.0,
            latest_estimated_recent_revenue=float(i * 500),
        ))
    for i in range(n_id):
        rows.append(dict(
            product_listing_key=f"id:{i}", country_code="id", shop_id="s3", item_id=str(i),
            platform_category_id="100630", activity_days=float(i % 7),
            latest_monthly_sold=float(i * 5), latest_clean_sales_delta=float(i - 2),
            latest_estimated_recent_revenue=float(i * 2000),
        ))
    return pd.DataFrame(rows)


# --- percentile -----------------------------------------------------------

def test_percentile_formula_matches_the_spec():
    series = pd.Series([10.0, 20.0, 30.0])
    assert list(percentile(series)) == [0.0, 0.5, 1.0]


def test_single_member_cohort_gets_one_half():
    assert list(percentile(pd.Series([7.0]))) == [0.5]


def test_ties_share_a_percentile_so_the_bundle_stays_reproducible():
    """Breaking ties by row order would make the score depend on file ordering."""
    tied = percentile(pd.Series([5.0, 5.0, 9.0]))
    assert tied.iloc[0] == tied.iloc[1]


def test_score_bands_are_one_to_five():
    assert score_from_percentile(0.0) == 1
    assert score_from_percentile(1.0) == 5
    assert score_from_percentile(0.5) == 3
    assert score_from_percentile(None) is None
    assert score_from_percentile(float("nan")) is None


# --- the NaN bug ----------------------------------------------------------

def test_a_voided_monetary_score_is_insufficient_data_not_steady():
    """``nan is None`` is False, so an ``is None`` check passed every voided
    score through. On the real dataset that labelled 63 listings whose monetary
    score had been deliberately voided as "Steady" -- a healthy segment."""
    assert segment_for(3, 3, float("nan"), latest_sold=5, latest_clean_delta=1,
                       pam_score=float("nan")) == "InsufficientData"
    assert segment_for(3, 3, None, latest_sold=5, latest_clean_delta=1,
                       pam_score=None) == "InsufficientData"


def test_segment_precedence_is_applied_in_order():
    """A Dormant listing also satisfies Steady; evaluating Steady first would
    relabel it healthy. The precedence is the definition."""
    assert segment_for(1, 5, 5, latest_sold=0, latest_clean_delta=0,
                       pam_score=50.0) == "Dormant"
    assert segment_for(5, 1, 5, latest_sold=10, latest_clean_delta=-3,
                       pam_score=50.0) == "Cooling"
    assert segment_for(5, 5, 5, latest_sold=10, latest_clean_delta=2,
                       pam_score=90.0) == "Star"
    assert segment_for(5, 5, 2, latest_sold=10, latest_clean_delta=2,
                       pam_score=60.0) == "Rising"
    assert segment_for(3, 3, 3, latest_sold=10, latest_clean_delta=1,
                       pam_score=50.0) == "Steady"


# --- the cohort bug -------------------------------------------------------

def test_fallback_cohort_is_the_whole_country_not_the_leftovers():
    """Sizing the fallback from the fallen-back rows produced cohorts of 8 --
    smaller than the threshold of 20 that triggered the fallback, so the
    fallback defeated its own purpose while reporting success."""
    frame = assign_cohorts(listing_frame(), PamConfig(min_cohort_size=20))
    fell_back = frame[frame["cohort_fallback"]]
    assert not fell_back.empty
    country_total = (frame["country_code"] == "vn").sum()
    assert set(fell_back["cohort_size"]) == {country_total}
    assert fell_back["cohort_size"].min() >= 20


def test_large_category_keeps_its_own_cohort():
    frame = assign_cohorts(listing_frame(), PamConfig(min_cohort_size=20))
    kept = frame[~frame["cohort_fallback"]]
    assert set(kept["platform_category_id"]) == {"100629", "100630"}


def test_fallback_rows_are_ranked_against_the_whole_country():
    """A percentile computed inside the small group that triggered the fallback
    describes the group, not the market."""
    scored = score_frame(listing_frame(), PamConfig(min_cohort_size=20))
    small = scored[scored["product_listing_key"].str.startswith("vn-small")]
    assert len(small) == 5
    # Five listings ranked among themselves would span the full 1..5 range.
    # Ranked against 35 VN listings with far higher revenue, they cluster low.
    assert small["monetary_score"].max() <= 3


def test_no_listing_is_emitted_twice_by_the_wider_population():
    scored = score_frame(listing_frame(), PamConfig(min_cohort_size=20))
    assert len(scored) == len(listing_frame())
    assert scored["product_listing_key"].nunique() == len(scored)


def test_markets_are_never_ranked_against_each_other():
    """The sold proxy is capped differently per market and price is in a
    different currency, so a cross-market percentile compares nothing."""
    scored = score_frame(listing_frame(), PamConfig(min_cohort_size=20))
    for country in ("vn", "id"):
        subset = scored[scored["country_code"] == country]
        assert subset["cohort_key"].str.startswith(country).all()


# --- momentum -------------------------------------------------------------

def test_missing_transition_uses_sold_only_and_does_not_fill_zero():
    """Filling delta with 0 would make "not measured" indistinguishable from
    "measured as flat"."""
    frame = listing_frame(n_vn=25, n_id=25, small_category=0)
    frame.loc[frame.index[:5], "latest_clean_sales_delta"] = None
    scored = score_frame(frame, PamConfig(min_cohort_size=20))
    missing = scored[scored["latest_clean_sales_delta"].isna()]
    assert not missing.empty
    assert missing["momentum_score"].notna().all()


def test_null_monetary_makes_pam_null():
    frame = listing_frame(n_vn=25, n_id=25, small_category=0)
    frame.loc[frame.index[:3], "latest_estimated_recent_revenue"] = None
    scored = score_frame(frame, PamConfig(min_cohort_size=20))
    voided = scored[scored["latest_estimated_recent_revenue"].isna()]
    assert voided["pam_score"].isna().all()
    assert (voided["pam_segment"] == "InsufficientData").all()


# --- config ---------------------------------------------------------------

def test_weights_must_sum_to_one():
    with pytest.raises(ValueError, match="cộng lại bằng 1"):
        PamConfig(weights=(0.5, 0.4, 0.3))


def test_default_weights_are_the_documented_ones():
    assert DEFAULT_WEIGHTS == (0.30, 0.40, 0.30)
    assert math.isclose(sum(DEFAULT_WEIGHTS), 1.0)


def test_pam_score_is_bounded():
    scored = score_frame(listing_frame(), PamConfig(min_cohort_size=20))
    values = scored["pam_score"].dropna()
    assert values.min() >= 0.0
    assert values.max() <= 100.0
