"""Prompt assembly — ultimate solution §6.6.

Turns a route into the typed items the packer weighs.  The order below is the
spec's, and it is an order of *decreasing consequence*: anything that changes
whether the answer is correct is built first and marked undroppable, so the
budget can only ever eat things that change how well the answer is phrased.

The single rule worth stating twice: **required refs are never droppable, even
when their owning topic was not selected.**  A ref the request bound but the
route did not cover would otherwise vanish between the two, and the planner
would produce a confident plan for a question it was shown two-thirds of.
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from ..domain import topics
from ..domain.invariants import INVARIANTS, hard_invariants
from ..domain.relations import RELATIONS
from .context_packer import ContextItem, render_catalog_ref
from .topic_router import RoutingResult

if TYPE_CHECKING:  # import-time cycle: agent.context -> agent -> workflow -> shadow
    from ..agent.context import RequestDigest

RENDERER_VERSION = "prompt-library.v1"

# Priorities are relative only; the packer sorts hard items ahead of optional
# ones regardless, so these order items *within* the optional tier.
_P_CATALOG_REQUIRED = 90
_P_RELATION = 80
_P_TOPIC = 70
_P_CATALOG_OPTIONAL = 50
_P_EXAMPLE = 10


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _plannable(ref: str) -> bool:
    """Refs an AtomicPlan may address.

    Tool-computed similarity refs and ``context.*`` are indistinguishable from
    real measures in the catalogue -- same kind, same answerability -- so the
    filter has to live here, at the one place that builds a catalog item.
    Applying it only to required refs (as this first did) let the same refs back
    in through the optional candidate list.
    """
    return ref in _CATALOG_REFS and ref not in topics.non_sql_refs()


def _catalog_item(ref: str, *, droppable: bool, priority: int) -> ContextItem:
    rendered = render_catalog_ref(ref)
    return ContextItem(
        item_id=f"catalog:{ref}", kind="catalog", payload={"render": rendered},
        priority=priority, semantic_refs=(ref,), source="catalog",
        source_hash=_hash(rendered), droppable=droppable,
    )


def _relation_item(name: str) -> ContextItem:
    spec = RELATIONS[name]
    # Join keys are deliberately omitted: §6.6 forbids physical keys in a
    # prompt, and the compiler resolves the path from the registry anyway.
    rendered = (
        f"{spec.name} | {spec.left} -> {spec.right} | card={spec.cardinality} "
        f"| grain={spec.input_grain}->{spec.output_grain} "
        f"| fanout={spec.fanout_effect} | dedupe={spec.dedupe_strategy or '-'}"
    )
    return ContextItem(
        item_id=f"relation:{name}", kind="relation", payload={"render": rendered},
        priority=_P_RELATION, source="relations", source_hash=_hash(rendered),
        droppable=False,
    )


def _invariant_item(invariant_id: str) -> ContextItem:
    spec = INVARIANTS[invariant_id]
    rendered = f"{spec.invariant_id}@{spec.version} | {spec.severity} | {spec.message_key}"
    return ContextItem(
        item_id=f"invariant:{invariant_id}", kind="constraint",
        payload={"render": rendered}, priority=100,
        semantic_refs=spec.semantic_refs, source="invariants",
        source_hash=_hash(rendered), droppable=spec.severity != "hard",
    )


def _topic_item(topic_id: str) -> ContextItem:
    card = topics.TOPICS[topic_id]
    rendered = f"{card.id} {card.name} | kind={card.kind} | anchors={','.join(card.anchor_entities) or '-'}"
    return ContextItem(
        item_id=f"topic:{topic_id}", kind="topic", payload={"render": rendered},
        priority=_P_TOPIC, source="topics", source_hash=_hash(rendered),
        droppable=True,
    )


def build_atomic_plan_context(
    digest: "RequestDigest",
    routing: RoutingResult,
    *,
    required_refs: tuple[str, ...] = (),
    required_relations: tuple[str, ...] = (),
    examples: tuple[str, ...] = (),
    allow_broad_slice: bool = False,
) -> list[ContextItem]:
    """Assemble items for an AtomicPlan call, in §6.6 selection order."""
    items: list[ContextItem] = []
    seen_refs: set[str] = set()

    # 1. hard constraints + digest -- undroppable by construction.
    for invariant_id in hard_invariants():
        items.append(_invariant_item(invariant_id))
    digest_payload = digest.model_dump(mode="json")
    items.append(ContextItem(
        item_id="digest", kind="digest", payload=digest_payload, priority=100,
        source="request_digest",
        source_hash=_hash(repr(sorted(digest_payload.items()))), droppable=False,
    ))

    # 2. required refs, whatever topic owns them.
    for ref in dict.fromkeys(tuple(required_refs) + routing.resolved_refs):
        if not _plannable(ref):
            continue
        items.append(_catalog_item(ref, droppable=False, priority=_P_CATALOG_REQUIRED))
        seen_refs.add(ref)

    # 3. universal CORE refs for scope and grouping.
    for ref in topics.TOPICS["CORE"].all_refs():
        if ref in seen_refs or not _plannable(ref):
            continue
        items.append(_catalog_item(ref, droppable=True, priority=_P_CATALOG_OPTIONAL + 10))
        seen_refs.add(ref)

    # 4. optional candidates, restricted to the effective refs of selected
    #    topics. A broad slice is admissible only where §6.6 permits it, and
    #    never as a way to reach a ref the route did not justify.
    if allow_broad_slice and routing.mode in {"unknown", "overflow"}:
        candidate_refs = tuple(_CATALOG_REFS)
    else:
        candidate_refs = routing.effective_refs()
    for ref in candidate_refs:
        if ref in seen_refs or not _plannable(ref):
            continue
        items.append(_catalog_item(ref, droppable=True, priority=_P_CATALOG_OPTIONAL))
        seen_refs.add(ref)

    # 5. minimal relation union. Required relations stay undroppable so
    #    relation recall cannot be traded for budget.
    for name in dict.fromkeys(tuple(required_relations) + routing.required_relation_ids):
        if name in RELATIONS:
            items.append(_relation_item(name))

    # 6. topic cards and examples -- the first things the budget may take.
    for topic_id in routing.domain_topic_ids + routing.aspect_topic_ids:
        items.append(_topic_item(topic_id))
    for index, example in enumerate(examples):
        items.append(ContextItem(
            item_id=f"example:{index}", kind="example", payload={"text": example},
            priority=_P_EXAMPLE, source="eval", source_hash=_hash(example),
            droppable=True,
        ))
    return items


def _catalog_refs() -> frozenset[str]:
    from ..domain.catalog import CATALOG
    return frozenset(CATALOG)


_CATALOG_REFS = _catalog_refs()
