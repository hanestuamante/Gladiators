"""LegacyPlanningInputFactory — ultimate solution §8.8.

The factory exists so the compatibility adapter holds no planning logic. The
test that matters is the one below about country: a factory that reconciles a
mismatch by rewriting the digest lets a caller silently redirect a request to a
market nobody asked about.
"""
from __future__ import annotations

import pytest

from gladiators.agent.context import RequestDigest
from gladiators.planner.decomposer import AnalyticalDecomposer, DecomposerInputMismatch
from gladiators.planner.legacy_input import LegacyPlanningInputFactory
from gladiators.planner.semantic_parser import DeterministicSemanticParser

PARSER = DeterministicSemanticParser()
QUESTION = "Giá trung bình tại Việt Nam"


@pytest.fixture(scope="module")
def factory():
    return LegacyPlanningInputFactory(dataset_version="ds-1")


def test_legacy_arguments_become_a_verified_decomposer_input(factory):
    payload = factory.from_legacy(
        question=QUESTION, request=PARSER.parse(QUESTION, "vi", "vn"), country="vn",
    )
    payload.verify()
    assert payload.context_snapshot.dataset_version == "ds-1"
    assert payload.packed_context.routing_hash == payload.routing.routing_hash


def test_country_outside_the_digest_is_refused_not_reconciled(factory):
    """Rewriting the digest here would redirect the request to another market."""
    digest = RequestDigest(
        normalized_question=PARSER.parse(QUESTION, "vi", "vn").normalized_question,
        language="vi", intent="analytical",
        countries=("vn",), requested_output_shape="scalar",
    )
    with pytest.raises(DecomposerInputMismatch, match="country"):
        factory.from_legacy(
            question=QUESTION, request=PARSER.parse(QUESTION, "vi", "vn"),
            country="id", digest=digest,
        )


def test_matching_country_is_accepted(factory):
    request = PARSER.parse(QUESTION, "vi", "vn")
    # A real digest is derived from the request, so it carries the normalized
    # question -- not the raw one the user typed.
    digest = RequestDigest(
        normalized_question=request.normalized_question, language="vi",
        intent="analytical", countries=("vn", "id"), requested_output_shape="scalar",
    )
    payload = factory.from_legacy(
        question=QUESTION, request=request, country="id", digest=digest,
    )
    payload.verify()


def test_factory_output_is_accepted_by_the_decomposer(factory):
    """End to end: the conversion produces something the decomposer will run."""
    payload = factory.from_legacy(
        question=QUESTION, request=PARSER.parse(QUESTION, "vi", "vn"), country="vn",
    )
    result = AnalyticalDecomposer().build_execution_plan(payload)
    assert result.mode == "deterministic_atomic"


def test_snapshot_pins_the_live_registry_hashes(factory):
    from gladiators.domain import topics

    payload = factory.from_legacy(
        question=QUESTION, request=PARSER.parse(QUESTION, "vi", "vn"), country="vn",
    )
    assert payload.context_snapshot.topic_hash == topics.REGISTRY_HASH
    assert payload.context_snapshot.execution_context_hash


def test_supplied_routing_is_not_recomputed(factory):
    """§8.8: the decomposer path must not re-route; nor may the factory."""
    request = PARSER.parse(QUESTION, "vi", "vn")
    from gladiators.planner.topic_router import TopicRouter
    routing = TopicRouter().route(QUESTION, request)
    payload = factory.from_legacy(
        question=QUESTION, request=request, country="vn", routing=routing,
    )
    assert payload.routing is routing
