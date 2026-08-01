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
    DecomposedExecutionPlan,
    DecompositionProposal,
    ExecutionContextSnapshot,
    PlanningIssue,
    SideBySideProposal,
    SubrequestProposal,
    UnionScopeProposal,
)
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
            return DecomposerResult(
                execution_plan=None, mode="deterministic_decomposed",
                attempts=0, decomposition_attempts=0,
                planning_meta=meta | {
                    "proposal_op": proposal.composition.op,
                    "subplan_count": len(proposal.subrequests),
                    "proposal_source": "deterministic",
                },
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

    def feasibility_for(self, decomposer_input: DecomposerInput):
        decomposer_input.verify()
        atoms = atomize_request(decomposer_input.digest, decomposer_input.request)
        countries = tuple(
            str(atom.value) for atom in atoms if atom.kind == "country" and atom.value
        )
        return analyze(decomposer_input.request, decomposer_input.routing, countries=countries)
