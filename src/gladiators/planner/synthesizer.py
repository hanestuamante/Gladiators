"""DeterministicPlanSynthesizer — ultimate solution §5.

Replaces the six hard-coded templates in :mod:`analytical` with a grammar.  The
templates could only answer the exact questions someone had already written a
builder for; anything adjacent -- a different direction, a named date, a
grouping, an extra filter -- fell through to ``A19-PLAN``.  That rigidity is
what this module removes: the same node patterns are now generated from the
request instead of being frozen per question.

Release grammar (§5)::

    1 bound scalar measure (or a certified RatioSpec)
    × 0..2 bound dimensions
    × shape ∈ {scalar, ratio, ranking, comparison, table}
    × aggregation ∈ CatalogObject.valid_aggregations
    × country mandatory
    × optional date
    × ≤2 allowed predicates
    × 0..1 certified relation

Anything outside the grammar returns ``None`` so the caller can fall through to
the decomposer or ``A-CAPABILITY-MISS``.  The grammar is never widened to make a
question fit -- that is the rule which keeps this from becoming a second,
sloppier planner.  Every plan still goes through the existing validator,
compiler and executor.
"""
from __future__ import annotations

from dataclasses import dataclass

from gladiators.domain.catalog import CATALOG
from gladiators.domain.relations import RELATIONS

from .query_ir import LogicalQueryPlan, OutputField, PlanNode, Predicate
from .semantic_parser import AnalyticalRequest

MAX_DIMENSIONS = 2
MAX_EXTRA_PREDICATES = 2
PRICE_SENTINEL = 999999999
SCOPE_REFS = frozenset({"dim.country", "dim.date"})

# Base scan artifacts, in preference order. products_clean carries the raw
# listing attributes; snapshot metrics carries the derived ones.
_BASE_SOURCES = ("products_clean.csv", "product_snapshot_metrics.csv")

# Dimensions that live on the shop table and therefore need the one certified
# relation this grammar allows.
_SHOP_RELATION = "belongs_to"

_TYPE_BY_CATALOG_TYPE = {
    "number": "number", "integer": "integer", "date": "date",
    "bool": "boolean", "string": "string",
}


class SynthesisError(ValueError):
    pass


@dataclass(frozen=True)
class SynthesisResult:
    plan: LogicalQueryPlan
    grammar_path: str
    aggregation: str | None
    dimensions: tuple[str, ...]
    relation: str | None


def _sources_of(ref: str) -> set[str]:
    obj = CATALOG.get(ref)
    if obj is None or not obj.physical:
        return set()
    return {column.split(".csv")[0] + ".csv" for column in obj.physical}


def _field(ref: str, name: str | None = None) -> OutputField:
    obj = CATALOG[ref]
    return OutputField(
        name=name or ref.split(".")[-1],
        type=_TYPE_BY_CATALOG_TYPE.get(obj.type, "string"),
        semantic_ref=ref,
    )


def _bound_refs(items) -> list[str]:
    return [item.ref for item in items if item.ref and not item.unresolved]


def _choose_aggregation(measure_ref: str, request: AnalyticalRequest) -> str | None:
    """Pick an aggregation the catalog actually certifies for this measure.

    §5: ``sum(monthly_sold)`` is rejected because the catalog does not list it.
    A requested aggregation outside ``valid_aggregations`` is a refusal, never a
    silent substitution -- answering a mean question with a median is exactly the
    class of wrong answer this whole layer exists to stop.
    """
    allowed = CATALOG[measure_ref].valid_aggregations
    if not allowed:
        return None
    if "mean_requested" in request.assumptions or "mean" in request.analytical_operators:
        return "mean" if "mean" in allowed else None
    if measure_ref == "derived.product_count":
        return "count" if "count" in allowed else None
    return "median" if "median" in allowed else allowed[0]


