"""Decomposition validation and gate — ultimate solution §8.5 / §8.11.

The gate is closed by default and these tests mostly prove it stays closed:
a missing artifact, a stale hash, an unlisted signature and a missing sign-off
must all read as *not enabled*, because every one of them is a case where
nobody has actually checked the shape that is about to run.
"""
from __future__ import annotations

import pytest

from gladiators.planner.atoms import make_atom
from gladiators.planner.decomposition_validator import (
    GATE_SCHEMA_VERSION,
    DecompositionGate,
    gate_signature,
    validate_decomposition_proposal,
    validate_execution_plan,
)
from gladiators.planner.execution_plan import (
    DecompositionProposal,
    SideBySideProposal,
    SubrequestProposal,
    UnionScopeProposal,
)
from tests.test_execution_plan import (  # reuse the sealed fixtures
    contract,
    decomposed,
    side_by_side,
    subplan,
)

ATOM_A = make_atom("measure", semantic_ref="measure.price")
ATOM_B = make_atom("measure", semantic_ref="measure.rating")
ATOM_VN = make_atom("country", semantic_ref="dim.country", value="vn")


def proposal(**overrides) -> DecompositionProposal:
    base = dict(
        request_hash="rh", digest_hash="dh",
        request_atoms=(ATOM_A, ATOM_B, ATOM_VN),
        subrequests=(
            SubrequestProposal(subplan_id="s1", request=None,
                               covered_atom_ids=(ATOM_A.atom_id,),
                               shared_atom_ids=(ATOM_VN.atom_id,)),
            SubrequestProposal(subplan_id="s2", request=None,
                               covered_atom_ids=(ATOM_B.atom_id,),
                               shared_atom_ids=(ATOM_VN.atom_id,)),
        ),
        composition=SideBySideProposal(input_subplan_ids=("s1", "s2")),
    )
    base.update(overrides)
    return DecompositionProposal(**base)


def codes(issues) -> set[str]:
    return {issue.code for issue in issues}


# --- phase 1: proposal grammar -------------------------------------------

def test_a_well_formed_proposal_has_no_issues():
    assert validate_decomposition_proposal(proposal()) == ()


def test_uncovered_atom_is_caught_before_any_planning():
    """The whole point: a dropped requirement is a set difference, not a hunch."""
    thin = proposal(subrequests=(
        SubrequestProposal(subplan_id="s1", request=None,
                           covered_atom_ids=(ATOM_A.atom_id,)),
        SubrequestProposal(subplan_id="s2", request=None,
                           covered_atom_ids=(ATOM_A.atom_id,)),
    ))
    assert "ATOM_COVERAGE_MISMATCH" in codes(validate_decomposition_proposal(thin))


def test_invented_atom_is_rejected():
    bogus = proposal(subrequests=(
        SubrequestProposal(subplan_id="s1", request=None,
                           covered_atom_ids=(ATOM_A.atom_id, "mea-notreal")),
        SubrequestProposal(subplan_id="s2", request=None,
                           covered_atom_ids=(ATOM_B.atom_id, ATOM_VN.atom_id)),
    ))
    assert "UNKNOWN_ATOM" in codes(validate_decomposition_proposal(bogus))


def test_only_scope_atoms_may_be_shared():
    """A measure in two subrequests is one requirement measured twice and then
    composed as if it were two findings."""
    bad = proposal(subrequests=(
        SubrequestProposal(subplan_id="s1", request=None,
                           covered_atom_ids=(ATOM_A.atom_id, ATOM_VN.atom_id),
                           shared_atom_ids=(ATOM_B.atom_id,)),
        SubrequestProposal(subplan_id="s2", request=None,
                           covered_atom_ids=(ATOM_B.atom_id,)),
    ))
    assert "ATOM_COVERAGE_MISMATCH" in codes(validate_decomposition_proposal(bad))


