"""CapabilitySpec and matcher — ultimate solution §3.5 / §3.6.

A capability is what the system can actually answer, described as a semantic
contract rather than an intent label.  ``CertifiedShape`` said only which
measures a macro tolerates; matching therefore came down to a name lookup, and a
question the label happened to hit was routed to a macro that answers a
different question.  That is the failure the DeepSeek smoke run surfaced: a
counting question labelled ``dataset_coverage`` was answered with the data's date
range.

The matcher deals in *semantics only*.  Whether the data exists is a separate
question answered from a precomputed profile (§3.6): a matcher that reads
artifacts would make "we cannot answer this" and "there is nothing to answer
from" indistinguishable, and those need different remedies.

Specs are derived from the certified macro registry rather than written twice --
§3.5 is explicit that three parallel registries must not exist.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CapabilityKind = Literal["macro", "template", "analytical", "tool", "insight"]
BlockerCode = Literal[
    "shape", "measure", "measure_missing", "grouping",
    "grouping_missing", "aggregation", "filter", "qualifier", "scope",
]
AvailabilityBlocker = Literal[
    "data_absent", "zero_variance", "binding_unavailable",
    "formula_not_approved", "dataset_scope_missing",
]


class CapabilityFilterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ref: str
    allowed_ops: frozenset[str]
    required: bool = False


class CapabilitySpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    capability_id: str
    kind: CapabilityKind
    produces_shape: str
    produces_grain: str
    required_measures: frozenset[str] = frozenset()
    optional_measures: frozenset[str] = frozenset()
    allowed_grouping: frozenset[str] = frozenset()
    required_grouping_count: int = 0
    allowed_aggregations: frozenset[str] = frozenset()
    allowed_filters: tuple[CapabilityFilterSpec, ...] = ()
    required_slots: frozenset[str] = frozenset()
    scope_predicates: frozenset[str] = frozenset()
    forbidden_qualifiers: frozenset[str] = frozenset()
    cue_terms: tuple[str, ...] = ()
    tool_plan: tuple[str, ...] = ()
    macro_name: str | None = None
    output_field_refs: tuple[str, ...] = ()


class CapabilityBlocker(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: BlockerCode
    requested: tuple[str, ...] = ()
    supported: tuple[str, ...] = ()


class MatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability_id: str
    eligible: bool
    score: int
    score_breakdown: dict[str, int] = Field(default_factory=dict)
    blockers: tuple[CapabilityBlocker, ...] = ()
    missing_slots: tuple[str, ...] = ()


class AvailabilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    available: bool
    blockers: tuple[AvailabilityBlocker, ...] = ()
    profile_version: str
    dataset_version: str


class CapabilityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    match: MatchResult
    availability: AvailabilityResult
    eligible: bool
    decision_blockers: tuple[str, ...] = ()


def specs_from_macros(registry) -> tuple[CapabilitySpec, ...]:
    """Derive capability specs from the certified macro registry.

    §3.5 forbids three parallel registries, so these are *derived*, not
    authored: a macro's certified shape, required slots and tool plan already
    describe what it can serve, and duplicating that by hand is how the two
    drift apart.
    """
    specs: list[CapabilitySpec] = []
    for name in registry.names():
        macro = registry.get(name)
        shape = macro.certified_shape
        specs.append(CapabilitySpec(
            capability_id=name, kind="macro",
            produces_shape=shape.output_shape,
            produces_grain=macro.plan_template.nodes[-1].output_grain,
            required_measures=frozenset(shape.required_measures),
            optional_measures=frozenset(shape.allowed_extra_measures),
            allowed_grouping=frozenset(shape.allowed_grouping),
            forbidden_qualifiers=frozenset(shape.forbidden_qualifiers),
            required_slots=frozenset(macro.required_slots),
            tool_plan=tuple(macro.tool_plan),
            macro_name=macro.name,
            output_field_refs=tuple(
                field.semantic_ref for field in macro.plan_template.requested_output_shape
                if field.semantic_ref
            ),
        ))
    return tuple(specs)


def match(digest, spec: CapabilitySpec) -> MatchResult:
    """Score one capability against a request digest.

    A blocker is a reason this capability answers a *different* question, so any
    blocker makes it ineligible.  Score only orders the eligible ones; it never
    rescues a blocked one, because "closest available" is how a system ends up
    answering something it was not asked.
    """
    requested_measures = frozenset(getattr(digest, "requested_measures", ()) or ())
    requested_dimensions = frozenset(getattr(digest, "requested_dimensions", ()) or ())
    grouping = frozenset(
        ref for ref in requested_dimensions if ref not in {"dim.country", "dim.date"}
    )
    qualifiers = frozenset(getattr(digest, "qualifiers", ()) or ())
    shape = getattr(digest, "requested_output_shape", None)

    blockers: list[CapabilityBlocker] = []
    breakdown: dict[str, int] = {}

    if spec.produces_shape and shape and shape != spec.produces_shape:
        blockers.append(CapabilityBlocker(
            code="shape", requested=(str(shape),), supported=(spec.produces_shape,),
        ))
    else:
        breakdown["shape"] = 2

    missing_measures = tuple(sorted(spec.required_measures - requested_measures))
    if missing_measures:
        blockers.append(CapabilityBlocker(
            code="measure_missing", requested=tuple(sorted(requested_measures)),
            supported=tuple(sorted(spec.required_measures)),
        ))
    supported_measures = spec.required_measures | spec.optional_measures
    unsupported = tuple(sorted(requested_measures - supported_measures))
    if unsupported and supported_measures:
        blockers.append(CapabilityBlocker(
            code="measure", requested=unsupported,
            supported=tuple(sorted(supported_measures)),
        ))
    else:
        breakdown["measure"] = 3 * len(requested_measures & supported_measures)

    unsupported_grouping = tuple(sorted(grouping - spec.allowed_grouping))
    if unsupported_grouping and spec.allowed_grouping:
        blockers.append(CapabilityBlocker(
            code="grouping", requested=unsupported_grouping,
            supported=tuple(sorted(spec.allowed_grouping)),
        ))
    elif len(grouping) < spec.required_grouping_count:
        blockers.append(CapabilityBlocker(
            code="grouping_missing", requested=tuple(sorted(grouping)),
            supported=tuple(sorted(spec.allowed_grouping)),
        ))
    else:
        breakdown["grouping"] = len(grouping & spec.allowed_grouping)

    forbidden = tuple(sorted(qualifiers & spec.forbidden_qualifiers))
    if forbidden:
        blockers.append(CapabilityBlocker(
            code="qualifier", requested=forbidden,
            supported=tuple(sorted(spec.forbidden_qualifiers)),
        ))

    missing_slots = tuple(sorted(
        slot for slot in spec.required_slots
        if not getattr(digest, slot, None)
    ))
    return MatchResult(
        capability_id=spec.capability_id,
        eligible=not blockers,
        score=sum(breakdown.values()),
        score_breakdown=breakdown,
        blockers=tuple(blockers),
        missing_slots=missing_slots,
    )


def rank(digest, specs) -> tuple[MatchResult, ...]:
    """Every capability scored, best eligible first, blocked ones after."""
    results = [match(digest, spec) for spec in specs]
    return tuple(sorted(
        results, key=lambda item: (not item.eligible, -item.score, item.capability_id),
    ))


def nearest_answerable(
    digest, specs, decisions: dict[str, AvailabilityResult] | None = None,
    limit: int = 3,
) -> tuple[str, ...]:
    """Capabilities reachable by relaxing exactly one axis (§3.6).

    Deliberately one axis: a suggestion that changes the measure *and* the
    grouping is a different question wearing the original's clothes. Anything
    with a data blocker is dropped -- suggesting a question we also cannot
    answer wastes the reader's next turn.
    """
    decisions = decisions or {}
    suggestions: list[tuple[int, str]] = []
    for result in rank(digest, specs):
        if result.eligible or len(result.blockers) != 1:
            continue
        availability = decisions.get(result.capability_id)
        if availability is not None and not availability.available:
            continue
        suggestions.append((-result.score, result.capability_id))
    suggestions.sort()
    return tuple(capability for _, capability in suggestions[:limit])
