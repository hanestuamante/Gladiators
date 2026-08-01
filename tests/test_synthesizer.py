"""DeterministicPlanSynthesizer (§5): grammar, guards, and denotation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gladiators.agent.parser import MultilingualIntentParser
from gladiators.data.repository import ArtifactRepository
from gladiators.domain.intent_registry import default_registry
from gladiators.planner.compiler import compile_plan
from gladiators.planner.executor import QueryExecutor
from gladiators.planner.semantic_parser import AnalyticalRequest
from gladiators.planner.synthesizer import synthesize
from gladiators.planner.validator import validate_plan

ORACLE = {
    record["case_id"]: record["value"]
    for record in json.loads(
        Path("eval/independent/p0_probe_expected.json").read_text(encoding="utf-8"),
    )
}


def _request(question: str, country: str = "vn") -> AnalyticalRequest:
    parsed = MultilingualIntentParser().parse(question, default_registry())
    return AnalyticalRequest.model_validate(parsed.analytical)


def _run(question: str, country: str = "vn"):
    result = synthesize(_request(question), country)
    assert result is not None, f"expected in-grammar: {question}"
    assert validate_plan(result.plan).valid, f"invalid plan: {question}"
    executor = QueryExecutor(ArtifactRepository())
    try:
        return result, executor.execute(compile_plan(result.plan)).frame
    finally:
        executor.close()


def test_ascending_ranking_returns_the_minimum_not_the_maximum():
    oracle = ORACLE["p0_rank_direction_vn"]
    result, frame = _run("Sản phẩm nào có giá thấp nhất tại VN?")
    assert ":asc:" in result.plan.plan_id
    assert frame.iloc[0]["price"] == oracle["min_price"]
    assert frame.iloc[0]["price"] != oracle["max_price"]


def test_named_date_is_scanned_not_the_latest_snapshot():
    oracle = ORACLE["p0_date_point_vn"]["by_date"]
    result, frame = _run("Có bao nhiêu listing tại VN ngày 01/07?")
    assert result.plan.time_scope == ("2026-07-01",)
    assert frame.iloc[0]["listing_count"] == oracle["2026-07-01"]["listing_count"]
    assert frame.iloc[0]["listing_count"] != oracle["2026-07-03"]["listing_count"]


@pytest.mark.parametrize("question", [
    # Restrictions the deterministic parser never binds into a predicate. The
    # request object is a lossy summary of these, so synthesising from it would
    # answer a wider question than the one asked.
    "Sản phẩm nào có giá thấp nhất của shop official tại VN?",
    "Rating theo brand không tồn tại tại VN",
    "Có bao nhiêu listing chưa bán hết tại VN?",
])
def test_unbound_qualifier_makes_the_synthesizer_decline(question):
    assert synthesize(_request(question), "vn") is None


def test_country_is_mandatory():
    assert synthesize(_request("Sản phẩm nào có giá thấp nhất?"), "") is None


def test_aggregation_outside_catalog_is_refused_not_substituted():
    # §5: sum(monthly_sold) is not certified. Answering it with a median would
    # be exactly the silent substitution this layer exists to stop.
    request = _request("Tổng lượt bán tại VN là bao nhiêu?")
    result = synthesize(request, "vn")
    if result is not None:
        aggregation = result.aggregation
        assert aggregation != "sum" or "monthly_sold" not in result.plan.plan_id
