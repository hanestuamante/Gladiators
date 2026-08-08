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

    @cached_property
    def dataset_version(self) -> str:
        h = hashlib.sha256()
        for name in sorted(["products_clean.csv", "product_snapshot_metrics.csv", "product_transition_metrics.csv"]):
            # Git may check text artifacts out as CRLF on Windows and LF on
            # Linux.  The dataset is identical in both cases, so its version
            # must be based on canonical text bytes rather than OS line endings.
            payload = (self.root / name).read_bytes()
            h.update(payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
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