def synthesize(request: AnalyticalRequest, country: str) -> SynthesisResult | None:
    """Build a plan for the release grammar, or ``None`` when out of grammar."""
    if not country:
        return None  # country is mandatory; cross-market needs the decomposer

    measures = _bound_refs(request.requested_measures)
    if len(measures) != 1:
        return None
    measure_ref = measures[0]
    if measure_ref not in CATALOG:
        return None
    if CATALOG[measure_ref].answerability in {"absent", "context_only"}:
        return None

    dimensions = [ref for ref in _bound_refs(request.requested_dimensions) if ref not in SCOPE_REFS]
    dimensions = list(dict.fromkeys(dimensions))
    if len(dimensions) > MAX_DIMENSIONS:
        return None

    extra = [p for p in request.filters if p.field_ref not in SCOPE_REFS]
    if len(extra) > MAX_EXTRA_PREDICATES:
        return None

    aggregation = _choose_aggregation(measure_ref, request)
    if aggregation is None:
        return None

    dates = tuple(request.time_scope.dates) if request.time_scope else ()
    if len(dates) != 1:
        # Multi-snapshot aggregation is a decomposition question (§8.6
        # union_scope), not something to average over silently.
        return None
    date = dates[0]

    # --- source and relation ------------------------------------------------
    needed = {measure_ref, *dimensions, *(p.field_ref for p in extra)}
    needed.discard("derived.product_count")  # counted, not scanned
    source = next(
        (
            candidate for candidate in _BASE_SOURCES
            if all(not _sources_of(ref) or candidate in _sources_of(ref) for ref in needed)
        ),
        None,
    )
    relation: str | None = None
    if source is None:
        # One certified relation is allowed: listing → shop.
        shop_side = {ref for ref in needed if _sources_of(ref) == {"shop_info_clean.csv"}}
        rest = needed - shop_side
        source = next(
            (
                candidate for candidate in _BASE_SOURCES
                if all(not _sources_of(ref) or candidate in _sources_of(ref) for ref in rest)
            ),
            None,
        )
        if source is None or not shop_side:
            return None
        relation = _SHOP_RELATION
        if relation not in RELATIONS:
            return None

    ranking = request.ranking
    if ranking and ranking.order_by != measure_ref:
        return None

    # --- output contract ----------------------------------------------------
    fields: list[OutputField] = [_field(ref) for ref in dimensions]
    if not dimensions and ranking:
        # A listing-level ranking has to name the thing it ranked.
        fields.append(_field("dim.product_name", "product_name"))
    measure_name = "listing_count" if measure_ref == "derived.product_count" else measure_ref.split(".")[-1]
    fields.append(_field(measure_ref, measure_name))
    output = tuple(fields)

    scan_refs = tuple(dict.fromkeys(
        [ref for ref in (*dimensions, measure_ref) if ref != "derived.product_count"]
        + (["dim.product_name"] if (not dimensions and ranking) else [])
        + (["entity.product_listing"] if measure_ref == "derived.product_count" else [])
    ))
    scan_refs = tuple(ref for ref in scan_refs if not relation or _sources_of(ref) != {"shop_info_clean.csv"})

    predicates = [
        Predicate(ref="dim.country", op="eq", parameter="country", value=country),
        Predicate(ref="dim.date", op="eq", parameter="date", value=date),
    ]
    for index, item in enumerate(extra):
        obj = CATALOG.get(item.field_ref)
        if obj is None or item.op not in obj.allowed_filters:
            return None  # a predicate the catalog forbids is out of grammar
        predicates.append(Predicate(
            ref=item.field_ref, op=item.op,
            parameter=f"p{index}", value=item.value_binding,
        ))
    if measure_ref == "measure.price":
        # §4.8: never rank or aggregate a price without dropping the sentinel.
        predicates.append(Predicate(
            ref="measure.price", op="lt", parameter="price_sentinel", value=PRICE_SENTINEL,
        ))

    nodes: list[PlanNode] = [
        PlanNode(
            node_id="n1", op="Scan", source=source, refs=scan_refs,
            input_grain="listing_snapshot", output_grain="listing_snapshot",
            expected_schema=output, expected_cardinality="<=3341",
        ),
        PlanNode(
            node_id="n2", op="Filter", inputs=("n1",), predicates=tuple(predicates),
            input_grain="listing_snapshot", output_grain="listing_snapshot",
            expected_schema=output, expected_cardinality="<=3341",
        ),
    ]
    cursor = "n2"
    if relation:
        nodes.append(PlanNode(
            node_id="n3", op="Join", inputs=(cursor,), relation=relation,
            refs=tuple(ref for ref in (*dimensions,) if _sources_of(ref) == {"shop_info_clean.csv"}),
            input_grain="listing_snapshot", output_grain="listing_snapshot",
            expected_schema=output, expected_cardinality="<=3341",
        ))
        cursor = "n3"

    grain = "listing_snapshot"
    if dimensions or measure_ref == "derived.product_count":
        nodes.append(PlanNode(
            node_id="n4", op="Aggregate", inputs=(cursor,), refs=(measure_ref,),
            group_by=tuple(dimensions), aggregation=aggregation,
            input_grain="listing_snapshot",
            output_grain="group" if dimensions else "country_snapshot",
            expected_schema=output,
            expected_cardinality="<=3341" if dimensions else "1",
        ))
        cursor, grain = "n4", "group" if dimensions else "country_snapshot"

    if ranking:
        nodes.append(PlanNode(
            node_id="n5", op="Rank", inputs=(cursor,), rank_by=measure_ref,
            descending=ranking.direction == "desc", limit=ranking.top_k,
            input_grain=grain, output_grain=grain, expected_schema=output,
            expected_cardinality=f"<={ranking.top_k}",
        ))
        cursor = "n5"
    elif cursor in {"n2", "n3"}:
        nodes.append(PlanNode(
            node_id="n5", op="Project", inputs=(cursor,), refs=scan_refs,
            input_grain=grain, output_grain=grain, expected_schema=output,
            expected_cardinality="<=3341",
        ))
        cursor = "n5"

    direction = ranking.direction if ranking else "none"
    plan = LogicalQueryPlan(
        plan_id=(
            f"synth:{measure_ref}:{aggregation}:"
            f"{'+'.join(dimensions) or 'nogroup'}:{direction}:{country}:{date}:1.0"
        ),
        time_scope=(date,), output_node=cursor, requested_output_shape=output,
        nodes=tuple(nodes),
    )
    return SynthesisResult(
        plan=plan, grammar_path=plan.plan_id, aggregation=aggregation,
        dimensions=tuple(dimensions), relation=relation,
    )
