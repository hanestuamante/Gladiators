"""Prompt assembly contract — ultimate solution §6.6.

The selection order is an order of decreasing consequence. These tests check
that the budget can only ever take things that change how an answer is phrased,
never things that change whether it is right.
"""
from __future__ import annotations

import pytest

from gladiators.agent.context import RequestDigest
from gladiators.domain import topics
from gladiators.domain.catalog import CATALOG
from gladiators.domain.invariants import hard_invariants
from gladiators.domain.relations import RELATIONS
from gladiators.planner.context_packer import pack_context
from gladiators.planner.prompt_library import build_atomic_plan_context
from gladiators.planner.semantic_parser import DeterministicSemanticParser
from gladiators.planner.topic_router import TopicRouter


@pytest.fixture(scope="module")
def router():
    return TopicRouter()


@pytest.fixture(scope="module")
def parser():
    return DeterministicSemanticParser()


def digest(question: str) -> RequestDigest:
    return RequestDigest(
        normalized_question=question, language="vi", intent="analytical",
        countries=("vn",), requested_output_shape="scalar",
    )


def build(router, parser, question: str, **kwargs):
    request = parser.parse(question, "vi", "vn")
    routing = router.route(question, request)
    return routing, build_atomic_plan_context(digest(question), routing, **kwargs)


def pack(items, routing, **kwargs):
    kwargs.setdefault("budget_tokens", 6000)
    return pack_context("atomic_plan", "ds-1", "dg-1", routing.routing_hash, items, **kwargs)


# --- what the budget may never take ---------------------------------------

def test_required_ref_is_undroppable_even_when_its_topic_was_not_selected():
    """A ref the request bound but the route did not cover must still ship.

    Otherwise it vanishes between router and packer, and the planner produces a
    confident plan for a question it was shown two-thirds of.
    """
    routing = TopicRouter().route("Có bao nhiêu listing tại Việt Nam?", None)
    assert "T5" not in routing.domain_topic_ids
    items = build_atomic_plan_context(
        digest("q"), routing, required_refs=("measure.shop_followers",),
    )
    entry = next(i for i in items if i.item_id == "catalog:measure.shop_followers")
    assert entry.droppable is False


def test_hard_invariants_are_present_and_undroppable(router, parser):
    _, items = build(router, parser, "Giá trung bình tại Việt Nam")
    hard = {i.item_id for i in items if not i.droppable}
    for invariant_id in hard_invariants():
        assert f"invariant:{invariant_id}" in hard


def test_required_relations_are_undroppable(router, parser):
    routing, items = build(
        router, parser, "Lượt bán tháng theo shop tại VN",
        required_relations=("belongs_to",),
    )
    entry = next(i for i in items if i.item_id == "relation:belongs_to")
    assert entry.droppable is False


def test_under_budget_pressure_examples_go_before_catalog(router, parser):
    routing, items = build(
        router, parser, "Giá trung bình tại Việt Nam",
        required_refs=("measure.price",),
        examples=tuple(f"vi du {i} " + "x" * 300 for i in range(10)),
    )
    packed = pack(items, routing, budget_tokens=1400)
    dropped = {d.item_id for d in packed.dropped}
    assert any(d.startswith("example:") for d in dropped)
    assert "catalog:measure.price" in {i.item_id for i in packed.items}
    assert "digest" in {i.item_id for i in packed.items}


def test_digest_is_never_dropped(router, parser):
    routing, items = build(router, parser, "Giá trung bình tại Việt Nam")
    packed = pack(items, routing, budget_tokens=900)
    assert "digest" in {i.item_id for i in packed.items}


# --- what must never reach a prompt ---------------------------------------

def test_no_item_leaks_a_physical_column_or_join_key(router, parser):
    """§6.6: the planner may only ever address semantics."""
    _, items = build(router, parser, "Lượt bán tháng theo shop tại VN")
    blob = " ".join(str(v) for i in items for v in i.payload.values())
    assert ".csv" not in blob
    for spec in RELATIONS.values():
        for left, right in spec.join_keys:
            assert f"{left}=={right}" not in blob


def test_tool_computed_refs_never_enter_the_plan_context(router, parser):
    """Similarity refs look like measures in the catalogue but have no column."""
    _, items = build(router, parser, 'Sản phẩm nào tương tự "Chupa Chups"?')
    shipped = {ref for i in items if i.kind == "catalog" for ref in i.semantic_refs}
    assert not (shipped & topics.non_sql_refs())


# --- broad slice ----------------------------------------------------------

def test_broad_slice_is_refused_on_a_routed_question(router, parser):
    """Broad fallback must not become a way to reach a ref the route rejected."""
    routing, items = build(
        router, parser, "Giá trung bình tại Việt Nam", allow_broad_slice=True,
    )
    assert routing.mode == "topic_scoped"
    shipped = {ref for i in items if i.kind == "catalog" for ref in i.semantic_refs}
    assert shipped < set(CATALOG)


def test_broad_slice_is_allowed_only_for_unknown_or_overflow(router, parser):
    routing, items = build(
        router, parser, "Tỷ lệ chuyển đổi là bao nhiêu?", allow_broad_slice=True,
    )
    assert routing.mode == "unknown"
    shipped = {ref for i in items if i.kind == "catalog" for ref in i.semantic_refs}
    assert len(shipped) > 60


# --- packing behaviour ----------------------------------------------------

def test_routed_context_costs_far_less_than_the_whole_catalogue(router, parser):
    """Measured: routed catalogue context is ~1.2k tokens against 3.6k broad.

    Token reduction is a secondary goal per §7.3 and never traded for
    correctness, so this asserts a loose bound rather than a target.
    """
    routing, items = build(router, parser, "Giá trung bình tại Việt Nam",
                           required_refs=("measure.price",))
    packed = pack(items, routing)
    assert packed.estimated_tokens < 3000
    assert not packed.dropped


def test_context_is_deterministic_for_the_same_question(router, parser):
    a_routing, a_items = build(router, parser, "Giá trung bình tại Việt Nam")
    b_routing, b_items = build(router, parser, "Giá trung bình tại Việt Nam")
    assert pack(a_items, a_routing).context_hash == pack(b_items, b_routing).context_hash


def test_different_topics_produce_different_context(router, parser):
    a_routing, a_items = build(router, parser, "Giá trung bình tại Việt Nam")
    b_routing, b_items = build(router, parser, "Điểm đánh giá trung bình tại Việt Nam")
    assert a_routing.domain_topic_ids != b_routing.domain_topic_ids
    assert pack(a_items, a_routing).context_hash != pack(b_items, b_routing).context_hash
