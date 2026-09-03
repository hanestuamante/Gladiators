"""AnalyticalDecomposer — ultimate solution §8.4 / §8.8.

Replaces ``OpenAnalyticalPlanner`` at the planning boundary.  Its job is narrow
and it matters that it stays narrow: prove whether one atomic plan can answer
the request, and if not, split the request and plan each part.  It does not
compile, execute, compose, or write an answer.

The input is a single typed object that has already been parsed, routed and
packed. §8.8 forbids the decomposer from re-parsing, re-routing or building its
own broad context, and the reason is drift: a component that can rebuild its own
inputs will eventually disagree with the state everything else was validated
against, and nothing will report it. So a mismatch between the input pieces is a
terminal ``decomposer_input_mismatch`` -- the decomposer never quietly repairs
its input to keep going.

Deterministic decomposition is tried before any model is asked. Two markets
compared, or a producer/consumer question, have exactly one sensible split and
inferring it costs nothing; asking a model to guess a shape we can derive adds a
failure mode and a call budget for no accuracy.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from .atoms import RequestAtom, atomize_request
from .execution_plan import (
    AtomicExecutionPlan,
    CompositeOutputContract,
    ScopePartition,
    SectionSpec,
    SideBySideSpec,
    UnionScopeSpec,
    DecomposedExecutionPlan,
    DecompositionProposal,
    ExecutionContextSnapshot,
    PlanningIssue,
    SideBySideProposal,
    SubrequestProposal,
    UnionScopeProposal,
)
from .decomposition_validator import validate_decomposition_proposal
from .feasibility import analyze

DECOMPOSER_VERSION = "decomposer.v1"

# §8.4 call budget. Exceeding it fails closed; §8.4 explicitly forbids falling
# back to the nearest macro, because a near-miss answer to a question that
# needed decomposition is a confidently wrong answer.
MAX_DECOMPOSITION_PROPOSAL_CALLS = 1
MAX_SUBPLANS = 4
MAX_TOTAL_PLANNER_CALLS = 9

DecomposerMode = Literal[
    "deterministic_atomic", "llm_atomic",
    "deterministic_decomposed", "llm_decomposed",
    "legacy_broad_atomic_plan",
]


class DecomposerInputMismatch(RuntimeError):
    """The input pieces disagree. Terminal by design (§8.8)."""

    code = "decomposer_input_mismatch"

    def __init__(self, detail: str):
        super().__init__(f"decomposer_input_mismatch: {detail}")
        self.detail = detail


class DecomposerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    normalized_question: str
    request: Any
    digest: Any
    routing: Any
    packed_context: Any
    context_snapshot: ExecutionContextSnapshot

    def verify(self) -> None:
        """Assert the pieces describe one request (§8.8).

        Each check below is a way two components could be validated against
        different state while every individual object looks well-formed.
        """
        digest_question = getattr(self.digest, "normalized_question", None)
        if digest_question and digest_question != self.normalized_question:
            raise DecomposerInputMismatch("normalized_question lệch giữa input và digest")

        packed = self.packed_context
        routing_hash = getattr(self.routing, "routing_hash", None)
        packed_routing = getattr(packed, "routing_hash", None)
        if packed_routing is not None and routing_hash and packed_routing != routing_hash:
            raise DecomposerInputMismatch("routing_hash lệch giữa routing và packed context")

        packed_dataset = getattr(packed, "dataset_version", None)
        if packed_dataset and packed_dataset != self.context_snapshot.dataset_version:
            raise DecomposerInputMismatch("dataset_version lệch giữa context và snapshot")

        gate_version = getattr(self.routing, "topic_gate_version", None)
        if gate_version and gate_version != self.context_snapshot.topic_gate_version:
            raise DecomposerInputMismatch("topic_gate_version lệch giữa routing và snapshot")


@dataclass(frozen=True)
class DecomposerResult:
    execution_plan: AtomicExecutionPlan | DecomposedExecutionPlan | None
    mode: DecomposerMode
    attempts: int = 0
    decomposition_attempts: int = 0
    subplan_attempts: dict[str, int] = field(default_factory=dict)
    planning_meta: dict[str, Any] = field(default_factory=dict)
    issues: tuple[PlanningIssue, ...] = ()


class DecomposerProtocol(Protocol):
    def build_execution_plan(self, decomposer_input: DecomposerInput) -> DecomposerResult: ...


# --- deterministic decomposition -----------------------------------------

def infer_deterministic_decomposition(
    digest, request, atoms: tuple[RequestAtom, ...], feasibility,
) -> DecompositionProposal | None:
    """Derive the split when the request has exactly one sensible one (§8.4).

    Returns ``None`` when nothing can be inferred -- that is the signal to ask a
    model, not a failure. Guessing here would be worse than asking, because a
    wrong deterministic split carries the authority of a rule.
    """
    if feasibility.feasible:
        return None

    countries = [atom for atom in atoms if atom.kind == "country"]

    # Same measurement, disjoint markets, incompatible units: this is exactly
    # union_scope, and there is no second reading of it.
    if "unit_incompatible" in feasibility.blockers and 2 <= len(countries) <= MAX_SUBPLANS:
        subrequests = []
        shared = tuple(atom.atom_id for atom in atoms if atom.shareable and atom.kind != "country")
        # The payload atoms are recorded once, not replicated per partition.
        # Duplicating them would double-count the requirement, and §8.5 only
        # permits country/date to be shared. That every partition computes the
        # same schema is asserted by the union spec itself, not by the atom set.
        payload = tuple(
            atom.atom_id for atom in atoms if not atom.shareable and atom.kind != "country"
        )
        for index, country in enumerate(countries):
            subrequests.append(SubrequestProposal(
                subplan_id=f"sp{index + 1}", request=request,
                covered_atom_ids=(country.atom_id,) + (payload if index == 0 else ()),
                shared_atom_ids=shared,
            ))
        return DecompositionProposal(
            request_hash=_request_hash(digest), digest_hash=_digest_hash(digest),
            request_atoms=atoms, subrequests=tuple(subrequests),
            composition=UnionScopeProposal(
                input_subplan_ids=tuple(s.subplan_id for s in subrequests),
                scope_ref="dim.country",
            ),
        )

    # Explicit compound parts: the request already says it is several questions.
    compound = [atom for atom in atoms if atom.kind == "compound_part"]
    if 2 <= len(compound) <= MAX_SUBPLANS:
        shared = tuple(atom.atom_id for atom in atoms if atom.shareable)
        subrequests = tuple(
            SubrequestProposal(
                subplan_id=f"sp{index + 1}", request=request,
                covered_atom_ids=(atom.atom_id,), shared_atom_ids=shared,
            )
            for index, atom in enumerate(compound)
        )
        return DecompositionProposal(
            request_hash=_request_hash(digest), digest_hash=_digest_hash(digest),
            request_atoms=atoms, subrequests=subrequests,
            composition=SideBySideProposal(
                input_subplan_ids=tuple(s.subplan_id for s in subrequests),
            ),
        )

    return None


def _proposal_hash(proposal) -> str:
    return hashlib.sha256(
        f"{proposal.request_hash}|{proposal.composition.op}|"
        f"{','.join(sorted(s.subplan_id for s in proposal.subrequests))}".encode("utf-8")
    ).hexdigest()[:16]


def build_composition_spec(proposal, subplans):
    """§8.4 step 7: derive the contract from the planned subplans.

    The output contract is *derived*, never restated. A hand-written schema that
    drifts from what the subplans actually produce is a mismatch nothing catches
    until the composition tries to line two frames up.
    """
    by_id = {spec.subplan_id: spec for spec in subplans}
    op = proposal.composition.op

    if op == "union_scope":
        # Every partition computes the same measurement, so the fields come from
        # one subplan and the schema-equality check at compose time enforces the
        # rest. Scope values are read back from each subrequest's own country
        # atoms rather than assumed from ordering.
        first = subplans[0]
        contract = CompositeOutputContract(
            presentation="single_frame", output_shape_kind="table",
            output_grain=first.plan.nodes[-1].output_grain,
            fields=first.output_fields,
            expected_cardinality=f"<={sum(1 for _ in subplans) * 10000}",
        )
        partitions = tuple(
            ScopePartition(
                subplan_id=sub.subplan_id,
                scope_values=_scope_values_of(proposal, sub.subplan_id),
            )
            for sub in subplans
        )
        return UnionScopeSpec(
            scope_ref=proposal.composition.scope_ref,
            partitions=partitions, dedupe_policy_id="one_row_per_listing",
            # Money from two markets may be stacked to look at, never averaged.
            allow_post_union_aggregate=all(
                f.aggregatable_across_scope for sub in subplans for f in sub.output_fields
            ),
            output_contract=contract,
        )

    contract = CompositeOutputContract(
        presentation="sections", output_shape_kind="comparison",
        output_grain=subplans[0].plan.nodes[-1].output_grain,
        expected_cardinality=str(len(subplans)),
    )
    return SideBySideSpec(
        sections=tuple(
            SectionSpec(
                section_id=f"sec{index + 1}", title_key=f"section.{sub.subplan_id}",
                subplan_id=sub.subplan_id, order=index,
            )
            for index, sub in enumerate(subplans)
        ),
        output_contract=contract,
    )


def _scope_values_of(proposal, subplan_id: str) -> tuple[str, ...]:
    by_atom = {atom.atom_id: atom for atom in proposal.request_atoms}
    for sub in proposal.subrequests:
        if sub.subplan_id != subplan_id:
            continue
        return tuple(
            str(by_atom[a].value) for a in sub.covered_atom_ids
            if a in by_atom and by_atom[a].kind == "country" and by_atom[a].value
        )
    return ()


def _digest_hash(digest) -> str:
    payload = getattr(digest, "model_dump", lambda **_: {})(mode="json")
    return hashlib.sha256(
        repr(sorted(payload.items())).encode("utf-8")
    ).hexdigest()[:16]


def _request_hash(digest) -> str:
    return _digest_hash(digest)


# --- the decomposer -------------------------------------------------------

class AnalyticalDecomposer:
    """§8.8 entry point. Proves atomic feasibility, then plans or splits."""

    def __init__(self, *, synthesizer=None, proposal_service=None,
                 subrequest_planner=None):
        """``subrequest_planner`` is injected: §8.4 forbids the decomposer from
        routing the root again, so the only component allowed to route is one it
        was handed, and only ever for a new subrequest."""
        self.synthesizer = synthesizer
        self.proposal_service = proposal_service
        self.subrequest_planner = subrequest_planner

    def build_execution_plan(self, decomposer_input: DecomposerInput) -> DecomposerResult:
        decomposer_input.verify()

        digest = decomposer_input.digest
        request = decomposer_input.request
        routing = decomposer_input.routing

        atoms = atomize_request(digest, request)
        countries = tuple(
            str(atom.value) for atom in atoms if atom.kind == "country" and atom.value
        )
        feasibility = analyze(request, routing, countries=countries)

        meta: dict[str, Any] = {
            "decomposer_version": DECOMPOSER_VERSION,
            "atom_count": len(atoms),
            "routing_mode": getattr(routing, "mode", None),
            "feasible": feasibility.feasible,
            "blockers": list(feasibility.blockers),
            "target_grain": feasibility.target_grain,
        }

        if feasibility.feasible:
            return DecomposerResult(
                execution_plan=None, mode="deterministic_atomic", attempts=0,
                planning_meta=meta | {"next_step": "atomic_plan_synthesis"},
            )

        proposal = infer_deterministic_decomposition(digest, request, atoms, feasibility)
        if proposal is not None:
            proposal_meta = meta | {
                "proposal_op": proposal.composition.op,
                "subplan_count": len(proposal.subrequests),
                "proposal_source": "deterministic",
            }
            # §8.5: grammar is checked before any subplan is planned. Planning
            # first would spend the whole call budget proving a split that was
            # never admissible.
            issues = validate_decomposition_proposal(proposal)
            if issues:
                return DecomposerResult(
                    execution_plan=None, mode="deterministic_decomposed",
                    planning_meta=proposal_meta | {"proposal_valid": False},
                    issues=issues,
                )
            if self.subrequest_planner is None:
                return DecomposerResult(
                    execution_plan=None, mode="deterministic_decomposed",
                    planning_meta=proposal_meta | {
                        "proposal_valid": True, "next_step": "subrequest_planning",
                    },
                )
            return self._plan_decomposed(
                proposal, decomposer_input, atoms, countries, proposal_meta,
            )

        # Nothing could be derived. Whether a model is asked is the caller's
        # decision via the feature gate; the decomposer reports rather than
        # reaching for an LLM on its own.
        return DecomposerResult(
            execution_plan=None, mode="deterministic_atomic", attempts=0,
            planning_meta=meta | {
                "next_step": "llm_decomposition_proposal",
                "proposal_source": "none",
            },
        )

    def _plan_decomposed(
        self, proposal, decomposer_input, atoms, countries, meta,
    ) -> DecomposerResult:
        """§8.4 steps 5-8: plan each subrequest, then build the composition."""
        country = countries[0] if countries else ""
        try:
            planned = self.subrequest_planner.plan_all(
                proposal.subrequests, decomposer_input.digest, country=country,
            )
        except Exception as error:  # noqa: BLE001 - reported, never a crash
            return DecomposerResult(
                execution_plan=None, mode="deterministic_decomposed",
                planning_meta=meta | {
                    "proposal_valid": True,
                    "subplan_error": f"{type(error).__name__}: {error}"[:200],
                },
            )

        subplans = tuple(result.spec for result in planned)
        composition = build_composition_spec(proposal, subplans)
        plan = DecomposedExecutionPlan(
            execution_plan_id=f"ep:{_digest_hash(decomposer_input.digest)}",
            request_hash=proposal.request_hash, digest_hash=proposal.digest_hash,
            capability_id="analytical", context_snapshot=decomposer_input.context_snapshot,
            request_atoms=atoms,
            output_shape_kind=composition.output_contract.output_shape_kind,
            root_routing=decomposer_input.routing,
            decomposition_proposal_hash=_proposal_hash(proposal),
            subplans=subplans, composition=composition,
        )
        return DecomposerResult(
            execution_plan=plan, mode="deterministic_decomposed",
            attempts=sum(r.attempts for r in planned),
            subplan_attempts={r.spec.subplan_id: r.attempts for r in planned},
            planning_meta=meta | {
                "proposal_valid": True,
                "subplan_sources": {r.spec.subplan_id: r.source for r in planned},
                "composition_op": composition.op,
            },
        )

    def feasibility_for(self, decomposer_input: DecomposerInput):
        decomposer_input.verify()
        atoms = atomize_request(decomposer_input.digest, decomposer_input.request)
        countries = tuple(
            str(atom.value) for atom in atoms if atom.kind == "country" and atom.value
        )
        return analyze(decomposer_input.request, decomposer_input.routing, countries=countries)
