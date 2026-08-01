"""The four miners — ultimate solution §12.3.

The wording guards are the substance here. A card saying "giảm giá 15% giúp
tăng doanh số" reads perfectly and no reader double-checks it, so the plausible
sentence is the dangerous one and the build breaks on it rather than shipping it.
"""
from __future__ import annotations

import pandas as pd
import pytest

from gladiators.insights.miners import (
    CAUSAL_PHRASES,
    CausalWordingError,
    MinerConfig,
    assert_no_causal_wording,
    mine_all,
    mine_data_quality,
    mine_price_moves,
    mine_top_movers,
    mine_voucher_gap,
)

AS_OF = "2026-07-03"
DS = "ds-1"


def transitions(n: int = 8, *, delta_sign: int = 1, pct: float = -15.0) -> pd.DataFrame:
    return pd.DataFrame([
        dict(product_listing_key=f"vn:{i}", country_code="vn", date=AS_OF,
             transition_metric_eligible=True,
             snapshot_sales_delta_clean=float((i + 1) * delta_sign),
             price_change_percent=pct)
        for i in range(n)
    ])


def snapshots(with_voucher: int = 12, without: int = 12) -> pd.DataFrame:
    rows = []
    for i in range(with_voucher):
        rows.append(dict(product_listing_key=f"vn:v{i}", country_code="vn", date=AS_OF,
                         has_structured_voucher=True, monthly_sold_value_num=float(100 + i)))
    for i in range(without):
        rows.append(dict(product_listing_key=f"vn:n{i}", country_code="vn", date=AS_OF,
                         has_structured_voucher=False, monthly_sold_value_num=float(50 + i)))
    return pd.DataFrame(rows)


# --- causal wording -------------------------------------------------------

def test_causal_wording_breaks_the_build():
    """The dataset has no experiment, no holdout and no control."""
    with pytest.raises(CausalWordingError):
        assert_no_causal_wording("Giảm giá giúp tăng doanh số", where="test")


def test_neutral_wording_passes():
    assert assert_no_causal_wording("Hai biến số cùng thay đổi trong một cửa sổ", where="test")


def test_every_generated_finding_is_checked():
    output = mine_all(
        snapshots=snapshots(), transitions=transitions(), issues=pd.DataFrame(),
        as_of_date=AS_OF, dataset_version=DS,
    )
    for card in output.cards:
        for phrase in CAUSAL_PHRASES:
            assert phrase not in card.finding.lower(), card.finding


# --- top movers -----------------------------------------------------------

def test_top_movers_respects_top_k():
    output = mine_top_movers(transitions(20), as_of_date=AS_OF, dataset_version=DS,
                             config=MinerConfig(top_k=5))
    assert len(output.cards) == 5


def test_top_movers_ignores_non_positive_delta():
    output = mine_top_movers(transitions(delta_sign=-1), as_of_date=AS_OF, dataset_version=DS)
    assert output.cards == []


def test_top_movers_ignores_ineligible_transitions():
    """A transition measured across a gap does not describe the window it
    appears to describe."""
    frame = transitions()
    frame["transition_metric_eligible"] = False
    assert mine_top_movers(frame, as_of_date=AS_OF, dataset_version=DS).cards == []


def test_every_card_carries_at_least_one_evidence():
    output = mine_top_movers(transitions(), as_of_date=AS_OF, dataset_version=DS)
    evidence_ids = {e.evidence_id for e in output.evidence}
    for card in output.cards:
        assert card.evidence_ids
        assert set(card.evidence_ids) <= evidence_ids


def test_evidence_points_back_to_an_artifact_and_row():
    """A card whose number cannot be traced to a row is a claim, not a finding."""
    output = mine_top_movers(transitions(), as_of_date=AS_OF, dataset_version=DS)
    for item in output.evidence:
        assert item.source_artifact.endswith(".csv")
        assert item.stable_row_key
        assert item.formula


# --- price move -----------------------------------------------------------

def test_tied_top_movers_say_the_order_is_not_a_ranking():
    """Observed in the real bundle: in one market every positive delta topped
    out at the same round number with several listings sharing it. Presenting
    five of them as the biggest movers reads as a ranking when it is a tie."""
    tied = pd.DataFrame([
        dict(product_listing_key=f"id:{i}", country_code="id", date=AS_OF,
             transition_metric_eligible=True, snapshot_sales_delta_clean=1000.0,
             price_change_percent=0.0)
        for i in range(8)
    ])
    output = mine_top_movers(tied, as_of_date=AS_OF, dataset_version=DS)
    assert len(output.cards) == 5
    for item in output.evidence:
        assert "8 listing cùng mức thay đổi" in item.caveat
        assert "bậc hiển thị" in item.caveat


