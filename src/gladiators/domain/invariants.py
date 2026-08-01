"""Invariant registry — ultimate solution §3.8.

Cross-topic rules currently live as prose: a caveat string on a catalogue
object, a trap number, a comment in a validator.  Deciding anything from prose
means parsing it, and prose drifts from the check it is supposed to describe.

Here each rule is an addressable, versioned spec pointing at a deterministic
handler.  Callers reference ``invariant_id``; the message a user sees comes from
``message_key`` so there is never a second copy of the rule text living in a
TopicCard or a prompt.

``registry_hash`` feeds the context hash, the topic/decomposition gates and the
proof pack, so a changed rule set cannot be served from a cache or signed off
against an artifact built under the old rules.
"""
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict

InvariantStage = Literal[
    "request", "plan", "composition", "execution", "evidence", "answer",
]
Severity = Literal["hard", "warning"]


class InvariantSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    invariant_id: str
    version: str
    severity: Severity
    applies_to: tuple[InvariantStage, ...]
    semantic_refs: tuple[str, ...] = ()
    operators: tuple[str, ...] = ()
    validator_id: str
    message_key: str
    owner: str
    # Trap numbers from the data brief, kept as a mapping rather than as prose so
    # existing caveats can be traced to the rule that enforces them.
    traps: tuple[int, ...] = ()


_SPECS: tuple[InvariantSpec, ...] = (
    InvariantSpec(
        invariant_id="INV-CURRENCY-NO-MIX", version="1.0", severity="hard",
        applies_to=("request", "plan", "evidence"),
        semantic_refs=("measure.price", "measure.price_original", "derived.estimated_recent_revenue"),
        operators=("Aggregate", "Union", "Rank"),
        validator_id="currency.no_cross_market_arithmetic",
        message_key="invariant.currency_no_mix", owner="data-engineering",
    ),
    InvariantSpec(
        invariant_id="INV-DEDUPE-BEFORE-AGGREGATE", version="1.0", severity="hard",
        applies_to=("plan", "execution"),
        operators=("Join", "Aggregate"),
        validator_id="grain.dedupe_before_aggregate",
        message_key="invariant.dedupe_before_aggregate", owner="data-engineering",
        traps=(12,),
    ),
    InvariantSpec(
        invariant_id="INV-PRICE-SENTINEL-EXCLUDED", version="1.0", severity="hard",
        applies_to=("plan", "execution"),
        semantic_refs=("measure.price",), operators=("Aggregate", "Rank"),
        validator_id="sentinel.price_excluded_before_rank",
        message_key="invariant.price_sentinel_excluded", owner="data-owner",
        traps=(5,),
    ),
    InvariantSpec(
        invariant_id="INV-SNAPSHOT-SCOPE", version="1.0", severity="hard",
        applies_to=("request", "plan", "evidence"),
        semantic_refs=("dim.date",),
        validator_id="temporal.scope_within_governed_snapshots",
        message_key="invariant.snapshot_scope", owner="data-engineering",
    ),
    InvariantSpec(
        invariant_id="INV-DATE-RANGE-HONOURED", version="1.0", severity="hard",
        applies_to=("evidence",), semantic_refs=("dim.date",),
        operators=("TemporalCompare",),
        validator_id="temporal.evidence_matches_requested_range",
        message_key="invariant.date_range_honoured", owner="architecture",
    ),
    InvariantSpec(
        invariant_id="INV-COUNTRY-COVERAGE", version="1.0", severity="hard",
        applies_to=("evidence",), semantic_refs=("dim.country",),
        validator_id="scope.evidence_covers_requested_countries",
        message_key="invariant.country_coverage", owner="architecture",
    ),
    InvariantSpec(
        invariant_id="INV-PROXY-NOT-VERIFIED-SALES", version="1.0", severity="warning",
        applies_to=("answer",),
        semantic_refs=("measure.monthly_sold", "measure.history_sold", "derived.estimated_recent_revenue"),
        validator_id="wording.proxy_labelled_as_estimate",
        message_key="invariant.proxy_label_required", owner="product",
        traps=(4,),
    ),
    InvariantSpec(
        invariant_id="INV-NO-CAUSAL-CLAIM", version="1.0", severity="hard",
        applies_to=("answer",),
        validator_id="wording.no_causal_claim",
        message_key="invariant.no_causal_claim", owner="product",
    ),
    InvariantSpec(
        invariant_id="INV-EMPTY-RESULT-IS-VALID", version="1.0", severity="hard",
        applies_to=("execution", "evidence"),
        validator_id="execution.zero_row_is_a_result",
        message_key="invariant.empty_result_valid", owner="architecture",
    ),
    InvariantSpec(
        invariant_id="INV-NO-INTERNAL-VOCABULARY", version="1.0", severity="hard",
        applies_to=("answer",),
        validator_id="wording.no_internal_jargon",
        message_key="invariant.no_internal_vocabulary", owner="product",
    ),
    InvariantSpec(
        invariant_id="INV-SHELF-NOT-PLATFORM-CATEGORY", version="1.0", severity="hard",
        applies_to=("plan",),
        semantic_refs=("entity.shop_category", "entity.platform_category"),
        operators=("Join",),
        validator_id="relation.no_shelf_to_platform_edge",
        message_key="invariant.shelf_not_platform_category", owner="data-engineering",
        traps=(2, 3),
    ),
)


class InvariantRegistryError(ValueError):
    pass


def _build(specs: tuple[InvariantSpec, ...]) -> dict[str, InvariantSpec]:
    registry: dict[str, InvariantSpec] = {}
    from .catalog import CATALOG  # local import: catalog must not import this

    for spec in specs:
        if spec.invariant_id in registry:
            raise InvariantRegistryError(f"Invariant trùng ID: {spec.invariant_id}")
        if not spec.applies_to:
            raise InvariantRegistryError(f"{spec.invariant_id}: applies_to rỗng")
        missing = [ref for ref in spec.semantic_refs if ref not in CATALOG]
        if missing:
            raise InvariantRegistryError(
                f"{spec.invariant_id}: semantic ref không tồn tại: {missing}"
            )
        if not spec.validator_id or not spec.message_key or not spec.owner:
            raise InvariantRegistryError(
                f"{spec.invariant_id}: thiếu validator_id/message_key/owner"
            )
        registry[spec.invariant_id] = spec
    return registry


INVARIANTS: dict[str, InvariantSpec] = _build(_SPECS)

REGISTRY_HASH: str = hashlib.sha256(
    "|".join(
        f"{spec.invariant_id}@{spec.version}:{spec.severity}:{spec.validator_id}"
        for spec in sorted(INVARIANTS.values(), key=lambda item: item.invariant_id)
    ).encode("utf-8")
).hexdigest()[:16]


def get(invariant_id: str) -> InvariantSpec | None:
    return INVARIANTS.get(invariant_id)


def for_stage(stage: InvariantStage) -> tuple[InvariantSpec, ...]:
    return tuple(
        spec for spec in INVARIANTS.values() if stage in spec.applies_to
    )


def hard_invariants() -> tuple[str, ...]:
    """IDs a critic may never downgrade, skip or 'repair' (§3.8)."""
    return tuple(sorted(
        spec.invariant_id for spec in INVARIANTS.values() if spec.severity == "hard"
    ))
