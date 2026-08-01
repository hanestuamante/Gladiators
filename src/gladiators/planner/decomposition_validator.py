"""Decomposition validation and feature gate — ultimate solution §8.5 / §8.11.

Two validation phases that §8.5 forbids mixing, for a reason worth restating:
the exact gate key includes each subrequest's topic signature, and that
signature only exists *after* the subrequest has been routed.  So the proposal
stage can only check grammar -- atoms, operator, arity -- and the execution
stage checks the exact canonical signature and artifact hashes.  Collapsing them
would mean either gating on a key that does not exist yet, or admitting a
proposal on a key computed from something other than what will run.

The gate itself is deliberately unhelpful in one specific way: **an absent
signature is never widened to the nearest neighbour.**  A composition certified
for two subplans says nothing about the same operator over three, and treating
it as evidence is how an untested shape reaches production wearing another
shape's approval.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..domain.relations import RELATIONS
from .atoms import RequestAtom, coverage_gap
from .execution_plan import (
    DecompositionProposal,
    FilterThenMeasureSpec,
    IssueParam,
    JoinOnRelationSpec,
    PlanningFailure,
    PlanningIssue,
    SideBySideSpec,
    UnionScopeSpec,
    composition_arity,
)

DECOMPOSITION_GATE_VERSION = "decomp-gate.v1"
GATE_SCHEMA_VERSION = "decomposition-gate.v1"

# Only scope atoms may be shared between subrequests. Anything else appearing in
# two subplans means the same requirement is being measured twice and composed
# as if it were two findings.
SHAREABLE_ALLOW_LIST: frozenset[str] = frozenset({"country", "date"})

RELEASE_OPS: frozenset[str] = frozenset({
    "side_by_side", "union_scope", "join_on_relation", "filter_then_measure",
})


def _issue(category: str, code: str, message_key: str, *,
           path: tuple = (), params: dict[str, Any] | None = None,
           repairable: bool = False) -> PlanningIssue:
    return PlanningIssue(
        category=category, code=code, message_key=message_key, path=path,
        params=tuple(IssueParam(name=k, value=v) for k, v in sorted((params or {}).items())),
        repairable=repairable,
    )


# --- phase 1: proposal grammar -------------------------------------------

def validate_decomposition_proposal(
    proposal: DecompositionProposal,
) -> tuple[PlanningIssue, ...]:
    """Grammar only. The exact topic signature does not exist yet (§8.5)."""
    issues: list[PlanningIssue] = []

    ids = [sub.subplan_id for sub in proposal.subrequests]
    if len(ids) != len(set(ids)):
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        issues.append(_issue("decomposition", "SUBPLAN_ID_DUPLICATE",
                             "decomposition.subplan_id_duplicate",
                             params={"ids": ",".join(duplicates)}))

    if proposal.composition.op not in RELEASE_OPS:
        issues.append(_issue("decomposition", "SUBPLAN_ARITY_INVALID",
                             "decomposition.op_not_in_release",
                             params={"op": str(proposal.composition.op)}))

    referenced = _proposal_subplan_ids(proposal.composition)
    unknown_ids = sorted(referenced - set(ids))
    if unknown_ids:
        issues.append(_issue("decomposition", "SUBPLAN_ARITY_INVALID",
                             "decomposition.composition_references_unknown_subplan",
                             params={"ids": ",".join(unknown_ids)}))
    elif len(referenced) != len(ids):
        # Every subrequest must take part; an orphan subplan is work whose
        # result reaches no answer.
        issues.append(_issue("decomposition", "SUBPLAN_ARITY_INVALID",
                             "decomposition.arity_mismatch",
                             params={"arity": len(referenced), "subplans": len(ids)}))

    covered: set[str] = set()
    for sub in proposal.subrequests:
        covered |= set(sub.covered_atom_ids)
        bad_shares = [
            atom_id for atom_id in sub.shared_atom_ids
            if _kind_of(proposal.request_atoms, atom_id) not in SHAREABLE_ALLOW_LIST
        ]
        if bad_shares:
            issues.append(_issue("decomposition", "ATOM_COVERAGE_MISMATCH",
                                 "decomposition.shared_atom_not_allowed",
                                 path=("subrequests", sub.subplan_id),
                                 params={"ids": ",".join(sorted(bad_shares))}))
        covered |= set(sub.shared_atom_ids)

    uncovered, unknown = coverage_gap(proposal.request_atoms, frozenset(covered))
    if uncovered:
        issues.append(_issue("decomposition", "ATOM_COVERAGE_MISMATCH",
                             "decomposition.atoms_not_covered",
                             params={"ids": ",".join(sorted(uncovered))}))
    if unknown:
        issues.append(_issue("decomposition", "UNKNOWN_ATOM",
                             "decomposition.unknown_atom",
                             params={"ids": ",".join(sorted(unknown))}))

    # A non-shareable atom claimed by two subrequests is double-counted.
    claimed: dict[str, str] = {}
    for sub in proposal.subrequests:
        for atom_id in sub.covered_atom_ids:
            if _kind_of(proposal.request_atoms, atom_id) in SHAREABLE_ALLOW_LIST:
                continue
            if atom_id in claimed and claimed[atom_id] != sub.subplan_id:
                issues.append(_issue("decomposition", "ATOM_COVERAGE_MISMATCH",
                                     "decomposition.atom_claimed_twice",
                                     params={"atom_id": atom_id}))
            claimed[atom_id] = sub.subplan_id

    return tuple(issues)


def _kind_of(atoms: tuple[RequestAtom, ...], atom_id: str) -> str | None:
    for atom in atoms:
        if atom.atom_id == atom_id:
            return atom.kind
    return None


def _proposal_subplan_ids(composition) -> set[str]:
    ids = getattr(composition, "input_subplan_ids", None)
    if ids is not None:
        return set(ids)
    if hasattr(composition, "left_subplan_id"):
        return {composition.left_subplan_id, composition.right_subplan_id}
    return {composition.producer_subplan_id, composition.consumer_subplan_id}


# --- phase 2: execution plan ---------------------------------------------

def validate_execution_plan(plan, *, gate: "DecompositionGate | None" = None,
                            mode: str = "enforce") -> tuple[PlanningIssue, ...]:
    """Full check before anything executes (§8.5)."""
    issues: list[PlanningIssue] = []
    if getattr(plan, "kind", "atomic") == "atomic":
        return tuple(issues)

    pinned = plan.context_snapshot.dataset_version
    for sub in plan.subplans:
        if sub.dataset_version != pinned:
            issues.append(_issue("atomic_plan", "DATASET_SNAPSHOT_MISMATCH",
                                 "plan.dataset_version_mismatch",
                                 path=("subplans", sub.subplan_id)))
        if not sub.context_hash or not sub.topic_gate_version:
            issues.append(_issue("atomic_plan", "PLAN_INVALID",
                                 "plan.missing_routing_provenance",
                                 path=("subplans", sub.subplan_id)))
        if sub.plan.subplan_count != 1:
            issues.append(_issue("atomic_plan", "PLAN_INVALID",
                                 "plan.subplan_not_atomic",
                                 path=("subplans", sub.subplan_id)))

    covered = {a for sub in plan.subplans for a in sub.covered_atom_ids}
    covered |= {a for sub in plan.subplans for a in sub.shared_atom_ids}
    uncovered, unknown = coverage_gap(plan.request_atoms, frozenset(covered))
    if uncovered:
        issues.append(_issue("composition", "ATOM_COVERAGE_MISMATCH",
                             "plan.atoms_not_covered",
                             params={"ids": ",".join(sorted(uncovered))}))
    if unknown:
        issues.append(_issue("composition", "UNKNOWN_ATOM", "plan.unknown_atom",
                             params={"ids": ",".join(sorted(unknown))}))

    issues.extend(_validate_composition(plan))

    if plan.partial_policy == "explicit_partial":
        # Only a root digest that asked for partial answers may get one; a
        # planner deciding this for itself turns a failure into a half answer.
        issues.append(_issue("composition", "PARTIAL_NOT_ALLOWED",
                             "plan.partial_requires_root_optin"))

    if gate is not None:
        signature = gate_signature(plan)
        verdict = gate.check(signature)
        if not verdict.enabled and mode == "enforce":
            issues.append(_issue("composition", "GATE_SIGNATURE_DISABLED",
                                 "plan.gate_signature_disabled",
                                 params={"signature": signature, "reason": verdict.reason}))
    return tuple(issues)


def _validate_composition(plan) -> list[PlanningIssue]:
    issues: list[PlanningIssue] = []
    composition = plan.composition
    by_id = {sub.subplan_id: sub for sub in plan.subplans}

    if composition_arity(composition) != len(plan.subplans):
        issues.append(_issue("composition", "SUBPLAN_ARITY_INVALID",
                             "composition.arity_mismatch"))

    if isinstance(composition, UnionScopeSpec):
        # Units must match across a union: the whole point is that the parts are
        # the same measurement over disjoint scope.
        units = {f.unit for sub in plan.subplans for f in sub.output_fields}
        if len(units) > 1:
            issues.append(_issue("composition", "UNIT_MISMATCH",
                                 "composition.union_mixed_units",
                                 params={"units": ",".join(sorted(units))}))
        if composition.allow_post_union_aggregate:
            non_aggregatable = sorted({
                f.name for sub in plan.subplans for f in sub.output_fields
                if not f.aggregatable_across_scope
            })
            if non_aggregatable:
                issues.append(_issue("composition", "UNIT_MISMATCH",
                                     "composition.aggregate_across_scope_forbidden",
                                     params={"fields": ",".join(non_aggregatable)}))

    if isinstance(composition, JoinOnRelationSpec):
        spec = RELATIONS.get(composition.relation_id)
        if spec is None:
            issues.append(_issue("composition", "RELATION_INVALID",
                                 "composition.unknown_relation",
                                 params={"relation": composition.relation_id}))
        elif spec.fanout_effect != "none" and not composition.dedupe_policy_id:
            issues.append(_issue("composition", "CARDINALITY_VIOLATION",
                                 "composition.join_fanout_without_dedupe",
                                 params={"relation": composition.relation_id}))

    if isinstance(composition, FilterThenMeasureSpec):
        producer = by_id.get(composition.producer_subplan_id)
        if producer is not None:
            field_refs = {f.semantic_ref for f in producer.output_fields}
            if composition.deferred_predicate.source_field_ref not in {
                f.name for f in producer.output_fields
            } | field_refs:
                issues.append(_issue("composition", "OUTPUT_SCHEMA_MISMATCH",
                                     "composition.deferred_source_field_absent",
                                     params={"field": composition.deferred_predicate.source_field_ref}))

    if isinstance(composition, SideBySideSpec):
        orders = [section.order for section in composition.sections]
        if len(set(orders)) != len(orders):
            issues.append(_issue("composition", "OUTPUT_SCHEMA_MISMATCH",
                                 "composition.section_order_duplicate"))
    return issues


# --- gate ----------------------------------------------------------------

def gate_signature(plan) -> str:
    """Canonical key: op, arity, output shape, per-subplan topic signature.

    §8.11: symmetric operators sort their subplan signatures but never collapse
    duplicates -- two subplans on the same topic is a different shape from one,
    and collapsing would enable the wrong case. Ordered operators keep their
    direction, because producer and consumer are not interchangeable.
    """
    composition = plan.composition
    op = composition.op
    by_id = {sub.subplan_id: sub for sub in plan.subplans}

    def topic_of(subplan_id: str) -> str:
        sub = by_id.get(subplan_id)
        if sub is None:
            return "?"
        domains = sub.routing.domain_topic_ids or ("CORE",)
        return "+".join(domains)

    if isinstance(composition, SideBySideSpec):
        ordered = [s.subplan_id for s in sorted(composition.sections, key=lambda x: x.order)]
        signatures = sorted(topic_of(i) for i in ordered)
        shape = composition.output_contract.presentation
    elif isinstance(composition, UnionScopeSpec):
        signatures = sorted(topic_of(p.subplan_id) for p in composition.partitions)
        shape = composition.output_contract.presentation
    elif isinstance(composition, JoinOnRelationSpec):
        signatures = [topic_of(composition.left_subplan_id),
                      topic_of(composition.right_subplan_id)]
        shape = f"{composition.output_contract.presentation}:{composition.relation_id}"
    else:
        signatures = [topic_of(composition.producer_subplan_id),
                      topic_of(composition.consumer_subplan_id)]
        shape = composition.output_contract.presentation

    return (
        f"op={op}|arity={composition_arity(composition)}"
        f"|shape={shape}|subplans={';'.join(signatures)}"
    )


class GateVerdict:
    __slots__ = ("enabled", "reason", "signature")

    def __init__(self, enabled: bool, reason: str, signature: str):
        self.enabled = enabled
        self.reason = reason
        self.signature = signature


class DecompositionGate:
    """Reads ``eval/decomposition_gate.json`` and answers one question honestly.

    Closed by default. A missing artifact, a hash mismatch against the running
    registries, or an unlisted signature all mean *not enabled* -- never
    "probably fine".
    """

    def __init__(self, artifact: dict | None = None, *, runtime_hashes: dict | None = None):
        self.artifact = artifact or {}
        self.runtime_hashes = runtime_hashes or {}

    @classmethod
    def from_path(cls, path: str | Path, **kwargs) -> "DecompositionGate":
        file = Path(path)
        if not file.exists():
            return cls({}, **kwargs)
        try:
            return cls(json.loads(file.read_text(encoding="utf-8")), **kwargs)
        except json.JSONDecodeError:
            return cls({}, **kwargs)

    def check(self, signature: str) -> GateVerdict:
        if not self.artifact:
            return GateVerdict(False, "artifact_missing", signature)
        if self.artifact.get("schema_version") != GATE_SCHEMA_VERSION:
            return GateVerdict(False, "schema_version_mismatch", signature)

        declared = self.artifact.get("source_hashes", {}) or {}
        for name, expected in self.runtime_hashes.items():
            if name in declared and declared[name] != expected:
                return GateVerdict(False, f"hash_mismatch:{name}", signature)

        entry = (self.artifact.get("signatures") or {}).get(signature)
        if entry is None:
            # Never widened to a neighbouring signature: a composition certified
            # for two subplans is no evidence about three.
            return GateVerdict(False, "signature_not_certified", signature)
        if not entry.get("enabled"):
            return GateVerdict(False, str(entry.get("reason") or "disabled"), signature)
        if not entry.get("reviewer") or not entry.get("approved_at"):
            return GateVerdict(False, "missing_signoff", signature)
        return GateVerdict(True, str(entry.get("reason") or "acceptance_passed"), signature)


def failure_from(issues: tuple[PlanningIssue, ...], terminal_code: str) -> PlanningFailure:
    return PlanningFailure.from_issues(terminal_code, issues)


def artifact_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
