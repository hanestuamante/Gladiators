"""PAM scoring — ultimate solution §12.2.

The unit is a listing, not a customer.  §12.2 ends with "do not call PAM
buyer-RFM" and that is a correctness instruction, not branding: RFM measures
people repeating purchases, this measures listings moving stock, and the two
license completely different decisions.

Three rules do the real work:

**Scoring happens inside country x platform category.**  A Vietnamese listing is
never ranked against an Indonesian one, because the sold proxy is capped
differently per market and the price is in a different currency.

**A missing transition is flagged, not filled.**  Substituting a delta of 0 for
an absent one would make a listing with no measurement look exactly like a
listing measured as flat, and the two are not the same claim.

**Sentinel prices void the monetary score entirely.**  A placeholder price
multiplied by a real sold count produces a revenue figure that is confident,
precise and meaningless -- so Monetary and PAM become null rather than wrong.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

FORMULA_VERSION = "pam_v1"

DEFAULT_WEIGHTS = (0.30, 0.40, 0.30)  # activity, momentum, monetary
MOMENTUM_SOLD_WEIGHT = 0.7
MOMENTUM_DELTA_WEIGHT = 0.3
DEFAULT_MIN_COHORT_SIZE = 20


@dataclass(frozen=True)
class PamConfig:
    min_cohort_size: int = DEFAULT_MIN_COHORT_SIZE
    weights: tuple[float, float, float] = DEFAULT_WEIGHTS
    window_days: int = 30

    def __post_init__(self):
        if not math.isclose(sum(self.weights), 1.0, abs_tol=1e-9):
            raise ValueError(f"PAM weights phải cộng lại bằng 1.0, đang là {sum(self.weights)}")


def percentile(series: pd.Series, *, ascending: bool = True) -> pd.Series:
    """§12.2: ``p = (average_rank - 1) / (n - 1)``, and ``n == 1`` gives 0.5.

    Average rank so tied values receive one shared percentile: breaking ties by
    row order would make the score depend on file ordering, and the bundle would
    stop being reproducible.
    """
    values = series.dropna()
    n = len(values)
    if n == 0:
        return pd.Series(dtype="float64", index=series.index)
    if n == 1:
        return pd.Series(0.5, index=values.index).reindex(series.index)
    ranks = values.rank(method="average", ascending=ascending)
    return ((ranks - 1) / (n - 1)).reindex(series.index)


def score_from_percentile(p: float | None) -> int | None:
    """``min(5, floor(p*5) + 1)`` -- a 1..5 band, never 0."""
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return None
    return int(min(5, math.floor(p * 5) + 1))


def _missing(value) -> bool:
    """True for None and for NaN.

    ``nan is None`` is False, so an ``is None`` check silently passes every
    voided score straight through. That mislabelled 63 listings whose monetary
    score had been deliberately voided as "Steady" -- a healthy segment -- when
    the whole point of voiding was to say we cannot score them.
    """
    if value is None:
        return True
    try:
        return bool(math.isnan(float(value)))
    except (TypeError, ValueError):
        return False


def segment_for(
    activity_score: int | None, momentum_score: int | None, monetary_score: int | None,
    *, latest_sold: float | None, latest_clean_delta: float | None,
    pam_score: float | None,
) -> str:
    """§12.2 precedence, applied in order and not reordered.

    Order matters more than the individual rules: a Dormant listing can satisfy
    the Steady condition, and evaluating Steady first would relabel it as
    healthy. The precedence *is* the definition.
    """
    if _missing(monetary_score) or _missing(pam_score):
        return "InsufficientData"
    if not _missing(activity_score) and activity_score <= 2 and (latest_sold or 0) == 0:
        return "Dormant"
    if (not _missing(latest_clean_delta) and latest_clean_delta < 0) or (
        not _missing(momentum_score) and momentum_score <= 2
    ):
        return "Cooling"
    if all(not _missing(s) and s >= 4 for s in (activity_score, momentum_score, monetary_score)):
        return "Star"
    if not _missing(momentum_score) and momentum_score >= 4 and monetary_score < 4:
        return "Rising"
    return "Steady"


def assign_cohorts(frame: pd.DataFrame, config: PamConfig) -> pd.DataFrame:
    """Primary cohort is (country, platform category); small ones fall back.

    A cohort of three would give a percentile that says more about the cohort's
    size than the listing's performance, so it falls back to country level and
    says so via ``cohort_fallback``.
    """
    frame = frame.copy()
    frame["category_missing"] = frame["platform_category_id"].isna() | (
        frame["platform_category_id"].astype(str).str.strip().isin(("", "nan", "None"))
    )
    primary = frame.groupby(
        ["country_code", "platform_category_id"], dropna=False
    )["product_listing_key"].transform("size")
    frame["cohort_fallback"] = frame["category_missing"] | (primary < config.min_cohort_size)
    frame["cohort_key"] = frame.apply(
        lambda row: row["country_code"] if row["cohort_fallback"]
        else f"{row['country_code']}|{row['platform_category_id']}",
        axis=1,
    )
    # The fallback cohort is the whole country, not merely the rows that fell
    # back. Sizing it from the fallen-back rows alone produced cohorts of 8 --
    # smaller than the threshold of 20 that triggered the fallback, so the
    # fallback defeated its own purpose while reporting success.
    country_size = frame.groupby("country_code")["product_listing_key"].transform("size")
    category_size = primary
    frame["cohort_size"] = country_size.where(frame["cohort_fallback"], category_size)
    return frame


def score_frame(frame: pd.DataFrame, config: PamConfig | None = None) -> pd.DataFrame:
    """Compute activity/momentum/monetary/PAM per §12.2."""
    config = config or PamConfig()
    frame = assign_cohorts(frame, config)

    parts: list[pd.DataFrame] = []
    for cohort_key, members in frame.groupby("cohort_key", dropna=False):
        # Rank the fallback rows against every listing in their country, not
        # just against each other: a percentile computed inside the small group
        # that triggered the fallback describes the group, not the market.
        if "|" in str(cohort_key):
            population = members
        else:
            population = frame[frame["country_code"] == cohort_key]
        cohort = population.copy()
        # Fewer days since a positive event is better, so activity ranks
        # ascending: the reversal is the point, not a detail.
        p_activity = percentile(cohort["activity_days"], ascending=False)
        p_sold = percentile(cohort["latest_monthly_sold"], ascending=True)
        p_delta = percentile(cohort["latest_clean_sales_delta"], ascending=True)
        p_monetary = percentile(cohort["latest_estimated_recent_revenue"], ascending=True)

        # Missing transition means sold-only momentum. Filling delta with 0
        # would make "not measured" indistinguishable from "measured as flat".
        momentum = pd.Series(index=cohort.index, dtype="float64")
        both = p_sold.notna() & p_delta.notna()
        momentum[both] = (
            MOMENTUM_SOLD_WEIGHT * p_sold[both] + MOMENTUM_DELTA_WEIGHT * p_delta[both]
        )
        sold_only = p_sold.notna() & ~p_delta.notna()
        momentum[sold_only] = p_sold[sold_only]

        cohort["_p_activity"] = p_activity
        cohort["_p_momentum"] = momentum
        cohort["_p_monetary"] = p_monetary
        # Keep only the rows this cohort owns; the wider population was needed
        # to rank against, not to emit twice.
        parts.append(cohort.loc[cohort.index.intersection(members.index)])

    scored = pd.concat(parts) if parts else frame
    scored = scored[~scored.index.duplicated(keep="first")]
    scored["activity_score"] = scored["_p_activity"].map(score_from_percentile)
    scored["momentum_score"] = scored["_p_momentum"].map(score_from_percentile)
    scored["monetary_score"] = scored["_p_monetary"].map(score_from_percentile)

    w_activity, w_momentum, w_monetary = config.weights

    def pam(row) -> float | None:
        # A sentinel or null price already voided the monetary proxy upstream;
        # a PAM score built on the other two would look complete and be wrong.
        if pd.isna(row["_p_monetary"]) or pd.isna(row["_p_activity"]) or pd.isna(row["_p_momentum"]):
            return None
        return round(100 * (
            w_activity * row["_p_activity"]
            + w_momentum * row["_p_momentum"]
            + w_monetary * row["_p_monetary"]
        ), 4)

    scored["pam_score"] = scored.apply(pam, axis=1)
    scored["pam_segment"] = scored.apply(
        lambda row: segment_for(
            row["activity_score"], row["momentum_score"], row["monetary_score"],
            latest_sold=row.get("latest_monthly_sold"),
            latest_clean_delta=row.get("latest_clean_sales_delta"),
            pam_score=row["pam_score"],
        ),
        axis=1,
    )
    scored["formula_version"] = FORMULA_VERSION
    return scored.drop(columns=[c for c in scored.columns if c.startswith("_p_")])
