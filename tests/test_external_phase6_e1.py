"""Phase 6 E1: additive contracts and tier/provenance enforcement."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gladiators.agent.verifier import verify_numeric_claims
from gladiators.contracts import Evidence
from gladiators.domain.catalog import CATALOG
from gladiators.external.contracts import (
    ExternalProvenance, SourceLocator, SourceRegistryEntry, SourceSpan,
)
from gladiators.external.search_contracts import LiveSearchPlan, SearchQuery
from gladiators.planner.query_ir import LogicalQueryPlan, OutputField, PlanNode
from gladiators.planner.validator import validate_plan


NOW = datetime(2026, 7, 22, tzinfo=timezone.utc)
HASH = "a" * 64


def _provenance(tier="external") -> ExternalProvenance:
    return ExternalProvenance(
        source_id="live_web_search", source_tier=tier,
        source_locator=SourceLocator(kind="url", value="https://example.com/event"),
        content_hash=HASH, observed_at=NOW, retrieved_at=NOW,
        unit=None, currency=None, mapping_status="needs_review",
        admission="context_only", license="public-facts-with-attribution",
        caveats=("Chỉ dùng làm bối cảnh.",),
        provider="fake", search_query="campaign context fixture", result_rank=1,
        source_spans=(SourceSpan(field="event", text="event", start=0, end=5),),
    )


def _evidence(eid: str, tier: str, value: float) -> Evidence:
    return Evidence(
        evidence_id=eid, source_tier=tier, metric="test_metric", value=value,
        source_locator=SourceLocator(
            kind="internal" if tier == "btc_dataset" else "url",
            value="fixture" if tier == "btc_dataset" else "https://example.com/event",
        ),
        dataset_version="phase6-e1",
        provenance=None if tier == "btc_dataset" else _provenance(tier),
    )


def test_source_registry_is_fail_closed_and_requires_license():
    entry = SourceRegistryEntry(
        source_id="live_web_search", kind="api", default_tier="external",
        parser_id="p6_web_extract", schema_version="1.0",
        trust_level="public_aggregator", review_policy="per_batch_review",
        owner="DS1", license="provider-api-terms",
        allowed_use=("campaign_context",),
    )
    assert entry.enabled is False
    with pytest.raises(ValidationError):
        entry.model_copy(update={"license": ""}).model_validate(
            {**entry.model_dump(), "license": ""}
        )


def test_source_span_requires_ordered_offsets():
    assert SourceSpan(field="event", text="7.7 Sale", start=4, end=12).end == 12
    with pytest.raises(ValidationError):
        SourceSpan(field="event", text="7.7 Sale", start=12, end=4)


def test_non_internal_evidence_requires_matching_provenance():
    assert _evidence("ev:ext:0001", "external", 20).provenance is not None
    with pytest.raises(ValidationError, match="A21-PROV"):
        Evidence(
            evidence_id="ev:ext:0002", source_tier="external", metric="x", value=1,
            source_locator=SourceLocator(kind="url", value="https://example.com"),
            dataset_version="phase6-e1",
        )
    with pytest.raises(ValidationError, match="không khớp"):
        Evidence(
            evidence_id="ev:ref:0001", source_tier="reference", metric="x", value=1,
            source_locator=SourceLocator(kind="file", value="calendar.csv"),
            dataset_version="phase6-e1", provenance=_provenance("external"),
        )


def test_a20_blocks_one_claim_citing_multiple_tiers_but_allows_separate_claims():
    internal = _evidence("ev:btc:0001", "btc_dataset", 10)
    external = _evidence("ev:live:0002", "external", 20)
    mixed = verify_numeric_claims(
        "Giá trị 10 và bối cảnh 20 [ev:btc:0001] [ev:live:0002].",
        [internal, external],
    )
    assert mixed["passed"] is False
    assert mixed["tier_mixing"][0]["tiers"] == ["btc_dataset", "external"]

    separated = verify_numeric_claims(
        "Số nội bộ là 10 [ev:btc:0001].\n"
        "Bối cảnh ngoài ghi 20 [ev:live:0002] [nguồn: live_web_search, lấy 2026-07-22T00:00:00+00:00]. "
        "Dữ liệu needs_review — chưa xác nhận cùng sản phẩm/thực thể.",
        [internal, external],
    )
    assert separated["passed"] is True
    assert separated["tier_mixing"] == []


def test_a21_reports_missing_provenance_even_for_unvalidated_fixture():
    invalid = Evidence.model_construct(
        evidence_id="ev:ext:bad", source_tier="external", metric="x", value=1,
        source_locator=SourceLocator(kind="url", value="https://example.com"),
        source_path=None, dataset_version="phase6-e1", attrs={}, provenance=None,
        parent_evidence_ids=(),
    )
    result = verify_numeric_claims("Giá trị 1 [ev:ext:bad].", [invalid])
    assert result["passed"] is False
    assert result["provenance_gaps"] == [
        {"evidence_id": "ev:ext:bad", "reason": "missing_provenance"}
    ]


def test_a20_blocks_cross_tier_parent_evidence():
    internal = _evidence("ev:btc:0001", "btc_dataset", 10)
    external = _evidence("ev:live:0002", "external", 20)
    derived = _evidence("ev:derived:0003", "btc_dataset", 30).model_copy(update={
        "parent_evidence_ids": (internal.evidence_id, external.evidence_id),
    })
    result = verify_numeric_claims("Kết quả 30 [ev:derived:0003].", [internal, external, derived])
    assert result["passed"] is False
    assert result["tier_mixing"][0]["kind"] == "derived_evidence"


def test_context_catalog_is_non_physical_and_rejected_from_ir():
    context = CATALOG["context.campaign_window"]
    assert context.kind == "context"
    assert context.source_tier == "external"
    assert context.answerability == "context_only"
    assert context.physical == ()
    output = (OutputField(
        name="campaign_window", type="string", semantic_ref="context.campaign_window",
    ),)
    plan = LogicalQueryPlan(
        plan_id="phase6:forbidden_context_scan", output_node="n1",
        requested_output_shape=output, nodes=(PlanNode(
            node_id="n1", op="Scan", source="products_clean.csv",
            refs=("context.campaign_window",), input_grain="listing_snapshot",
            output_grain="listing_snapshot", expected_schema=output,
            expected_cardinality="<=3341",
        ),),
    )
    result = validate_plan(plan)
    assert result.valid is False
    assert any(issue.code == "tier_violation" for issue in result.issues)


def test_logical_query_plan_source_tier_remains_hard_locked():
    with pytest.raises(ValidationError):
        LogicalQueryPlan.model_validate({
            "plan_id": "phase6:external", "source_tier": "external",
            "nodes": [], "output_node": "n1", "requested_output_shape": [],
        })


def test_live_search_plan_defaults_cache_only_and_is_bounded():
    query = SearchQuery(
        query="Shopee 7.7 campaign 2026", market="id", recency_days=60,
        purpose="campaign_context",
    )
    assert LiveSearchPlan(plan_id="p1", queries=(query,)).mode == "cache_only"
    with pytest.raises(ValidationError):
        LiveSearchPlan(plan_id="p2", queries=(query, query, query, query))


def test_all_external_source_flags_default_off():
    config = yaml.safe_load(Path("configs/default.yaml").read_text(encoding="utf-8"))
    assert config["sources"]["live_search"]["enabled"] is False
    assert config["sources"]["live_search"]["mode"] == "cache_only"
    assert config["sources"]["live_search"]["max_admission"] == "context_only"
    assert config["sources"]["reference"]["enabled"] is False
    assert config["sources"]["external"]["enabled"] is False
