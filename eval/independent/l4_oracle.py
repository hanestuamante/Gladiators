"""Independent L4 denotation oracle.

This module intentionally imports no production ``gladiators`` code. Gold
denotations are computed from frozen CSV bytes with an explicit, reviewable
semantic-to-column mapping.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


MEASURE_COLUMNS = {
    "measure.price": "price_num",
    "measure.price_original": "price_original_num",
    "measure.discount_percent": "discount_percent_num",
    "measure.monthly_sold": "monthly_sold_value_num",
    "measure.history_sold": "history_sold_value_num",
    "measure.rating": "rating_num",
    "measure.rating_count": "rating_count_num",
    "measure.liked_count": "liked_count_num",
    "measure.images_count": "images_count",
    "measure.variation_options_count": "tier_variation_options_count",
}
PRICE_REFS = {"measure.price", "measure.price_original"}


def _scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return value


def build_l4_denotation(case: dict, data_dir: str | Path = "data/processed") -> list[dict[str, Any]]:
    """Return reviewed-shape candidate gold for one explicit max-by-brand case."""
    if case.get("aggregation") != "max":
        raise ValueError("L4 oracle hiện chỉ hỗ trợ aggregation=max đã khai trong fixture.")
    measures = tuple(case["measures"])
    unknown = sorted(set(measures) - set(MEASURE_COLUMNS))
    if unknown:
        raise ValueError(f"L4 oracle chưa có mapping cho: {unknown}")

    frame = pd.read_csv(Path(data_dir) / "products_clean.csv", low_memory=False)
    frame = frame.loc[
        (frame.country_code == case["country"])
        & (frame.date.astype(str) == case["snapshot_date"])
    ].copy()
    for ref in measures:
        if ref in PRICE_REFS:
            frame = frame.loc[frame[MEASURE_COLUMNS[ref]].lt(999_999_999)]

    columns = [MEASURE_COLUMNS[ref] for ref in measures]
    grouped = frame.groupby("brand", dropna=False, sort=True)[columns].max().reset_index()
    rows: list[dict[str, Any]] = []
    for row in grouped.itertuples(index=False, name=None):
        item = {"brand": _scalar(row[0])}
        item.update({ref.rsplit(".", 1)[-1]: _scalar(value) for ref, value in zip(measures, row[1:])})
        rows.append(item)
    return rows