def test_non_shareable_atom_claimed_twice_is_caught():
    double = proposal(subrequests=(
        SubrequestProposal(subplan_id="s1", request=None,
                           covered_atom_ids=(ATOM_A.atom_id, ATOM_VN.atom_id)),
        SubrequestProposal(subplan_id="s2", request=None,
                           covered_atom_ids=(ATOM_A.atom_id, ATOM_B.atom_id)),
    ))
    assert "ATOM_COVERAGE_MISMATCH" in codes(validate_decomposition_proposal(double))


def test_duplicate_subplan_ids_are_caught():
    duplicated = proposal(subrequests=(
        SubrequestProposal(subplan_id="s1", request=None,
                           covered_atom_ids=(ATOM_A.atom_id, ATOM_VN.atom_id)),
        SubrequestProposal(subplan_id="s1", request=None,
                           covered_atom_ids=(ATOM_B.atom_id,)),
    ))
    assert "SUBPLAN_ID_DUPLICATE" in codes(validate_decomposition_proposal(duplicated))


def test_composition_referencing_an_unknown_subplan_is_caught():
    orphaned = proposal(composition=SideBySideProposal(input_subplan_ids=("s1", "s9")))
    assert "SUBPLAN_ARITY_INVALID" in codes(validate_decomposition_proposal(orphaned))


def test_proposal_stage_does_not_evaluate_the_exact_gate_signature():
    """§8.5: the signature needs each subrequest's route, which does not exist
    yet. Gating here would gate on a key computed from something else."""
    assert "GATE_SIGNATURE_DISABLED" not in codes(validate_decomposition_proposal(proposal()))


# --- phase 2: execution plan ---------------------------------------------

def test_valid_plan_passes_without_a_gate():
    plan = decomposed(request_atoms=(ATOM_A, ATOM_B))
    subplans = (
        subplan("s1", atom_ids=(ATOM_A.atom_id,)),
        subplan("s2", atom_ids=(ATOM_B.atom_id,)),
    )
    plan = decomposed(request_atoms=(ATOM_A, ATOM_B), subplans=subplans)
    assert validate_execution_plan(plan) == ()


def test_atom_dropped_between_proposal_and_plan_is_caught():
    subplans = (subplan("s1", atom_ids=(ATOM_A.atom_id,)),
                subplan("s2", atom_ids=(ATOM_A.atom_id,)))
    plan = decomposed(request_atoms=(ATOM_A, ATOM_B), subplans=subplans)
    assert "ATOM_COVERAGE_MISMATCH" in codes(validate_execution_plan(plan))


def test_explicit_partial_requires_root_opt_in():
    """A planner deciding this for itself turns a failure into a half answer."""
    plan = decomposed(
        request_atoms=(ATOM_A, ATOM_B),
        subplans=(subplan("s1", atom_ids=(ATOM_A.atom_id,)),
                  subplan("s2", atom_ids=(ATOM_B.atom_id,))),
        partial_policy="explicit_partial",
    )
    assert "PARTIAL_NOT_ALLOWED" in codes(validate_execution_plan(plan))


def test_atomic_plan_needs_no_composition_validation():
    from gladiators.planner.execution_plan import AtomicExecutionPlan
    from tests.test_execution_plan import FIELD, logical_plan, snapshot
    atomic = AtomicExecutionPlan(
        execution_plan_id="ep", request_hash="r", digest_hash="d", capability_id="c",
        context_snapshot=snapshot(), request_atom_ids=(ATOM_A.atom_id,),
        output_shape_kind="scalar", output_fields=(FIELD,),
        planning_source="macro", plan=logical_plan(),
    )
    assert validate_execution_plan(atomic) == ()


# --- gate signature -------------------------------------------------------

def test_signature_keeps_subplan_multiplicity():
    """§8.11: two subplans on one topic is a different shape from one, so
    duplicates must not collapse."""
    plan = decomposed(
        request_atoms=(ATOM_A, ATOM_B),
        subplans=(subplan("s1", atom_ids=(ATOM_A.atom_id,)),
                  subplan("s2", atom_ids=(ATOM_B.atom_id,))),
    )
    signature = gate_signature(plan)
    assert "arity=2" in signature
    assert signature.count(";") == 1


