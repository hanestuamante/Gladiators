"""ContextPacker — ultimate solution §7.1 / §7.2.

Everything sent to a model competes for one budget.  Today that competition is
implicit: whoever assembles the payload decides what fits, and when something is
cut nobody downstream can tell whether it was cut or never existed.  A dropped
relation and an absent relation produce the same prompt.

So the packer makes dropping explicit and asymmetric:

**Hard items are never dropped.**  Constraints, the digest, required refs and
relations, and validator feedback for a repair are structural.  If they do not
fit, that is a terminal ``context_budget_unsatisfied`` -- silently trimming an
invariant to make room for an example is how a guard stops guarding.

**The packer measures; it does not ask.**  ``estimated_tokens`` from a caller is
advisory and overwritten. A caller that undercounts its own payload would
otherwise overflow the budget it was handed.

**A guard-rejected hard item is terminal, not a drop.**  Recording it in the
drop ledger would make a rejected constraint look like an optional item that
lost a budget race.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..domain.catalog import CATALOG, SourceTier
from ..domain.invariants import INVARIANTS
from ..external.injection_guard import sanitize_internal_text

PACKER_VERSION = "context-packer.v1"
DEFAULT_RESERVE_RATIO = 0.15

ItemKind = Literal[
    "constraint", "digest", "feedback", "catalog",
    "relation", "topic", "evidence", "example",
]
DropReason = Literal["budget", "irrelevant", "stale", "guard_reject"]

# §7.2 budgets. Kept as typed config and written to the trace so a budget change
# is visible in the config hash rather than buried in a call site.
BUDGETS: dict[str, int] = {
    "generate": 4000,
    "extract": 2000,
    "decomposition_proposal": 3000,
    "atomic_plan": 6000,
    "atomic_repair": 3000,
    "critic": 4000,
    "alternate": 6000,
    "adjudicate": 3000,
}

# Staleness ceilings by tier. Internal governed data is versioned rather than
# aged, so only outward-sourced material expires on a clock.
STALENESS_POLICY: dict[SourceTier, timedelta | None] = {
    "btc_dataset": None,
    "reference": timedelta(days=30),
    "external": timedelta(days=1),
}


class ContextPackerError(RuntimeError):
    """Terminal packing failure. ``code`` is the stable outward identifier."""

    def __init__(self, code: str, message: str, *, item_ids: tuple[str, ...] = ()):
        super().__init__(message)
        self.code = code
        self.item_ids = item_ids


class ContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str
    kind: ItemKind
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    estimated_tokens: int = 0
    semantic_refs: tuple[str, ...] = ()
    source: str
    source_tier: SourceTier = "btc_dataset"
    source_hash: str
    as_of: datetime | None = None
    staleness_policy_id: str | None = None
    droppable: bool = True


class DroppedContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    item_id: str
    reason: DropReason
    estimated_tokens: int
    source_hash: str


class PackedContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    stage: str
    dataset_version: str
    digest_hash: str
    routing_hash: str | None = None
    items: tuple[ContextItem, ...] = ()
    dropped: tuple[DroppedContext, ...] = ()
    estimated_tokens: int = 0
    budget_tokens: int = 0
    reserve_ratio: float = DEFAULT_RESERVE_RATIO
    context_hash: str = ""

    @property
    def usable_budget(self) -> int:
        return int(self.budget_tokens * (1 - self.reserve_ratio))

    def selected_refs(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            ref for item in self.items for ref in item.semantic_refs
        ))

    def trace_summary(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "context_hash": self.context_hash,
            "routing_hash": self.routing_hash,
            "estimated_tokens": self.estimated_tokens,
            "budget_tokens": self.budget_tokens,
            "usable_budget": self.usable_budget,
            "item_count": len(self.items),
            "dropped_count": len(self.dropped),
            "packer_version": PACKER_VERSION,
        }


# --- rendering ------------------------------------------------------------

def canonical_render(item: ContextItem) -> str:
    """Deterministic text for an item, used for both tokens and hashing.

    Catalog items get the compact §7.2 line rather than a JSON dump: repeating
    caveat prose for every ref is most of the payload and none of the meaning.
    """
    if item.kind == "catalog":
        return "\n".join(render_catalog_ref(ref) for ref in item.semantic_refs) or _json(item.payload)
    return _json(item.payload)


def invariants_for_ref(ref: str) -> tuple[str, ...]:
    """Invariant ids that bind a ref, derived from the registry.

    The catalogue has no invariant field; it carries prose caveats and trap
    numbers. Deriving from §3.8 instead means the rendered rule and the enforced
    rule cannot drift, which restating them in the prompt would guarantee.
    """
    return tuple(sorted(
        spec.invariant_id for spec in INVARIANTS.values() if ref in spec.semantic_refs
    ))


def render_catalog_ref(ref: str) -> str:
    """`<ref> | <kind> | <unit> | grain= | agg= | filters= | binding= | invariant=`

    Physical columns are deliberately absent: §6.6 forbids the renderer from
    putting a join key or dataset fact into a prompt, so the planner can only
    ever address semantics.
    """
    obj = CATALOG.get(ref)
    if obj is None:
        return f"{ref} | unknown"
    return " | ".join([
        ref,
        getattr(obj, "kind", "") or "",
        getattr(obj, "unit", "") or "",
        f"grain={getattr(obj, 'grain', '') or ''}",
        f"agg={_join(getattr(obj, 'valid_aggregations', ()))}",
        f"filters={_join(getattr(obj, 'allowed_filters', ()))}",
        f"binding={getattr(obj, 'answerability', '') or ''}",
        f"invariant={_join(invariants_for_ref(ref))}",
    ])


def _join(values) -> str:
    return ",".join(str(v) for v in (values or ())) or "-"


def _json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# --- token estimation -----------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Byte-ratio fallback estimator (§7.2).

    Deliberately an over-estimate for Vietnamese: diacritics cost 2-3 UTF-8
    bytes each, so a byte-based count runs ahead of the real token count. An
    estimator that undercounts overflows a budget it believed it met.
    """
    if not text:
        return 0
    return math.ceil(len(text.encode("utf-8")) / 3.5)


