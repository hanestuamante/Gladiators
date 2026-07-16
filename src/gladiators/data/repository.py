from __future__ import annotations

import hashlib
from functools import cached_property
from pathlib import Path

import pandas as pd

from .contracts import validate_artifacts


class ArtifactRepository:
    def __init__(self, root: str | Path = "data/processed", validate: bool = True):
        self.root = Path(root)
        if validate:
            validate_artifacts(self.root)

    def read(self, name: str) -> pd.DataFrame:
        return pd.read_csv(self.root / name)

    @cached_property
    def products(self) -> pd.DataFrame:
        return self.read("products_clean.csv")

    @cached_property
    def snapshots(self) -> pd.DataFrame:
        return self.read("product_snapshot_metrics.csv")

    @cached_property
    def transitions(self) -> pd.DataFrame:
        return self.read("product_transition_metrics.csv")

    @property
    def dataset_version(self) -> str:
        h = hashlib.sha256()
        for name in sorted(["products_clean.csv", "product_snapshot_metrics.csv", "product_transition_metrics.csv"]):
            h.update((self.root / name).read_bytes())
        return h.hexdigest()[:16]

    def capability_profile(self) -> dict[str, object]:
        p = self.products
        return {
            "countries": sorted(p.country_code.dropna().unique().tolist()),
            "dates": sorted(p.date.dropna().astype(str).unique().tolist()),
            "fields": sorted(p.columns.tolist()),
            "snapshot_count": int(p.date.nunique()),
            "voucher_structured_by_country": p.groupby("country_code")["voucher_code"].apply(lambda s: int(s.notna().sum())).to_dict(),
        }

