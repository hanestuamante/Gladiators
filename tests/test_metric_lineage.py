"""Metric lineage, impact graph và caveat provenance — §E4.

``formula`` là documentation string, không phải AST. Sáu phụ thuộc metric→metric
trước đây chỉ nhìn thấy được bằng cách tìm tên trong chuỗi đó, và
``voucher_profile_score.depends_on`` khai một metric trong khi công thức dùng ba.
"""
from __future__ import annotations

import dataclasses

import pytest

from gladiators.domain.metrics import (
    METRIC_GRAPH,
    METRICS,
    MetricConstraint,
    MetricGraphError,
    build_metric_graph,
    effective_caveats,
    impact_of,
)


def test_registry_has_36_metrics_and_no_cycle():
    # 35 từ W11.2: discounted_listing_count và discounted_listing_rate.
    # 36 từ 01/09: `observed_day_count`. Ngày là một đơn vị đếm được như shop
    # hay brand, và trước đó "shop X xuất hiện trong bao nhiêu ngày" không bind
    # được measure nào nên rơi A19-CAT — dù `date` nằm ngay trong dữ liệu.
    assert len(METRICS) == 36
    assert METRIC_GRAPH.cycles == ()


def test_every_metric_to_metric_edge_is_declared():
    """§E4.1 tìm được sáu metric bằng substring; edge thứ bảy
    (`descriptive_gap_median_sold`) công thức không nhắc tên nên phép quét đó bỏ
    sót — đúng loại false negative mà lineage typed sinh ra để chặn."""
    edges = {
        name: tuple(spec.source_metrics)
        for name, spec in METRICS.items() if spec.source_metrics
    }
    assert edges == {
        "history_sold_decrease_flag": ("history_sold_delta_raw",),
        "history_sold_delta_clean": ("history_sold_delta_raw",),
        "median_estimated_recent_revenue": ("estimated_recent_revenue",),
        "similarity_score": ("text_sim", "category_overlap_depth", "brand_match",
                             "price_distance", "same_shelf_bonus"),
        "voucher_rate": ("has_structured_voucher",),
        "descriptive_gap_median_sold": ("has_structured_voucher",),
        "voucher_profile_score": ("voucher_rate", "median_discount_ratio",
                                  "descriptive_gap_median_sold"),
        # W11.2: tỷ lệ khai mẫu số là ba cạnh lineage TƯỜNG MINH — đúng thứ
        # bảng này tồn tại để bắt buộc.
        "discounted_listing_count": ("has_promo",),
        "discounted_listing_rate": ("discounted_listing_count", "product_count"),
    }
    assert METRIC_GRAPH.edge_count() == 16


def test_every_metric_has_lineage_to_a_column_or_a_tool():
    for name, spec in METRICS.items():
        assert spec.source_columns or spec.source_metrics or "tool_computed" in spec.tags, name
        assert spec.owner, name


def test_no_token_is_both_a_column_and_a_metric():
    for name, spec in METRICS.items():
        assert not (set(spec.source_columns) & set(spec.source_metrics)), name


def test_legacy_depends_on_is_preserved_and_fully_covered():
    """``depends_on`` giữ nguyên một release và trở thành legacy không
    authoritative — nhưng nếu nó nhắc thứ lineage mới không với tới thì một
    trong hai đang sai."""
    for name, spec in METRICS.items():
        reachable = set(spec.source_columns) | set(METRIC_GRAPH.ancestors(name))
        for parent in METRIC_GRAPH.ancestors(name):
            reachable |= set(METRICS[parent].source_columns)
        assert set(spec.depends_on) <= reachable, name


# --- impact ---------------------------------------------------------------

def test_voucher_impact_is_transitive():
    """§E4.1: has_structured_voucher → voucher_rate → voucher_profile_score.
    Không có lineage này, đổi metric gốc không cảnh báo được metric cuối."""
    impact = impact_of("has_structured_voucher")
    assert "voucher_rate" in impact.direct_consumers
    assert "descriptive_gap_median_sold" in impact.direct_consumers
    assert "voucher_profile_score" in impact.transitive_consumers
    assert "voucher_rate" in impact.transitive_consumers


