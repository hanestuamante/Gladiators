"""AnalyticalDecomposer — ultimate solution §8.4 / §8.8.

Two behaviours matter most. The decomposer must refuse an input whose pieces
disagree rather than repairing it, because a component that rebuilds its own
inputs eventually disagrees with the state everything else was validated
against and nothing reports it. And it must derive a split when there is exactly
one sensible split, rather than asking a model to guess a shape we can compute.
"""
from __future__ import annotations

import pytest

from gladiators.agent.context import RequestDigest
from gladiators.planner.atoms import atomize_request
from gladiators.planner.context_packer import pack_context
from gladiators.planner.decomposer import (
    AnalyticalDecomposer,
    DecomposerInput,
    DecomposerInputMismatch,
    infer_deterministic_decomposition,
)
from gladiators.planner.decomposition_validator import validate_decomposition_proposal
from gladiators.planner.feasibility import analyze
from gladiators.planner.semantic_parser import DeterministicSemanticParser
from gladiators.planner.topic_router import TopicRouter
from tests.test_execution_plan import snapshot

PARSER = DeterministicSemanticParser()
ROUTER = TopicRouter()


def digest_for(question: str, countries=("vn",)) -> RequestDigest:
    return RequestDigest(
        normalized_question=question, language="vi", intent="analytical",
        countries=countries, requested_output_shape="scalar",
    )


def build_input(question: str, *, countries=("vn",), country="vn", **overrides):
    request = PARSER.parse(question, "vi", country)
    routing = ROUTER.route(question, request)
    packed = pack_context("atomic_plan", "ds-1", "dg-1", routing.routing_hash, [])
    base = dict(
        normalized_question=question, request=request, digest=digest_for(question, countries),
        routing=routing, packed_context=packed, context_snapshot=snapshot("ds-1"),
    )
    base.update(overrides)
    return DecomposerInput(**base)


# --- input integrity ------------------------------------------------------

def test_a_consistent_input_verifies():
    build_input("Giá trung bình tại Việt Nam").verify()


def test_question_mismatch_between_input_and_digest_is_terminal():
    payload = build_input("Giá trung bình tại Việt Nam")
    mismatched = payload.model_copy(update={"digest": digest_for("một câu hỏi khác")})
    with pytest.raises(DecomposerInputMismatch, match="normalized_question"):
        mismatched.verify()


def test_routing_hash_mismatch_is_terminal():
    payload = build_input("Giá trung bình tại Việt Nam")
    other = ROUTER.route("Điểm đánh giá tại Việt Nam", None)
    with pytest.raises(DecomposerInputMismatch, match="routing_hash"):
        payload.model_copy(update={"routing": other}).verify()


def test_dataset_version_mismatch_is_terminal():
    payload = build_input("Giá trung bình tại Việt Nam")
    with pytest.raises(DecomposerInputMismatch, match="dataset_version"):
        payload.model_copy(update={"context_snapshot": snapshot("ds-9")}).verify()


def test_decomposer_never_repairs_its_input_to_continue():
    """§8.8: silently reconciling the input is how two components end up
    validated against different state."""
    payload = build_input("Giá trung bình tại Việt Nam")
    broken = payload.model_copy(update={"digest": digest_for("khác hẳn")})
    with pytest.raises(DecomposerInputMismatch):
        AnalyticalDecomposer().build_execution_plan(broken)


# --- atomic path ----------------------------------------------------------

def test_a_feasible_request_stays_atomic():
    result = AnalyticalDecomposer().build_execution_plan(
        build_input("Giá trung bình tại Việt Nam")
    )
    assert result.mode == "deterministic_atomic"
    assert result.planning_meta["feasible"] is True
    assert result.decomposition_attempts == 0


def test_two_topics_do_not_force_a_split():
    """§8.3's example, end to end through the decomposer."""
    payload = build_input("Tỷ lệ có voucher theo shop chính hãng tại VN")
    assert len(payload.routing.domain_topic_ids) > 1
    result = AnalyticalDecomposer().build_execution_plan(payload)
    assert result.mode == "deterministic_atomic"


def test_no_llm_call_is_made_on_the_deterministic_path():
    """The decomposer reports what it needs; the caller decides via the gate."""
    class ExplodingService:
        def propose(self, *a, **k):
            raise AssertionError("decomposer đã gọi LLM ngoài dự kiến")

    result = AnalyticalDecomposer(proposal_service=ExplodingService()).build_execution_plan(
        build_input("Giá trung bình tại Việt Nam")
    )
    assert result.mode == "deterministic_atomic"


# --- deterministic decomposition -----------------------------------------

def cross_market_pieces():
    question = "Giá trung bình tại Việt Nam và Indonesia"
    request = PARSER.parse(question, "vi", "vn")
    routing = ROUTER.route(question, request)
    digest = digest_for(question, ("vn", "id"))
    # The parser injects one country; a genuine two-market request carries both.
    filters = tuple(request.filters) + ()
    atoms = atomize_request(digest, request)
    from gladiators.planner.atoms import make_atom
    atoms = atoms + (make_atom("country", semantic_ref="dim.country", value="id"),)
    feasibility = analyze(request, routing, countries=("vn", "id"))
    return digest, request, atoms, feasibility


def test_incompatible_units_across_markets_infer_a_union_scope_split():
    """One sensible reading only: same measurement, disjoint markets."""
    digest, request, atoms, feasibility = cross_market_pieces()
    assert "unit_incompatible" in feasibility.blockers
    proposal = infer_deterministic_decomposition(digest, request, atoms, feasibility)
    assert proposal is not None
    assert proposal.composition.op == "union_scope"
    assert len(proposal.subrequests) == 2


def test_an_inferred_proposal_passes_its_own_validator():
    """A split the code derived must satisfy the same grammar as one a model
    proposed -- otherwise the deterministic path is unchecked."""
    digest, request, atoms, feasibility = cross_market_pieces()
    proposal = infer_deterministic_decomposition(digest, request, atoms, feasibility)
    assert validate_decomposition_proposal(proposal) == ()


def test_a_feasible_request_infers_no_decomposition():
    question = "Giá trung bình tại Việt Nam"
    request = PARSER.parse(question, "vi", "vn")
    routing = ROUTER.route(question, request)
    digest = digest_for(question)
    atoms = atomize_request(digest, request)
    feasibility = analyze(request, routing, countries=("vn",))
    assert infer_deterministic_decomposition(digest, request, atoms, feasibility) is None


def test_nothing_inferrable_reports_rather_than_guessing():
    """Returning None is the signal to ask a model, not a failure. A wrong
    deterministic split would carry the authority of a rule."""
    question = "Giá trung bình tại Việt Nam"
    request = PARSER.parse(question, "vi", "vn")
    routing = ROUTER.route(question, request)
    digest = digest_for(question)
    atoms = atomize_request(digest, request)
    feasibility = analyze(request, routing, countries=("vn",), context_fits=False)
    assert not feasibility.feasible
    assert infer_deterministic_decomposition(digest, request, atoms, feasibility) is None


def test_decomposer_reports_blockers_for_the_caller():
    payload = build_input("Giá trung bình tại Việt Nam")
    result = AnalyticalDecomposer().build_execution_plan(payload)
    assert "blockers" in result.planning_meta
    assert result.planning_meta["decomposer_version"]


def test_subplan_count_never_exceeds_four():
    from gladiators.planner.decomposer import MAX_SUBPLANS
    digest, request, atoms, feasibility = cross_market_pieces()
    proposal = infer_deterministic_decomposition(digest, request, atoms, feasibility)
    assert len(proposal.subrequests) <= MAX_SUBPLANS
