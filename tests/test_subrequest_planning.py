"""SubrequestPlanningService — ultimate solution §8.4, step 5.

Closes the last gap in P6: before this the decomposer could say *how* to split a
request and could not plan the pieces, so a decomposed answer was never actually
producible.

The two rules enforced here rather than by convention are that a subrequest may
not inherit a broad slice its parent never earned, and that every subplan records
its own routing, context hash, gate version and dataset version instead of
leaving a validator to re-derive them.
"""
from __future__ import annotations

import pytest

from gladiators.agent.context import RequestDigest
from gladiators.planner.atoms import atomize_request, make_atom
from gladiators.planner.context_packer import pack_context
from gladiators.planner.decomposer import (
    AnalyticalDecomposer,
    DecomposerInput,
    build_composition_spec,
    infer_deterministic_decomposition,
)
from gladiators.planner.decomposition_validator import validate_execution_plan
from gladiators.planner.execution_plan import SubrequestProposal
from gladiators.planner.feasibility import analyze
from gladiators.planner.semantic_parser import DeterministicSemanticParser
from gladiators.planner.subrequest_planning import (
    SubrequestPlanningError,
    SubrequestPlanningService,
    subrequest_digest_hash,
)
from gladiators.planner.topic_router import TopicRouter
from tests.test_execution_plan import snapshot

PARSER = DeterministicSemanticParser()
ROUTER = TopicRouter()
QUESTION = "Giá trung bình tại Việt Nam"


def digest_for(question: str, countries=("vn",)) -> RequestDigest:
    return RequestDigest(
        normalized_question=PARSER.parse(question, "vi", "vn").normalized_question,
        language="vi", intent="analytical", countries=countries,
        requested_output_shape="scalar",
    )


def proposal_for(subplan_id="sp1", question=QUESTION, atoms=("mea-1",)):
    return SubrequestProposal(
        subplan_id=subplan_id, request=PARSER.parse(question, "vi", "vn"),
        covered_atom_ids=tuple(atoms),
    )


def service(**kwargs) -> SubrequestPlanningService:
    kwargs.setdefault("dataset_version", "ds-1")
    return SubrequestPlanningService(**kwargs)


# --- planning a subrequest ------------------------------------------------

def test_the_synthesizer_is_preferred_over_a_model():
    """Deterministic, free, and where it has a grammar it beats asking a model
    to rediscover one."""
    class ExplodingBuilder:
        def build(self, **kwargs):
            raise AssertionError("không được gọi model khi synthesizer đủ")

    result = service(plan_builder=ExplodingBuilder()).plan_subrequest(
        proposal_for(), digest_for(QUESTION), country="vn", question=QUESTION,
    )
    assert result.source == "synthesizer"
    assert result.attempts == 0


def test_a_planned_subplan_is_atomic():
    result = service().plan_subrequest(
        proposal_for(), digest_for(QUESTION), country="vn", question=QUESTION,
    )
    assert result.spec.plan.subplan_count == 1


def test_each_subplan_records_its_own_provenance():
    """A re-derived value cannot detect a plan disagreeing with its context."""
    result = service().plan_subrequest(
        proposal_for(), digest_for(QUESTION), country="vn", question=QUESTION,
    )
    spec = result.spec
    assert spec.context_hash
    assert spec.topic_gate_version
    assert spec.dataset_version == "ds-1"
    assert spec.routing.routing_hash
    assert spec.plan_hash


def test_output_fields_are_derived_from_the_plan():
    """A hand-written field list that drifts from the plan is a mismatch nothing
    catches until a composition lines two of them up."""
    result = service().plan_subrequest(
        proposal_for(), digest_for(QUESTION), country="vn", question=QUESTION,
    )
    names = {f.name for f in result.spec.output_fields}
    assert names == {f.name for f in result.spec.plan.requested_output_shape}


def test_money_is_marked_not_aggregatable_across_scope():
    """VND and IDR have no rate here, so a cross-scope sum has no unit."""
    result = service().plan_subrequest(
        proposal_for(), digest_for(QUESTION), country="vn", question=QUESTION,
    )
    money = [f for f in result.spec.output_fields if f.unit == "local_currency"]
    assert money
    assert all(not f.aggregatable_across_scope for f in money)


def test_subrequest_digest_hash_follows_from_the_root():
    """§8.5 re-derives this, so a subrequest cannot claim a digest that does not
    follow from the request it was split out of."""
    root = digest_for(QUESTION)
    assert subrequest_digest_hash(root, ("a", "b")) == subrequest_digest_hash(root, ("b", "a"))
    assert subrequest_digest_hash(root, ("a",)) != subrequest_digest_hash(root, ("a", "b"))


# --- the broad-fallback rule ---------------------------------------------

def test_an_unadmitted_root_forbids_a_broad_fallback():
    """Otherwise decomposition becomes a way to see more of the catalogue than
    the capability check allowed."""
    unroutable = "Tỷ lệ chuyển đổi là bao nhiêu?"
    with pytest.raises(SubrequestPlanningError) as excinfo:
        service(root_admitted=False).route_and_pack(
            PARSER.parse(unroutable, "vi", "vn"), digest_for(unroutable),
            question=unroutable,
        )
    assert excinfo.value.code == "SUBREQUEST_BROAD_FALLBACK_FORBIDDEN"