def test_an_untied_top_mover_keeps_the_plain_caveat():
    output = mine_top_movers(transitions(3), as_of_date=AS_OF, dataset_version=DS)
    for item in output.evidence:
        assert "không có ý nghĩa xếp hạng" not in item.caveat
        assert "chỉ báo hiển thị" in item.caveat


def test_price_move_needs_both_a_drop_and_a_rise():
    assert mine_price_moves(transitions(pct=-2.0), as_of_date=AS_OF,
                            dataset_version=DS).cards == []
    assert mine_price_moves(transitions(delta_sign=-1), as_of_date=AS_OF,
                            dataset_version=DS).cards == []


def test_price_move_excludes_sentinel_listings():
    output = mine_price_moves(
        transitions(3), as_of_date=AS_OF, dataset_version=DS,
        sentinel_listings=frozenset({"vn:0", "vn:1", "vn:2"}),
    )
    assert output.cards == []


def test_price_move_emits_two_separate_evidence_records():
    """One per variable, so a reader sees two observations rather than one
    linked measurement."""
    output = mine_price_moves(transitions(1), as_of_date=AS_OF, dataset_version=DS)
    assert len(output.cards) == 1
    assert len(output.cards[0].evidence_ids) == 2
    metrics = {e.metric for e in output.evidence}
    assert metrics == {"price_change_percent", "snapshot_sales_delta_clean"}


def test_price_move_records_the_no_control_group_assumption():
    output = mine_price_moves(transitions(1), as_of_date=AS_OF, dataset_version=DS)
    assert "assume:no_control_group" in output.cards[0].assumption_ids


# --- voucher gap ----------------------------------------------------------

def test_voucher_gap_requires_ten_per_group():
    """A median over four rows describes those four rows."""
    assert mine_voucher_gap(snapshots(with_voucher=4), as_of_date=AS_OF,
                            dataset_version=DS).cards == []
    assert mine_voucher_gap(snapshots(without=3), as_of_date=AS_OF,
                            dataset_version=DS).cards == []


def test_voucher_gap_emits_with_sample_sizes():
    output = mine_voucher_gap(snapshots(), as_of_date=AS_OF, dataset_version=DS)
    assert len(output.cards) == 1
    assert all("n=" in e.caveat for e in output.evidence)
    assert "n=12" in output.cards[0].finding


def test_voucher_gap_never_says_lift_or_effectiveness():
    output = mine_voucher_gap(snapshots(), as_of_date=AS_OF, dataset_version=DS)
    finding = output.cards[0].finding.lower()
    assert "lift" not in finding
    assert "hiệu quả" not in finding
    assert "assume:groups_not_randomised" in output.cards[0].assumption_ids


def test_voucher_gap_is_vietnam_only():
    """Structured vouchers are only observed in VN."""
    frame = snapshots()
    frame["country_code"] = "id"
    assert mine_voucher_gap(frame, as_of_date=AS_OF, dataset_version=DS).cards == []


# --- data quality ---------------------------------------------------------

def test_data_quality_needs_a_source_mapping():
    """An issue with no source and no rows is a rumour."""
    issues = pd.DataFrame([{"issue": "x"}])
    assert mine_data_quality(issues, as_of_date=AS_OF, dataset_version=DS).cards == []


def test_data_quality_cards_are_high_priority_by_rule():
    """§12.3 reserves "high" for issues that directly affect a calculation, so
    it comes from a rule and never from a model."""
    issues = pd.DataFrame([
        {"issue": "null_price", "source_file": "products_clean.csv"},
        {"issue": "null_price", "source_file": "products_clean.csv"},
    ])
    output = mine_data_quality(issues, as_of_date=AS_OF, dataset_version=DS)
    assert len(output.cards) == 1
    assert output.cards[0].priority == "high"
    assert output.evidence[0].value == 2


# --- determinism ----------------------------------------------------------

def test_mining_is_deterministic():
    kwargs = dict(snapshots=snapshots(), transitions=transitions(),
                  issues=pd.DataFrame(), as_of_date=AS_OF, dataset_version=DS)
    first = mine_all(**kwargs)
    second = mine_all(**kwargs)
    assert [c.insight_id for c in first.cards] == [c.insight_id for c in second.cards]
    assert [e.evidence_id for e in first.evidence] == [e.evidence_id for e in second.evidence]


def test_insight_ids_carry_no_uuid_or_timestamp():
    output = mine_all(snapshots=snapshots(), transitions=transitions(),
                      issues=pd.DataFrame(), as_of_date=AS_OF, dataset_version=DS)
    for card in output.cards:
        assert card.insight_id.startswith("ic:")
        assert len(card.insight_id.rsplit(":", 1)[-1]) == 16