def test_signature_is_stable_for_symmetric_operator_ordering():
    a = decomposed(request_atoms=(ATOM_A, ATOM_B),
                   subplans=(subplan("s1", atom_ids=(ATOM_A.atom_id,)),
                             subplan("s2", atom_ids=(ATOM_B.atom_id,))),
                   composition=side_by_side(("s1", "s2")))
    b = decomposed(request_atoms=(ATOM_A, ATOM_B),
                   subplans=(subplan("s1", atom_ids=(ATOM_A.atom_id,)),
                             subplan("s2", atom_ids=(ATOM_B.atom_id,))),
                   composition=side_by_side(("s2", "s1")))
    assert gate_signature(a) == gate_signature(b)


# --- the gate stays closed ------------------------------------------------

def plan_for_gate():
    return decomposed(
        request_atoms=(ATOM_A, ATOM_B),
        subplans=(subplan("s1", atom_ids=(ATOM_A.atom_id,)),
                  subplan("s2", atom_ids=(ATOM_B.atom_id,))),
    )


def enabled_artifact(signature: str, **entry) -> dict:
    base = {"enabled": True, "reason": "acceptance_passed",
            "reviewer": "reviewer-1", "approved_at": "2026-07-30"}
    base.update(entry)
    return {
        "schema_version": GATE_SCHEMA_VERSION,
        "source_hashes": {"topics": "t1"},
        "signatures": {signature: base},
    }


def test_missing_artifact_means_not_enabled():
    plan = plan_for_gate()
    assert not DecompositionGate().check(gate_signature(plan)).enabled


def test_unlisted_signature_is_never_widened_to_a_neighbour():
    """A composition certified for two subplans is no evidence about three."""
    plan = plan_for_gate()
    gate = DecompositionGate(enabled_artifact("op=side_by_side|arity=3|shape=sections|subplans=T1;T1;T1"))
    verdict = gate.check(gate_signature(plan))
    assert not verdict.enabled
    assert verdict.reason == "signature_not_certified"


def test_hash_mismatch_closes_the_gate():
    plan = plan_for_gate()
    gate = DecompositionGate(enabled_artifact(gate_signature(plan)),
                             runtime_hashes={"topics": "t2"})
    verdict = gate.check(gate_signature(plan))
    assert not verdict.enabled
    assert verdict.reason == "hash_mismatch:topics"


def test_signature_without_signoff_is_not_enabled():
    plan = plan_for_gate()
    gate = DecompositionGate(enabled_artifact(gate_signature(plan), reviewer=""))
    assert gate.check(gate_signature(plan)).reason == "missing_signoff"


def test_fully_signed_off_signature_is_enabled():
    plan = plan_for_gate()
    gate = DecompositionGate(enabled_artifact(gate_signature(plan)),
                             runtime_hashes={"topics": "t1"})
    assert gate.check(gate_signature(plan)).enabled


def test_enforce_mode_blocks_an_uncertified_plan():
    plan = plan_for_gate()
    issues = validate_execution_plan(plan, gate=DecompositionGate(), mode="enforce")
    assert "GATE_SIGNATURE_DISABLED" in codes(issues)


def test_shadow_mode_records_but_does_not_block():
    """§8.5: shadow writes a verdict and absolutely does not execute."""
    plan = plan_for_gate()
    issues = validate_execution_plan(plan, gate=DecompositionGate(), mode="shadow")
    assert "GATE_SIGNATURE_DISABLED" not in codes(issues)


def test_gate_from_missing_path_is_closed(tmp_path):
    gate = DecompositionGate.from_path(tmp_path / "nope.json")
    assert not gate.check("op=x|arity=2|shape=sections|subplans=T1;T2").enabled