def test_impact_reaches_similarity_components():
    for component in ("text_sim", "brand_match", "price_distance"):
        assert "similarity_score" in impact_of(component).direct_consumers


def test_impact_reports_affected_constraints():
    impact = impact_of("has_structured_voucher")
    assert "structured-voucher-positive" in impact.affected_constraints


def test_unknown_metric_impact_is_an_error():
    with pytest.raises(MetricGraphError):
        impact_of("khong_co_metric_nay")


# --- caveat provenance ----------------------------------------------------

def test_vn_only_caveat_is_traceable_along_the_path():
    """Caveat truyền theo path và giữ chỗ sinh ra; chép text vào metric cha làm
    mất khả năng biết caveat còn đúng không khi metric nguồn đổi."""
    pairs = effective_caveats("voucher_profile_score")
    sources = {source for source, _ in pairs}
    assert "has_structured_voucher" in sources
    assert any(
        source == "has_structured_voucher" and "VN" in caveat
        for source, caveat in pairs
    )


def test_effective_caveats_are_deduped_by_pair():
    pairs = effective_caveats("voucher_profile_score")
    assert len(pairs) == len(set(pairs))


def test_effective_caveats_include_the_metric_itself():
    pairs = effective_caveats("voucher_rate")
    assert any(source == "voucher_rate" for source, _ in pairs)


# --- fail-closed ----------------------------------------------------------

def test_unknown_source_metric_fails_the_build():
    broken = dict(METRICS)
    broken["voucher_rate"] = dataclasses.replace(
        broken["voucher_rate"], source_metrics=("khong_ton_tai",)
    )
    with pytest.raises(MetricGraphError, match="không tồn tại"):
        build_metric_graph(broken)


def test_self_edge_fails_the_build():
    broken = dict(METRICS)
    broken["voucher_rate"] = dataclasses.replace(
        broken["voucher_rate"], source_metrics=("voucher_rate",)
    )
    with pytest.raises(MetricGraphError, match="chính nó"):
        build_metric_graph(broken)


def test_cycle_fails_the_build():
    broken = dict(METRICS)
    broken["has_structured_voucher"] = dataclasses.replace(
        broken["has_structured_voucher"], source_metrics=("voucher_profile_score",)
    )
    with pytest.raises(MetricGraphError, match="cycle"):
        build_metric_graph(broken)


def test_constraint_without_a_decision_id_fails_the_build():
    """Constraint chưa ai duyệt không được lẻn vào định nghĩa metric."""
    broken = dict(METRICS)
    broken["has_structured_voucher"] = dataclasses.replace(
        broken["has_structured_voucher"],
        definition_constraints=(
            MetricConstraint("x", "measure.voucher_discount", "gt", (0,), "false", ""),
        ),
    )
    with pytest.raises(MetricGraphError, match="decision_id"):
        build_metric_graph(broken)


def test_metric_without_lineage_fails_the_build():
    broken = dict(METRICS)
    broken["voucher_rate"] = dataclasses.replace(
        broken["voucher_rate"], source_metrics=(), source_columns=(), tags=()
    )
    with pytest.raises(MetricGraphError, match="lineage"):
        build_metric_graph(broken)


def test_constraint_ref_must_resolve_in_the_catalog():
    from gladiators.domain import bindings
    from gladiators.domain.bindings import BindingError, default_binding_snapshot

    snapshot = default_binding_snapshot()
    broken = dict(METRICS)
    broken["has_structured_voucher"] = dataclasses.replace(
        broken["has_structured_voucher"],
        definition_constraints=(
            MetricConstraint("x", "measure.khong_ton_tai", "gt", (0,), "false", "d1"),
        ),
    )
    with pytest.raises(BindingError, match="không tồn tại"):
        bindings.validate_metadata_bindings(
            snapshot.tables, snapshot.catalog, snapshot.relations, broken
        )