TokenEstimator = Callable[[str], int]


# --- packing --------------------------------------------------------------

def _guard(item: ContextItem) -> tuple[ContextItem, tuple[str, ...]]:
    """Neutralise instruction-like spans in text payload values."""
    hits: list[str] = []
    payload = dict(item.payload)
    for key, value in tuple(payload.items()):
        if not isinstance(value, str):
            continue
        guarded = sanitize_internal_text(value)
        payload[key] = guarded.text
        hits.extend(f"{item.item_id}:{key}:{hit}" for hit in guarded.hits)
    if not hits:
        return item, ()
    return item.model_copy(update={"payload": payload}), tuple(hits)


def _is_stale(item: ContextItem, now: datetime) -> bool:
    ceiling = STALENESS_POLICY.get(item.source_tier)
    if ceiling is None or item.as_of is None:
        return False
    as_of = item.as_of if item.as_of.tzinfo else item.as_of.replace(tzinfo=timezone.utc)
    return (now - as_of) > ceiling


def pack_context(
    stage: str,
    dataset_version: str,
    digest_hash: str,
    routing_hash: str | None,
    items: list[ContextItem],
    budget_tokens: int | None = None,
    reserve_ratio: float = DEFAULT_RESERVE_RATIO,
    *,
    estimator: TokenEstimator = estimate_tokens,
    now: datetime | None = None,
) -> PackedContext:
    budget_tokens = budget_tokens if budget_tokens is not None else BUDGETS.get(stage, 4000)
    now = now or datetime.now(timezone.utc)
    dropped: list[DroppedContext] = []

    # 1. guard. A hard item whose content was neutralised is terminal: packing a
    #    constraint whose text has been replaced would enforce nothing.
    guarded: list[ContextItem] = []
    rejected_hard: list[str] = []
    for item in items:
        checked, hits = _guard(item)
        if hits and not item.droppable:
            rejected_hard.append(item.item_id)
            continue
        if hits and item.droppable:
            dropped.append(DroppedContext(
                item_id=item.item_id, reason="guard_reject",
                estimated_tokens=0, source_hash=item.source_hash,
            ))
            continue
        guarded.append(checked)
    if rejected_hard:
        raise ContextPackerError(
            "context_guard_reject_hard",
            f"Hard context item bị guard từ chối: {sorted(rejected_hard)}",
            item_ids=tuple(sorted(rejected_hard)),
        )

    # 2. staleness, before packing. A required internal item that has gone stale
    #    is terminal -- falling back to an older copy would answer today's
    #    question from yesterday's data without saying so.
    fresh: list[ContextItem] = []
    for item in guarded:
        if not _is_stale(item, now):
            fresh.append(item)
            continue
        if not item.droppable:
            raise ContextPackerError(
                "context_required_item_stale",
                f"Required context item quá hạn staleness: {item.item_id}",
                item_ids=(item.item_id,),
            )
        dropped.append(DroppedContext(
            item_id=item.item_id, reason="stale",
            estimated_tokens=0, source_hash=item.source_hash,
        ))

    # 3. dedupe on (kind, source_hash); keep the first, and never let a
    #    droppable duplicate displace a hard one.
    deduped: list[ContextItem] = []
    seen: dict[tuple[str, str], ContextItem] = {}
    for item in sorted(fresh, key=lambda i: (i.droppable, -i.priority, i.item_id)):
        key = (item.kind, item.source_hash)
        if key in seen:
            dropped.append(DroppedContext(
                item_id=item.item_id, reason="irrelevant",
                estimated_tokens=0, source_hash=item.source_hash,
            ))
            continue
        seen[key] = item
        deduped.append(item)

    # 4. measure. The caller's estimate is advisory and overwritten.
    measured = [
        item.model_copy(update={"estimated_tokens": estimator(canonical_render(item))})
        for item in deduped
    ]

    hard = [item for item in measured if not item.droppable]
    optional = sorted(
        (item for item in measured if item.droppable),
        key=lambda i: (-i.priority, i.item_id),
    )

    usable = int(budget_tokens * (1 - reserve_ratio))
    hard_tokens = sum(item.estimated_tokens for item in hard)
    if hard_tokens > usable:
        raise ContextPackerError(
            "context_budget_unsatisfied",
            f"Hard context {hard_tokens} token vượt budget dùng được {usable}; "
            "không cắt invariant để nhét vừa.",
            item_ids=tuple(item.item_id for item in hard),
        )

    selected = list(hard)
    total = hard_tokens
    for item in optional:
        if total + item.estimated_tokens > usable:
            dropped.append(DroppedContext(
                item_id=item.item_id, reason="budget",
                estimated_tokens=item.estimated_tokens, source_hash=item.source_hash,
            ))
            continue
        selected.append(item)
        total += item.estimated_tokens

    selected.sort(key=lambda i: (i.droppable, -i.priority, i.item_id))
    packed = PackedContext(
        stage=stage, dataset_version=dataset_version, digest_hash=digest_hash,
        routing_hash=routing_hash, items=tuple(selected),
        dropped=tuple(sorted(dropped, key=lambda d: d.item_id)),
        estimated_tokens=total, budget_tokens=budget_tokens,
        reserve_ratio=reserve_ratio,
    )
    return packed.model_copy(update={"context_hash": _context_hash(packed)})


