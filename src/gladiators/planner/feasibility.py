"""AtomicFeasibilityAnalyzer — ultimate solution §8.3.

Answers one question before any planning happens: can a single atomic plan
actually carry this request?

The rule §8.3 is emphatic about is the one *not* to use: "two topics means
decompose". Two topics routinely share one valid plan -- voucher rate by
official shop is a join and an aggregate, not two questions. Decomposing it
would produce two correct halves and then need a composition to say something
their join already says, at four times the cost and with a new class of
composition bug.

So decomposition is driven by typed blockers, and every blocker names a concrete
thing an atomic plan cannot do: refs that no certified relation connects, more
than one defensible target grain, incompatible units, fanout with no dedupe
policy, an output shape the IR cannot express, or hard context that will not fit.

``ambiguous_target_grain`` is the subtle one. When several grains are defensible
and the registry has no deterministic priority, the analyzer refuses rather than
picking by path cost or alphabetical order -- a silently chosen grain is a
silently different question.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..domain import topics
from ..domain.catalog import CATALOG
from ..domain.relations import RELATIONS, find_path

AtomicBlocker = Literal[
    "disconnected_refs", "no_single_target_grain", "ambiguous_target_grain",
    "unit_incompatible", "fanout_without_dedupe",
    "output_not_representable", "context_budget_unsatisfied",
]

# Shapes the atomic IR can express. A composition is required for anything else.
_REPRESENTABLE_SHAPES = frozenset({"scalar", "table", "ranking", "comparison", "list"})

# Units that may not be arithmetically combined across a scope boundary.
_SCOPE_BOUND_UNITS = frozenset({"local_currency"})


class AtomicFeasibility(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    feasible: bool
    target_grain: str | None = None
    required_relations: tuple[str, ...] = ()
    candidate_target_grains: tuple[str, ...] = ()
    candidate_relation_paths: tuple[str, ...] = ()
    blockers: tuple[AtomicBlocker, ...] = ()


def _sql_refs(refs: tuple[str, ...]) -> tuple[str, ...]:
    non_sql = topics.non_sql_refs()
    return tuple(ref for ref in refs if ref in CATALOG and ref not in non_sql)


def _grain_of(ref: str) -> str | None:
    obj = CATALOG.get(ref)
    return getattr(obj, "grain", None) if obj else None


def _entity_of(ref: str) -> str:
    """Anchor entity a ref lives on, for connectivity checking."""
    for card in topics.TOPICS.values():
        if ref in card.owner_refs and card.anchor_entities:
            return card.anchor_entities[0]
    return "ProductListing"


def analyze(
    request,
    routing,
    *,
    countries: tuple[str, ...] = (),
    context_fits: bool = True,
    grain_priority: dict[str, int] | None = None,
) -> AtomicFeasibility:
    refs = _sql_refs(routing.resolved_refs)
    blockers: list[AtomicBlocker] = []

    # -- connectivity: every ref must be reachable from a shared anchor.
    relations: list[str] = list(routing.required_relation_ids)
    disconnected = False
    for ref in refs:
        entity = _entity_of(ref)
        if entity == "ProductListing":
            continue
        path = find_path("ProductListing", entity)
        if path is None:
            disconnected = True
            continue
        relations.extend(spec.name for spec in path)
    if disconnected:
        blockers.append("disconnected_refs")

    # -- fanout must carry a dedupe policy. Aggregating a fanned-out join
    #    double-counts, and the count looks perfectly plausible.
    for name in dict.fromkeys(relations):
        spec = RELATIONS.get(name)
        if spec and spec.fanout_effect != "none" and not spec.dedupe_strategy:
            blockers.append("fanout_without_dedupe")
            break

    # -- target grain.
    grains = tuple(dict.fromkeys(g for g in (_grain_of(ref) for ref in refs) if g))
    target: str | None = None
    if not grains:
        if refs:
            blockers.append("no_single_target_grain")
    elif len(grains) == 1:
        target = grains[0]
    else:
        priority = grain_priority or _default_grain_priority()
        ranked = sorted(grains, key=lambda g: priority.get(g, 10**6))
        best = priority.get(ranked[0], 10**6)
        if best == 10**6 or (len(ranked) > 1 and priority.get(ranked[1], 10**6) == best):
            # No deterministic winner. Choosing by path cost or name order here
            # would answer a different question without saying so.
            blockers.append("ambiguous_target_grain")
        else:
            target = ranked[0]

    # -- units. Currency may not be combined across markets.
    units = {getattr(CATALOG[ref], "unit", None) for ref in refs}
    if len(countries) > 1 and units & _SCOPE_BOUND_UNITS:
        blockers.append("unit_incompatible")

    shape = str(getattr(request, "requested_output_shape", "") or "")
    if shape and shape not in _REPRESENTABLE_SHAPES:
        blockers.append("output_not_representable")

    if not context_fits:
        blockers.append("context_budget_unsatisfied")

    blockers = list(dict.fromkeys(blockers))
    return AtomicFeasibility(
        feasible=not blockers,
        target_grain=target if not blockers else None,
        required_relations=tuple(dict.fromkeys(relations)),
        candidate_target_grains=grains,
        candidate_relation_paths=tuple(dict.fromkeys(relations)),
        blockers=tuple(blockers),
    )


def _default_grain_priority() -> dict[str, int]:
    """Registry-declared precedence when refs disagree about grain.

    Finer grains win: a plan at listing_snapshot can aggregate up to listing,
    while the reverse invents detail that was never measured.
    """
    return {
        "listing_snapshot": 0,
        "listing": 1,
        "listing_snapshot_category": 2,
        "listing_snapshot_voucher": 3,
        "shop": 4,
        "pair": 5,
    }
