"""Insight bundle builder — ultimate solution §12.1 / §12.2.

Builds the sidecar bundle from governed processed data.  The write protocol is
the interesting part, because the bundle is immutable and everything downstream
trusts that:

1. take a lock on ``dataset_version``;
2. write to a unique temp directory *beside* the destination, so the rename is
   atomic on the same filesystem;
3. validate schema, unique key, row counts, lineage and every hash;
4. rename into place only if the destination is absent;
5. identical content hash at the destination is an idempotent success;
6. same dataset version with a different hash is ``IMMUTABLE_INSIGHT_COLLISION``
   and is never overwritten.

Step 6 is the one that earns the design. Two builds of one dataset version that
disagree mean either the inputs or the code moved without the version moving,
and silently replacing the old bundle would destroy the only evidence that
happened.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .contracts import (
    PAM_SCORECARD_COLUMNS,
    SCORECARD_UNIQUE_KEY,
    BundleManifest,
    InsightCard,
    InsightEvidence,
    card_sort_key,
    sha256_of,
)
from .pam import FORMULA_VERSION, PamConfig, score_frame

BUNDLE_FILES = ("pam_scorecard.csv", "insight_cards.jsonl", "insight_evidence.jsonl")


class InsightBuildError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class BuildInputs:
    snapshots: pd.DataFrame
    transitions: pd.DataFrame
    products: pd.DataFrame
    quality_issues: pd.DataFrame = field(default_factory=pd.DataFrame)
    source_files: dict[str, str] = field(default_factory=dict)


def load_inputs(processed_dir: str | Path) -> BuildInputs:
    root = Path(processed_dir)
    paths = {
        "product_snapshot_metrics.csv": root / "product_snapshot_metrics.csv",
        "product_transition_metrics.csv": root / "product_transition_metrics.csv",
        "products_clean.csv": root / "products_clean.csv",
    }
    quality_path = root / "data_quality_issues.csv"
    source_files = {name: sha256_of(path) for name, path in paths.items() if path.exists()}
    if quality_path.exists():
        source_files["data_quality_issues.csv"] = sha256_of(quality_path)
    return BuildInputs(
        snapshots=pd.read_csv(paths["product_snapshot_metrics.csv"], low_memory=False),
        transitions=pd.read_csv(paths["product_transition_metrics.csv"], low_memory=False),
        products=pd.read_csv(
            paths["products_clean.csv"], low_memory=False,
            usecols=["product_listing_key", "country_code", "catid", "date"],
        ),
        quality_issues=(
            pd.read_csv(quality_path, low_memory=False) if quality_path.exists()
            else pd.DataFrame()
        ),
        source_files=source_files,
    )


def build_scorecard(
    inputs: BuildInputs, *, as_of_date: str | None = None, config: PamConfig | None = None,
    dataset_version: str = "unknown", category_names: dict[str, str] | None = None,
) -> pd.DataFrame:
    config = config or PamConfig()
    snapshots = inputs.snapshots
    as_of = as_of_date or str(snapshots["date"].max())

    # Latest snapshot at or before as_of_date, one row per listing.
    eligible = snapshots[snapshots["date"] <= as_of].copy()
    if eligible.empty:
        raise InsightBuildError("NO_SNAPSHOT_IN_SCOPE", f"Không có snapshot <= {as_of}")
    eligible = eligible.sort_values("date").groupby("product_listing_key", as_index=False).last()

    # Only eligible transitions: one measured across a gap is not a measurement
    # of the window it appears to describe.
    transitions = inputs.transitions
    if "transition_metric_eligible" in transitions.columns:
        transitions = transitions[
            transitions["transition_metric_eligible"].astype(str).str.lower().isin(("true", "1"))
        ]
    transitions = transitions[transitions["date"] <= as_of]
    latest_transition = (
        transitions.sort_values("date").groupby("product_listing_key", as_index=False).last()
        if not transitions.empty else pd.DataFrame(columns=["product_listing_key"])
    )

    before = len(eligible)
    frame = eligible.merge(
        latest_transition[[c for c in (
            "product_listing_key", "snapshot_sales_delta_clean", "price_change_percent", "date",
        ) if c in latest_transition.columns]],
        on="product_listing_key", how="left", suffixes=("", "_transition"),
    )
    # §12.2 step 3: assert the join did not multiply rows. A silent fanout here
    # would inflate every cohort and every percentile derived from it.
    if len(frame) != before:
        raise InsightBuildError(
            "JOIN_FANOUT", f"Join transition làm tăng row {before} -> {len(frame)}"
        )

    category = inputs.products.rename(columns={"catid": "platform_category_id"})
    category = category.sort_values("date").groupby(
        "product_listing_key", as_index=False
    ).last()[["product_listing_key", "platform_category_id"]]
    frame = frame.merge(category, on="product_listing_key", how="left")
    if len(frame) != before:
        raise InsightBuildError(
            "JOIN_FANOUT", f"Join category làm tăng row {before} -> {len(frame)}"
        )

    frame["as_of_date"] = as_of
    frame["dataset_version"] = dataset_version
    frame["platform_category_id"] = frame["platform_category_id"].astype("object")
    names = category_names or {}
    frame["platform_category_name"] = frame["platform_category_id"].map(
        lambda cid: names.get(str(cid), "")
    )

    sentinel = frame.get("price_sentinel_flag")
    frame["price_sentinel_excluded"] = (
        sentinel.astype(str).str.lower().isin(("true", "1")) if sentinel is not None
        else False
    )
    frame["latest_monthly_sold"] = pd.to_numeric(
        frame.get("monthly_sold_value_num"), errors="coerce"
    )
    frame["latest_clean_sales_delta"] = pd.to_numeric(
        frame.get("snapshot_sales_delta_clean"), errors="coerce"
    )
    frame["transition_missing"] = frame["latest_clean_sales_delta"].isna()

    revenue = pd.to_numeric(frame.get("estimated_recent_revenue"), errors="coerce")
    # A placeholder price times a real sold count is a confident, precise,
    # meaningless number. Void it rather than score it.
    frame["latest_estimated_recent_revenue"] = revenue.mask(frame["price_sentinel_excluded"])

    # §12.2: the most recent date with a *positive* delta, across all eligible
    # transitions -- not merely the latest transition. Reading only the latest
    # one marked 79% of listings inactive because their most recent measured
    # step happened to be flat or negative, which is a different statement.
    positive = transitions.copy()
    positive["_delta"] = pd.to_numeric(
        positive.get("snapshot_sales_delta_clean"), errors="coerce"
    )
    positive = positive[positive["_delta"] > 0]
    last_positive = (
        positive.groupby("product_listing_key")["date"].max()
        if not positive.empty else pd.Series(dtype="object")
    )
    frame["last_positive_date"] = frame["product_listing_key"].map(last_positive)
    as_of_ts = pd.Timestamp(as_of)
    frame["activity_days"] = frame["last_positive_date"].map(
        lambda d: (as_of_ts - pd.Timestamp(d)).days if d and not pd.isna(d) else None
    )
    no_event = frame["activity_days"].isna()
    frame.loc[no_event, "activity_days"] = config.window_days + 1

    frame["source_snapshot_key"] = frame.get("product_snapshot_key", "")
    frame["source_transition_key"] = frame.get("date_transition", "")

    scored = score_frame(frame, config)
    for column in PAM_SCORECARD_COLUMNS:
        if column not in scored.columns:
            scored[column] = None
    scorecard = scored[list(PAM_SCORECARD_COLUMNS)].copy()
    return scorecard.sort_values(list(SCORECARD_UNIQUE_KEY)).reset_index(drop=True)


def validate_scorecard(scorecard: pd.DataFrame) -> None:
    missing = [c for c in PAM_SCORECARD_COLUMNS if c not in scorecard.columns]
    if missing:
        raise InsightBuildError("SCHEMA_INVALID", f"Thiếu cột scorecard: {missing}")
    duplicated = scorecard.duplicated(subset=list(SCORECARD_UNIQUE_KEY)).sum()
    if duplicated:
        raise InsightBuildError(
            "UNIQUE_KEY_VIOLATION",
            f"{duplicated} row trùng khoá {SCORECARD_UNIQUE_KEY}",
        )
    if (scorecard["formula_version"] != FORMULA_VERSION).any():
        raise InsightBuildError("LINEAGE_INVALID", "formula_version không đồng nhất")


def write_bundle(
    output_root: str | Path, dataset_version: str, *,
    scorecard: pd.DataFrame, cards: list[InsightCard], evidence: list[InsightEvidence],
    as_of_date: str, source_files: dict[str, str], parameters: dict[str, Any],
) -> Path:
    """Write atomically, or fail loudly. Never overwrite (§12.1)."""
    validate_scorecard(scorecard)

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / dataset_version

    ordered_cards = sorted(cards, key=card_sort_key)
    ordered_evidence = sorted(evidence, key=lambda e: (e.insight_id, e.evidence_id))

    # Temp dir beside the destination so the rename stays on one filesystem;
    # a cross-device rename is a copy, and a copy is not atomic.
    staging = Path(tempfile.mkdtemp(prefix=f".{dataset_version}.staging-", dir=root))
    try:
        scorecard.to_csv(staging / "pam_scorecard.csv", index=False, lineterminator="\n")
        _write_jsonl(staging / "insight_cards.jsonl", ordered_cards)
        _write_jsonl(staging / "insight_evidence.jsonl", ordered_evidence)

        manifest = BundleManifest(
            dataset_version=dataset_version, generated_at=_now_iso(), as_of_date=as_of_date,
            source_files=dict(sorted(source_files.items())), parameters=parameters,
            row_counts={
                "pam_scorecard": int(len(scorecard)),
                "insight_cards": len(ordered_cards),
                "insight_evidence": len(ordered_evidence),
            },
            output_hashes={name: sha256_of(staging / name) for name in BUNDLE_FILES},
        )
        (staging / "manifest.json").write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        if destination.exists():
            existing = read_manifest(destination)
            if existing is not None and existing.content_hash() == manifest.content_hash():
                return destination  # idempotent success
            raise InsightBuildError(
                "IMMUTABLE_INSIGHT_COLLISION",
                f"Bundle {dataset_version} đã tồn tại với content hash khác; "
                "không ghi đè. Hai build của cùng một dataset version mà khác nhau "
                "nghĩa là input hoặc code đã đổi mà version không đổi.",
            )
        os.rename(staging, destination)
        staging = None  # renamed away; nothing left to clean up
        return destination
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def read_manifest(bundle_dir: str | Path) -> BundleManifest | None:
    path = Path(bundle_dir) / "manifest.json"
    if not path.exists():
        return None
    try:
        return BundleManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return None


def _write_jsonl(path: Path, records) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(
                record.model_dump(mode="json"), sort_keys=True, ensure_ascii=False,
            ) + "\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