def test_pending_metric_is_not_silently_enabled():
    """J3: voucher_profile_score giữ binding/lineage nhưng weight chờ DR1/Lead.
    Lineage là additive — nó không được tự cấp quyền phục vụ metric."""
    spec = METRICS["voucher_profile_score"]
    assert "pending_decision" in spec.tags
    assert spec.definition_constraints == ()


# --- WP-A9 · lineage gap ở verifier ---------------------------------------

def test_lineage_gap_fires_when_a_derived_number_has_no_ancestor_evidence():
    """Số dẫn xuất trình bày như số đo trực tiếp phải bị chặn.

    Gieo lỗi: claim trỏ `median_estimated_recent_revenue` mà không có evidence
    cho `estimated_recent_revenue` — tổ tiên metric của nó — và câu trả lời
    không mang caveat đã khai.

    Chọn metric này vì `estimated_recent_revenue` dựng thẳng từ CỘT, không từ
    metric nào, nên `ancestors()` của nó rỗng và nó không gieo lỗi được.
    """
    from gladiators.agent.verifier import _lineage_gaps
    from gladiators.contracts import Evidence, ResponseClaim
    from gladiators.external.contracts import SourceLocator

    evidence = [Evidence(
        evidence_id="ev:t:0001", source_tier="btc_dataset",
        metric="median_estimated_recent_revenue", value=1234.0, unit="local_currency",
        source_locator=SourceLocator(kind="internal", value="product_snapshot_metrics.csv#k"),
        dataset_version="v",
    )]
    claims = (ResponseClaim(
        claim_id="cl:t:0001", text="1234", claim_type="money", value=1234.0,
        evidence_id="ev:t:0001", evidence_path="value",
    ),)
    gaps = _lineage_gaps("Doanh thu là 1234.", evidence, claims)
    assert gaps and gaps[0]["kind"] == "lineage"
    assert gaps[0]["metric"] == "median_estimated_recent_revenue"


def test_declared_caveat_in_the_answer_satisfies_the_lineage_rule():
    """Hoặc đủ evidence tổ tiên, hoặc nói rõ đây là số dẫn xuất. Không có đường thứ ba."""
    from gladiators.agent.verifier import _lineage_gaps
    from gladiators.contracts import Evidence, ResponseClaim
    from gladiators.domain.metrics import METRICS
    from gladiators.external.contracts import SourceLocator

    caveat = METRICS["median_estimated_recent_revenue"].caveats[0]
    evidence = [Evidence(
        evidence_id="ev:t:0001", source_tier="btc_dataset",
        metric="median_estimated_recent_revenue", value=1234.0, unit="local_currency",
        source_locator=SourceLocator(kind="internal", value="product_snapshot_metrics.csv#k"),
        dataset_version="v",
    )]
    claims = (ResponseClaim(
        claim_id="cl:t:0001", text="1234", claim_type="money", value=1234.0,
        evidence_id="ev:t:0001", evidence_path="value",
    ),)
    assert _lineage_gaps(f"Doanh thu là 1234. {caveat}", evidence, claims) == []


def test_boolean_flag_ancestor_is_not_required_as_evidence():
    """`has_structured_voucher` là VỊ TỪ, không phải đại lượng hiển thị.

    Đòi một dòng Evidence cho nó cạnh `voucher_rate` là đòi bằng chứng cho một
    thứ không ai đọc. Phân biệt lấy từ `unit == "bool"` đã khai.
    """
    from gladiators.agent.verifier import _lineage_gaps
    from gladiators.contracts import Evidence, ResponseClaim
    from gladiators.external.contracts import SourceLocator

    evidence = [Evidence(
        evidence_id="ev:t:0001", source_tier="btc_dataset",
        metric="voucher_rate", value=0.9, unit="share_0_1",
        source_locator=SourceLocator(kind="internal", value="product_snapshot_metrics.csv#k"),
        dataset_version="v",
    )]
    claims = (ResponseClaim(
        claim_id="cl:t:0001", text="0.9", claim_type="percent", value=0.9,
        evidence_id="ev:t:0001", evidence_path="value",
    ),)
    assert _lineage_gaps("Tỷ lệ là 0.9.", evidence, claims) == []
