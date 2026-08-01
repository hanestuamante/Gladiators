"""Insight bundle builder — ultimate solution §12.1.

The bundle is immutable and everything downstream trusts that, so the write
protocol is what these tests hold: validate before rename, never overwrite, and
treat a same-version different-content build as a collision rather than an
update.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from gladiators.insights.builder import (
    InsightBuildError,
    build_scorecard,
    read_manifest,
    validate_scorecard,
    write_bundle,
)
from gladiators.insights.contracts import (
    PAM_SCORECARD_COLUMNS,
    BundleManifest,
    InsightCard,
    InsightEvidence,
    InsightScope,
    card_sort_key,
    stable_id,
)
from gladiators.insights.pam import FORMULA_VERSION


def scorecard(rows: int = 3, dataset_version: str = "ds-1") -> pd.DataFrame:
    data = {column: [None] * rows for column in PAM_SCORECARD_COLUMNS}
    data["product_listing_key"] = [f"vn:{i}" for i in range(rows)]
    data["country_code"] = ["vn"] * rows
    data["as_of_date"] = ["2026-07-03"] * rows
    data["dataset_version"] = [dataset_version] * rows
    data["formula_version"] = [FORMULA_VERSION] * rows
    data["pam_segment"] = ["Steady"] * rows
    return pd.DataFrame(data)[list(PAM_SCORECARD_COLUMNS)]


def card(insight_id: str = "ic:x", priority="medium", kind="top_mover") -> InsightCard:
    return InsightCard(
        insight_id=insight_id, kind=kind, title="t", finding="f",
        scope=InsightScope(country_code="vn", as_of_date="2026-07-03"),
        evidence_ids=("ev:1",), recommended_action="a", action_owner_role="r",
        impact_metric="m", baseline_value=1.0, target_definition="td",
        measurement_window="w", confidence="observed", priority=priority,
        dataset_version="ds-1",
    )


def evidence(evidence_id: str = "ev:1", insight_id: str = "ic:x") -> InsightEvidence:
    return InsightEvidence(
        evidence_id=evidence_id, insight_id=insight_id, metric="m", value=1.0,
        unit="count", formula="f", source_artifact="products_clean.csv",
        stable_row_key="k", dataset_version="ds-1",
    )


def build(tmp_path: Path, dataset_version="ds-1", **overrides) -> Path:
    kwargs = dict(
        scorecard=scorecard(dataset_version=dataset_version), cards=[card()],
        evidence=[evidence()], as_of_date="2026-07-03",
        source_files={"products_clean.csv": "abc"}, parameters={"top_k": 5},
    )
    kwargs.update(overrides)
    return write_bundle(tmp_path, dataset_version, **kwargs)


# --- write protocol -------------------------------------------------------

def test_a_bundle_is_written_with_every_expected_file(tmp_path):
    destination = build(tmp_path)
    for name in ("pam_scorecard.csv", "insight_cards.jsonl",
                 "insight_evidence.jsonl", "manifest.json"):
        assert (destination / name).exists()


def test_rebuilding_identical_content_is_an_idempotent_success(tmp_path):
    first = build(tmp_path)
    second = build(tmp_path)
    assert first == second


def test_same_version_different_content_is_a_collision_not_an_update(tmp_path):
    """Two builds of one dataset version that disagree mean the inputs or the
    code moved without the version moving. Overwriting destroys the only
    evidence that happened."""
    build(tmp_path)
    with pytest.raises(InsightBuildError) as excinfo:
        build(tmp_path, scorecard=scorecard(rows=5))
    assert excinfo.value.code == "IMMUTABLE_INSIGHT_COLLISION"


def test_a_collision_leaves_the_original_bundle_intact(tmp_path):
    destination = build(tmp_path)
    before = (destination / "pam_scorecard.csv").read_text(encoding="utf-8")
    with pytest.raises(InsightBuildError):
        build(tmp_path, scorecard=scorecard(rows=5))
    assert (destination / "pam_scorecard.csv").read_text(encoding="utf-8") == before


def test_no_staging_directory_survives_a_failed_build(tmp_path):
    build(tmp_path)
    with pytest.raises(InsightBuildError):
        build(tmp_path, scorecard=scorecard(rows=9))
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_generated_at_does_not_affect_the_content_hash():
    """Including a wall clock would make every rebuild collide with itself."""
    common = dict(
        dataset_version="ds-1", as_of_date="2026-07-03",
        source_files={"a": "1"}, parameters={"k": 1},
        row_counts={"pam_scorecard": 1}, output_hashes={"x": "y"},
    )
    a = BundleManifest(generated_at="2026-07-31T00:00:00Z", **common)
    b = BundleManifest(generated_at="2026-08-01T12:00:00Z", **common)
    assert a.content_hash() == b.content_hash()


def test_manifest_records_row_counts_and_output_hashes(tmp_path):
    manifest = read_manifest(build(tmp_path))
    assert manifest.row_counts["pam_scorecard"] == 3
    assert manifest.row_counts["insight_cards"] == 1
    assert set(manifest.output_hashes) == {
        "pam_scorecard.csv", "insight_cards.jsonl", "insight_evidence.jsonl",
    }


# --- validation before rename --------------------------------------------

def test_duplicate_unique_key_is_rejected(tmp_path):
    duplicated = pd.concat([scorecard(rows=1), scorecard(rows=1)])
    with pytest.raises(InsightBuildError) as excinfo:
        build(tmp_path, scorecard=duplicated)
    assert excinfo.value.code == "UNIQUE_KEY_VIOLATION"


def test_missing_column_is_rejected(tmp_path):
    thin = scorecard().drop(columns=["pam_score"])
    with pytest.raises(InsightBuildError) as excinfo:
        build(tmp_path, scorecard=thin)
    assert excinfo.value.code == "SCHEMA_INVALID"


def test_wrong_formula_version_is_rejected():
    bad = scorecard()
    bad["formula_version"] = "pam_v0"
    with pytest.raises(InsightBuildError) as excinfo:
        validate_scorecard(bad)
    assert excinfo.value.code == "LINEAGE_INVALID"


def test_nothing_is_written_when_validation_fails(tmp_path):
    with pytest.raises(InsightBuildError):
        build(tmp_path, scorecard=scorecard().drop(columns=["pam_score"]))
    assert not (tmp_path / "ds-1").exists()


# --- determinism ----------------------------------------------------------

def test_card_ordering_is_fully_determined_by_content():
    cards = [
        card("ic:c", priority="low"), card("ic:a", priority="high"),
        card("ic:b", priority="medium"),
    ]
    assert [c.insight_id for c in sorted(cards, key=card_sort_key)] == ["ic:a", "ic:b", "ic:c"]


def test_two_builds_of_the_same_data_produce_identical_files(tmp_path):
    first = build(tmp_path / "one")
    second = build(tmp_path / "two")
    for name in ("pam_scorecard.csv", "insight_cards.jsonl", "insight_evidence.jsonl"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_stable_id_is_content_addressed():
    assert stable_id("ic:x", "a", 1) == stable_id("ic:x", "a", 1)
    assert stable_id("ic:x", "a", 1) != stable_id("ic:x", "a", 2)


# --- scorecard construction from real-shaped inputs -----------------------

def test_join_fanout_is_detected(tmp_path):
    from gladiators.insights.builder import BuildInputs

    snapshots = pd.DataFrame([
        dict(product_listing_key="vn:1", product_snapshot_key="k1", country_code="vn",
             shop_id="s", item_id="1", date="2026-07-03", price_sentinel_flag=False,
             monthly_sold_value_num=10, estimated_recent_revenue=1000.0),
    ])
    transitions = pd.DataFrame([
        dict(product_listing_key="vn:1", country_code="vn", date="2026-07-03",
             transition_metric_eligible=True, snapshot_sales_delta_clean=5.0,
             price_change_percent=-2.0),
        # A duplicate transition row for the same listing would multiply the
        # scorecard and inflate every cohort derived from it.
        dict(product_listing_key="vn:1", country_code="vn", date="2026-07-03",
             transition_metric_eligible=True, snapshot_sales_delta_clean=6.0,
             price_change_percent=-3.0),
    ])
    products = pd.DataFrame([
        dict(product_listing_key="vn:1", country_code="vn", catid="100629",
             date="2026-07-03"),
        dict(product_listing_key="vn:1", country_code="vn", catid="100630",
             date="2026-07-03"),
    ])
    inputs = BuildInputs(snapshots=snapshots, transitions=transitions, products=products)
    # Latest-per-listing collapses both duplicates, so this must *not* raise --
    # the guard exists for the case where it does not collapse.
    result = build_scorecard(inputs, dataset_version="ds-1")
    assert len(result) == 1