def _context_hash(packed: PackedContext) -> str:
    """Hash over content and ledger, excluding anything auto-timestamped.

    ``as_of`` is deliberately omitted: including a wall-clock field would make
    two identical contexts hash differently and defeat the cache the hash exists
    to key.
    """
    canonical = {
        "stage": packed.stage,
        "dataset_version": packed.dataset_version,
        "digest_hash": packed.digest_hash,
        "routing_hash": packed.routing_hash,
        "budget_tokens": packed.budget_tokens,
        "reserve_ratio": packed.reserve_ratio,
        "packer_version": PACKER_VERSION,
        "items": [
            {
                "item_id": item.item_id, "kind": item.kind,
                "render": canonical_render(item),
                "refs": sorted(item.semantic_refs),
                "source_hash": item.source_hash, "priority": item.priority,
                "droppable": item.droppable,
            }
            for item in packed.items
        ],
        "dropped": [d.model_dump(mode="json") for d in packed.dropped],
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        .encode("utf-8")
    ).hexdigest()[:32]


# --- metrics (§7.3) -------------------------------------------------------

def context_metrics(
    packed: PackedContext,
    *,
    used_plan_refs: tuple[str, ...] = (),
    oracle_required_refs: tuple[str, ...] = (),
    selected_relations: tuple[str, ...] = (),
    oracle_required_relations: tuple[str, ...] = (),
) -> dict[str, Any]:
    """§7.3 definitions, computed per attempt rather than only for the winner.

    Computing these only on the accepted plan hides the catalog miss that forced
    the first attempt to be thrown away.
    """
    selected = set(packed.selected_refs())
    used = set(used_plan_refs)
    required = set(oracle_required_refs)
    required_rel = set(oracle_required_relations)
    overlap = used & selected
    return {
        "context_precision": len(overlap) / max(1, len(selected)),
        "context_recall": len(overlap) / max(1, len(used)),
        "required_ref_recall": len(required & selected) / max(1, len(required)),
        "required_relation_recall": (
            len(required_rel & set(selected_relations)) / max(1, len(required_rel))
        ),
        "catalog_miss": sorted(used - selected),
        "catalog_miss_count": len(used - selected),
        "estimated_tokens": packed.estimated_tokens,
        "dropped_count": len(packed.dropped),
        "context_hash": packed.context_hash,
        "routing_hash": packed.routing_hash,
    }
