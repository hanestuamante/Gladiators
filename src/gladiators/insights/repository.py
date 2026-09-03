"""Read-only bundle repository — ultimate solution §12.4 / §12.6.

Only the builder writes; everything here opens the bundle read-only.  The
repository pins one bundle object at construction and never reloads mid-request,
so a rebuild landing between two calls in the same request cannot produce a page
whose chart came from one dataset version and whose evidence came from another.

``INSIGHT_VERSION_MISMATCH`` exists for exactly that: when a caller asks for a
version this repository is not serving, the honest answer is 503, not a silent
substitution of whatever is loaded.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .contracts import BundleManifest, InsightCard, InsightEvidence


class InsightRepositoryError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class InsightRepository:
    """One immutable bundle, loaded once."""

    def __init__(self, bundle_dir: str | Path):
        self.bundle_dir = Path(bundle_dir)
        manifest_path = self.bundle_dir / "manifest.json"
        if not manifest_path.exists():
            raise InsightRepositoryError(
                "INSIGHT_BUNDLE_MISSING", f"Không tìm thấy manifest tại {self.bundle_dir}"
            )
        self.manifest = BundleManifest.model_validate(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
        self._cards = tuple(
            InsightCard.model_validate(record)
            for record in _read_jsonl(self.bundle_dir / "insight_cards.jsonl")
        )
        self._evidence = {
            item.evidence_id: item
            for item in (
                InsightEvidence.model_validate(record)
                for record in _read_jsonl(self.bundle_dir / "insight_evidence.jsonl")
            )
        }
        self._cards_by_id = {card.insight_id: card for card in self._cards}
        self._scorecard: pd.DataFrame | None = None

    # -- identity ----------------------------------------------------------

    @property
    def dataset_version(self) -> str:
        return self.manifest.dataset_version

    @property
    def as_of_date(self) -> str:
        return self.manifest.as_of_date

    def assert_version(self, requested: str | None) -> None:
        if requested and requested != self.dataset_version:
            raise InsightRepositoryError(
                "INSIGHT_VERSION_MISMATCH",
                f"Bundle đang phục vụ là {self.dataset_version}, không phải {requested}",
            )

    # -- reads -------------------------------------------------------------

    @property
    def scorecard(self) -> pd.DataFrame:
        if self._scorecard is None:
            self._scorecard = pd.read_csv(
                self.bundle_dir / "pam_scorecard.csv", low_memory=False
            )
        return self._scorecard

    def cards(
        self, *, country: str | None = None, kind: str | None = None,
        category_id: str | None = None, priority: str | None = None,
    ) -> tuple[InsightCard, ...]:
        result = self._cards
        if country:
            result = tuple(c for c in result if c.scope.country_code == country)
        if kind:
            result = tuple(c for c in result if c.kind == kind)
        if category_id:
            result = tuple(c for c in result if c.scope.platform_category_id == category_id)
        if priority:
            result = tuple(c for c in result if c.priority == priority)
        return result

    def card(self, insight_id: str) -> InsightCard | None:
        return self._cards_by_id.get(insight_id)

    def evidence(self, evidence_id: str) -> InsightEvidence | None:
        return self._evidence.get(evidence_id)

    def evidence_for(self, insight_id: str) -> tuple[InsightEvidence, ...]:
        card = self.card(insight_id)
        if card is None:
            return ()
        return tuple(
            item for item in (self._evidence.get(i) for i in card.evidence_ids)
            if item is not None
        )

    def segment_distribution(self, country: str) -> dict[str, int]:
        frame = self.scorecard
        subset = frame[frame["country_code"] == country]
        return {
            str(k): int(v) for k, v in
            subset["pam_segment"].value_counts().sort_index().items()
        }

    def overview(self, country: str) -> dict:
        frame = self.scorecard
        subset = frame[frame["country_code"] == country]
        quality_warnings = int(
            subset["price_sentinel_excluded"].astype(bool).sum()
            + subset["transition_missing"].astype(bool).sum()
        )
        return {
            "listings": int(len(subset)),
            "shops": int(subset["shop_id"].nunique()),
            "snapshot_coverage": self.as_of_date,
            "active_quality_warnings": quality_warnings,
            "segments": self.segment_distribution(country),
        }

    def price_move_chart(self, country: str) -> dict:
        """Typed chart payload (§12.4). Never a sentence from a model."""
        points = []
        for card in self.cards(country=country, kind="price_move"):
            items = {item.metric: item for item in self.evidence_for(card.insight_id)}
            x = items.get("price_change_percent")
            y = items.get("snapshot_sales_delta_clean")
            if x is None or y is None:
                continue
            points.append({
                "listing_key": x.stable_row_key.split("@")[0],
                "x": x.value, "y": y.value, "insight_id": card.insight_id,
                "evidence_ids": list(card.evidence_ids),
            })
        return {
            "chart_id": "price_move_scatter",
            "x": {"field": "price_change_percent", "unit": "percent"},
            "y": {"field": "snapshot_sales_delta_clean", "unit": "sold_proxy_delta"},
            "points": points,
        }

    def health(self) -> dict:
        """Schema/version/hash/build status -- never a path or a secret (§12.4)."""
        return {
            "schema_version": self.manifest.schema_version,
            "dataset_version": self.dataset_version,
            "formula_version": self.manifest.formula_version,
            "as_of_date": self.as_of_date,
            "content_hash": self.manifest.content_hash()[:16],
            "row_counts": dict(self.manifest.row_counts),
            "status": "ok",
        }


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def latest_bundle_dir(root: str | Path) -> Path | None:
    """Newest bundle by manifest as_of_date, then dataset version."""
    candidates = [
        path for path in Path(root).glob("*")
        if path.is_dir() and (path / "manifest.json").exists()
    ]
    if not candidates:
        return None

    def key(path: Path):
        try:
            manifest = BundleManifest.model_validate(
                json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            )
            return (manifest.as_of_date, manifest.dataset_version)
        except (json.JSONDecodeError, ValueError):
            return ("", path.name)

    return sorted(candidates, key=key)[-1]