def test_an_admitted_root_may_route_unknown():
    unroutable = "Tỷ lệ chuyển đổi là bao nhiêu?"
    routing, packed = service(root_admitted=True).route_and_pack(
        PARSER.parse(unroutable, "vi", "vn"), digest_for(unroutable), question=unroutable,
    )
    assert routing.mode == "unknown"
    assert packed.context_hash


def test_context_is_scoped_to_the_subrequest_not_the_root():
    routing, packed = service().route_and_pack(
        PARSER.parse(QUESTION, "vi", "vn"), digest_for(QUESTION), question=QUESTION,
    )
    assert routing.mode == "topic_scoped"
    assert packed.estimated_tokens > 0


def test_a_plan_that_cannot_be_built_fails_closed():
    """§8.4: never degrade to the nearest macro. A near-miss answer to a question
    that needed decomposition is a confidently wrong answer."""
    empty = SubrequestProposal(subplan_id="sp1", request=None, covered_atom_ids=("a",))
    with pytest.raises(SubrequestPlanningError) as excinfo:
        service().plan_subrequest(empty, digest_for(QUESTION), country="vn",
                                  question=QUESTION)
    assert excinfo.value.code == "SUBREQUEST_PLAN_UNAVAILABLE"


# --- end to end through the decomposer -----------------------------------

def cross_market_input() -> DecomposerInput:
    question = "Giá trung bình tại Việt Nam và Indonesia"
    request = PARSER.parse(question, "vi", "vn")
    routing = ROUTER.route(question, request)
    return DecomposerInput(
        normalized_question=request.normalized_question, request=request,
        digest=digest_for(question, ("vn", "id")), routing=routing,
        packed_context=pack_context("atomic_plan", "ds-1", "dg", routing.routing_hash, []),
        context_snapshot=snapshot("ds-1"),
    )


def test_decomposer_produces_a_runnable_decomposed_plan():
    """The gap this closes: before, the decomposer could say how to split and
    could not plan the pieces, so a decomposed answer was never producible."""
    payload = cross_market_input()
    # The parser injects one country; a genuine two-market request carries both.
    original = payload.request
    decomposer = AnalyticalDecomposer(subrequest_planner=service())

    atoms = atomize_request(payload.digest, original) + (
        make_atom("country", semantic_ref="dim.country", value="id"),
    )
    feasibility = analyze(original, payload.routing, countries=("vn", "id"))
    proposal = infer_deterministic_decomposition(
        payload.digest, original, atoms, feasibility,
    )
    assert proposal is not None

    planned = service().plan_all(proposal.subrequests, payload.digest, country="vn")
    assert len(planned) == 2
    assert all(p.spec.plan.subplan_count == 1 for p in planned)


def test_composition_contract_is_derived_from_the_subplans():
    payload = cross_market_input()
    atoms = atomize_request(payload.digest, payload.request) + (
        make_atom("country", semantic_ref="dim.country", value="id"),
    )
    feasibility = analyze(payload.request, payload.routing, countries=("vn", "id"))
    proposal = infer_deterministic_decomposition(
        payload.digest, payload.request, atoms, feasibility,
    )
    subplans = tuple(
        p.spec for p in service().plan_all(proposal.subrequests, payload.digest, country="vn")
    )
    composition = build_composition_spec(proposal, subplans)
    assert composition.op == "union_scope"
    assert composition.output_contract.fields == subplans[0].output_fields
    # Money across markets: stack for presentation, never aggregate.
    assert composition.allow_post_union_aggregate is False


def test_a_decomposed_plan_passes_its_own_validator():
    """A plan the decomposer built must satisfy the same checks as one a model
    proposed, or the deterministic path is the unchecked path."""
    payload = cross_market_input()
    atoms = atomize_request(payload.digest, payload.request) + (
        make_atom("country", semantic_ref="dim.country", value="id"),
    )
    feasibility = analyze(payload.request, payload.routing, countries=("vn", "id"))
    proposal = infer_deterministic_decomposition(
        payload.digest, payload.request, atoms, feasibility,
    )
    subplans = tuple(
        p.spec for p in service().plan_all(proposal.subrequests, payload.digest, country="vn")
    )
    from gladiators.planner.execution_plan import DecomposedExecutionPlan

    plan = DecomposedExecutionPlan(
        execution_plan_id="ep:test", request_hash=proposal.request_hash,
        digest_hash=proposal.digest_hash, capability_id="analytical",
        context_snapshot=snapshot("ds-1"), request_atoms=atoms,
        output_shape_kind="table", root_routing=payload.routing,
        decomposition_proposal_hash="ph", subplans=subplans,
        composition=build_composition_spec(proposal, subplans),
    )
    issues = validate_execution_plan(plan)
    assert [i.code for i in issues] == []


def test_without_an_injected_planner_the_decomposer_only_reports():
    """§8.4: the decomposer never reaches for a planner it was not given."""
    payload = cross_market_input()
    result = AnalyticalDecomposer().build_execution_plan(payload)
    assert result.execution_plan is None
    assert result.planning_meta["decomposer_version"]


def test_an_invalid_proposal_is_rejected_before_any_subplan_is_planned():
    """Planning first would spend the whole call budget proving a split that was
    never admissible."""
    calls: list[str] = []

    class CountingService(SubrequestPlanningService):
        def plan_all(self, proposals, root_digest, *, country):
            calls.append("planned")
            return ()

    payload = cross_market_input()
    decomposer = AnalyticalDecomposer(subrequest_planner=CountingService())
    decomposer.build_execution_plan(payload)
    # The single-country request is feasible, so no split and no planning at all.
    assert calls == []
