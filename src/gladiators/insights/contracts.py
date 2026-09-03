"""Insight bundle contracts — ultimate solution §12.1.

Every identifier here is derived from content, never from a uuid or a clock.
That is not tidiness: the bundle is immutable and keyed by content hash, so a
build that produced different ids for identical data could never be shown to be
identical, and the collision check that protects the bundle would be useless.

``generated_at`` is the single exception and is therefore excluded from every
content hash -- §12.1 is explicit that it takes no part in determinism.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BUNDLE_SCHEMA_VERSION = "insight-bundle.v1"
CARD_SCHEMA_VERSION = "insight-card.v1"
EVIDENCE_SCHEMA_VERSION = "insight-evidence.v1"
FORMULA_VERSION = "pam_v1"

CardKind = Literal["top_mover", "price_move", "voucher_gap", "data_quality"]
Priority = Literal["high", "medium", "low"]
Confidence = Literal["observed", "estimated"]

PAM_SEGMENTS = (
    "InsufficientData", "Dormant", "Cooling", "Star", "Rising", "Steady",
)


def stable_id(prefix: str, *parts: Any) -> str:
    """Content-addressed id. Deterministic across builds by construction."""
    payload = "|".join(str(p) for p in parts)
    return f"{prefix}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def sha256_of(path) -> str:
    """Hash a text artifact by canonical bytes, not by OS line endings.

    Git checks these CSVs out as CRLF on Windows and LF on Linux, so hashing raw
    bytes gives one dataset two identities. The bundle directory is named from
    this hash, so the same data built on two platforms would land in two
    directories, the collision check would never fire, and there would be two
    "immutable" bundles for one dataset -- exactly what immutability was for.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        trailing_cr = b""
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            chunk = trailing_cr + chunk
            # A CRLF split across the chunk boundary would normalise to "\n\n"
            # if handled naively, so hold a trailing CR back for the next chunk.
            trailing_cr = b"\r" if chunk.endswith(b"\r") else b""
            if trailing_cr:
                chunk = chunk[:-1]
            digest.update(chunk.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
        if trailing_cr:
            digest.update(b"\n")
    return digest.hexdigest()


class InsightScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    country_code: Literal["vn", "id"]
    as_of_date: str
    platform_category_id: str | None = None


class InsightEvidence(BaseModel):
    """Internal evidence with an artifact locator a reader can follow back.

    ``source_artifact`` + ``stable_row_key`` is the whole point: a card whose
    number cannot be traced to a row is a claim, not a finding.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["insight-evidence.v1"] = EVIDENCE_SCHEMA_VERSION
    evidence_id: str
    insight_id: str
    metric: str
    value: float | int | str | None
    unit: str
    formula: str
    source_artifact: str
    stable_row_key: str
    caveat: str = ""
    dataset_version: str
    currency_code: str | None = None


class InsightCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["insight-card.v1"] = CARD_SCHEMA_VERSION
    insight_id: str
    kind: CardKind
    title: str
    finding: str
    scope: InsightScope
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    assumption_ids: tuple[str, ...] = ()
    recommended_action: str
    action_owner_role: str
    impact_metric: str
    baseline_value: float | None = None
    target_definition: str
    measurement_window: str
    confidence: Confidence
    priority: Priority
    dataset_version: str


def card_sort_key(card: InsightCard) -> tuple:
    """§12.3 ordering: priority desc, kind, country, category, id.

    Fully determined by content so two builds of the same data emit the same
    file, byte for byte.
    """
    rank = {"high": 0, "medium": 1, "low": 2}[card.priority]
    return (
        rank, card.kind, card.scope.country_code,
        card.scope.platform_category_id or "", card.insight_id,
    )


class BundleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["insight-bundle.v1"] = BUNDLE_SCHEMA_VERSION
    dataset_version: str
    formula_version: str = FORMULA_VERSION
    generated_at: str
    as_of_date: str
    source_files: dict[str, str] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    row_counts: dict[str, int] = Field(default_factory=dict)
    output_hashes: dict[str, str] = Field(default_factory=dict)

    def content_hash(self) -> str:
        """Hash of everything that describes the data.

        ``generated_at`` is excluded (§12.1): including a wall clock would make
        every rebuild look like a collision with itself.
        """
        payload = {
            "schema_version": self.schema_version,
            "dataset_version": self.dataset_version,
            "formula_version": self.formula_version,
            "as_of_date": self.as_of_date,
            "source_files": self.source_files,
            "parameters": self.parameters,
            "row_counts": self.row_counts,
            "output_hashes": self.output_hashes,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()


PAM_SCORECARD_COLUMNS: tuple[str, ...] = (
    # identity/scope
    "product_listing_key", "country_code", "shop_id", "item_id", "as_of_date",
    "platform_category_id", "platform_category_name",
    # raw proxy
    "last_positive_date", "activity_days", "latest_monthly_sold",
    "latest_clean_sales_delta", "latest_estimated_recent_revenue",
    # score
    "activity_score", "momentum_score", "monetary_score", "pam_score", "pam_segment",
    # quality
    "cohort_size", "cohort_fallback", "category_missing", "transition_missing",
    "price_sentinel_excluded",
    # lineage
    "dataset_version", "source_snapshot_key", "source_transition_key", "formula_version",
)

SCORECARD_UNIQUE_KEY: tuple[str, ...] = (
    "dataset_version", "product_listing_key", "as_of_date",
)
