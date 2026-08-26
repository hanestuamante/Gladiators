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
    × 0..N certified relation (A1.4, tối đa RELATION_EDGE_BUDGET)

Anything outside the grammar returns ``None`` so the caller can fall through to
the decomposer or ``A-CAPABILITY-MISS``.  The grammar is never widened to make a
question fit -- that is the rule which keeps this from becoming a second,
sloppier planner.  Every plan still goes through the existing validator,
compiler and executor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from gladiators.domain.catalog import CATALOG
from gladiators.domain.qualifiers import QUALIFIERS
from gladiators.domain.relations import (
    ENTITY_BY_RIGHT_SOURCE,
    RELATION_LEFT_SOURCES,
    find_path,
)
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


# Words that restrict a question but that the deterministic parser does not bind
# into a predicate.  Their presence means the request object is a *lossy* summary
# of what was asked, so synthesising from it would silently widen the question:
#
#   "listing của shop official tại VN"   -> counts for all 20 shops, not the 7 official ones
#   "Rating theo brand không tồn tại"    -> all 31 brands instead of an empty result
#
# The guard is deliberately one-directional: an unrecognised qualifier can only
# ever make the synthesizer decline, never make it answer. False declines fall
# through to templates or the planner; a false accept would be a wrong number.
_ITEM_ID = re.compile(r"\d{8,}")

# WP-A4.4: marker của điều kiện SINH TỪ registry, không giữ bản thứ hai ở đây.
# Marker của một điều kiện đã bind được sẽ tự rời khỏi guard khi registry đổi —
# trước đây phải nhớ sửa hai chỗ, và hai danh sách thì sẽ lệch nhau.
_QUALIFIER_MARKER_REF: dict[str, str] = {
    surface: spec.ref
    for spec in QUALIFIERS
    for surface in spec.surfaces + spec.negations
}
# Marker CHƯA có ref nào bind được. Chúng ở lại nguyên trong phần literal dư —
# đó chính là lý do guard vẫn phải tồn tại sau WP-A4.
_LITERAL_QUALIFIER_MARKERS = (
    "khong", "chua", "chi rieng", "rieng", "ngoai tru", "tru",
    "verified", "sold out", "het hang",
)
_UNBOUND_QUALIFIER_MARKERS = tuple(_QUALIFIER_MARKER_REF) + _LITERAL_QUALIFIER_MARKERS


class SynthesisError(ValueError):
    pass


def _has_unbound_qualifier(request: AnalyticalRequest) -> bool:
    """True when the question restricts something the request never bound."""
    text = f" {request.normalized_question} "
    bound = {predicate.field_ref for predicate in request.filters}

    # §A4.4: khớp một điều kiện thì XOÁ span đó khỏi văn bản còn lại. Không xoá
    # thì marker phủ định trần ("khong") vẫn bắn cho câu "shop KHÔNG CHÍNH HÃNG"
    # — dù mệnh đề phủ định đó đã trở thành predicate hẳn hoi. Guard sẽ chặn một
    # câu mà chính nó vừa xác nhận là bind được.
    # Dài trước: xoá "chinh hang" trước "khong chinh hang" sẽ để lại "khong"
    # trần, và marker phủ định chung đó lại bắn cho đúng câu vừa bind được.
    for surface in sorted(_QUALIFIER_MARKER_REF, key=len, reverse=True):
        if _QUALIFIER_MARKER_REF[surface] in bound and surface in text:
            text = text.replace(surface, " ")

    # A question naming a specific listing/shop id is asking about that row. The
    # grammar has no way to bind an id, so synthesising would answer about the
    # whole market instead -- tc39 asks about item 26663401389 and would have got
    # a market-wide aggregate.
    if _ITEM_ID.search(text) and not any(
        isinstance(predicate.value_binding, str) and _ITEM_ID.fullmatch(predicate.value_binding)
        for predicate in request.filters
    ):
        return True

    for marker in _UNBOUND_QUALIFIER_MARKERS:
        if f" {marker} " not in text and not text.rstrip().endswith(f" {marker}"):
            continue
        # Guard vẫn MỘT CHIỀU: một điều kiện chỉ ngừng chặn khi nó THẬT SỰ đã
        # trở thành predicate. Không có đường nào để điều kiện chưa bind lọt qua.
        ref = _QUALIFIER_MARKER_REF.get(marker)
        if ref is not None and ref in bound:
            continue
        return True
    return False


@dataclass(frozen=True)
class SynthesisResult:
    plan: LogicalQueryPlan
    grammar_path: str
    aggregation: str | None
    dimensions: tuple[str, ...]
    # A1.4: một plan có thể đi nhiều nan hoa; giữ tên số ít sẽ buộc caller
    # đoán xem cạnh nào là 'cái' quan hệ.
    relations: tuple[str, ...]


def _sources_of(ref: str) -> set[str]:
    obj = CATALOG.get(ref)
    if obj is None or not obj.physical:
        return set()
    return {column.split(".csv")[0] + ".csv" for column in obj.physical}

# --- A1.4 · RelationPlanner -------------------------------------------------
# Đồ thị quan hệ là HÌNH SAO: mọi cạnh toả ra từ tâm ProductListing. Bài toán vì
# thế không phải tìm đường dài, mà là hợp nhất nhiều nan hoa và khử trùng lặp
# đúng cách. Toàn bộ thuật toán deterministic, không cần LLM.
RELATION_EDGE_BUDGET = 3


@dataclass(frozen=True)
class _RelationPlan:
    source: str
    edges: tuple[str, ...]                     # tên quan hệ, đã sắp theo B5
    refs_by_edge: dict[str, tuple[str, ...]]   # ref mà mỗi cạnh mang về


def _plan_relations(
    needed: set[str], dimensions: tuple[str, ...], dates: tuple[str, ...],
) -> _RelationPlan | None:
    """B1–B5. ``None`` nghĩa là ngoài grammar — không nới để một câu vừa vặn."""
    # B1 · base phủ được nhiều ref nhất; hoà thì giữ thứ tự khai báo.
    def covered(candidate: str) -> int:
        return sum(1 for ref in needed if candidate in (_sources_of(ref) or {candidate}))

    source = max(_BASE_SOURCES, key=covered)
    for scope_ref in ("dim.country", "dim.date"):
        sources = _sources_of(scope_ref)
        if sources and source not in sources:
            return None

    # B2 · gom ref còn thiếu theo artifact
    remote: dict[str, list[str]] = {}
    for ref in sorted(needed):
        sources = _sources_of(ref)
        if not sources or source in sources:
            continue
        artifact = sorted(sources)[0]
        remote.setdefault(artifact, []).append(ref)
    if not remote:
        return _RelationPlan(source, (), {})

    # B3 · mỗi artifact đúng một cạnh từ tâm
    chosen: dict[str, tuple[str, ...]] = {}
    for artifact, refs in remote.items():
        entity = ENTITY_BY_RIGHT_SOURCE.get(artifact)
        if entity is None:
            return None
        path = find_path("ProductListing", entity)
        if path is None or len(path) != 1:
            # Hình sao: mọi đường hợp lệ dài đúng 1. Dài hơn nghĩa là registry
            # đã đổi hình, và việc đó cần review chứ không cần code đoán.
            return None
        spec = path[0]
        if source not in RELATION_LEFT_SOURCES.get(spec.name, ()):
            return None
        chosen[spec.name] = tuple(refs)

    # B4 · ngân sách và tính hợp lệ thời gian
    if len(chosen) > RELATION_EDGE_BUDGET:
        return None
    for name in chosen:
        spec = RELATIONS[name]
        if spec.temporal_validity == "static_latest_only" and (
            len(dates) > 1 or "dim.date" in dimensions
        ):
            return None

    # B5 · thứ tự xác định, không phụ thuộc thứ tự dict
    order = tuple(sorted(
        chosen, key=lambda name: (RELATIONS[name].path_cost, RELATIONS[name].risk, name),
    ))
    return _RelationPlan(source, order, {name: chosen[name] for name in order})



def _field(ref: str, name: str | None = None) -> OutputField:
    """Name a projected column the way the compiler and templates already do.

    Dimensions and entities carry their physical column name -- ``entity.shop``
    is ``shop_id``, not ``shop`` -- because the compiler aliases group-by columns
    from the catalog mapping and the executor checks the result columns against
    ``expected_columns`` exactly.  Measures keep the friendly ref suffix
    (``measure.price`` → ``price``, not ``price_num``), matching the certified
    templates and the evidence metric names downstream.
    """
    obj = CATALOG[ref]
    if name is None:
        name = ref.split(".")[-1]
        if obj.kind in {"dimension", "entity"} and obj.physical:
            name = obj.physical[0].rsplit(".", 1)[1]
    return OutputField(
        name=name,
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
    if CATALOG[measure_ref].counts_unit:
        return "count" if "count" in allowed else None
    return "median" if "median" in allowed else allowed[0]


def synthesize(request: AnalyticalRequest, country: str) -> SynthesisResult | None:
    """Build a plan for the release grammar, or ``None`` when out of grammar."""
    if not country:
        return None  # country is mandatory; cross-market needs the decomposer
    if _has_unbound_qualifier(request):
        return None

    measures = _bound_refs(request.requested_measures)
    if len(measures) != 1:
        return None
    measure_ref = measures[0]
    if measure_ref not in CATALOG:
        return None
    if CATALOG[measure_ref].answerability in {"absent", "context_only"}:
        return None

    # A unit of analysis carries no column to GROUP BY. Keeping it here produced a
    # plan the validator accepted and the compiler could not build.
    dimensions = [
        ref for ref in _bound_refs(request.requested_dimensions)
        if ref not in SCOPE_REFS and CATALOG[ref].physical
    ]
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
    counted_unit = CATALOG[measure_ref].counts_unit
    needed = {measure_ref, *dimensions, *(p.field_ref for p in extra)}
    if counted_unit:
        needed.discard(measure_ref)  # counted, not scanned
    plan_edges = _plan_relations(needed, dimensions, (date,))
    if plan_edges is None:
        return None
    source = plan_edges.source
    relations = plan_edges.edges

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
        [ref for ref in (*dimensions, measure_ref) if not counted_unit or ref != measure_ref]
        + (["dim.product_name"] if (not dimensions and ranking) else [])
        + ([counted_unit] if counted_unit else [])
    ))
    remote_refs = {ref for refs in plan_edges.refs_by_edge.values() for ref in refs}
    scan_refs = tuple(ref for ref in scan_refs if ref not in remote_refs)

    predicates = [
        Predicate(ref="dim.country", op="eq", parameter="country", value=country),
        Predicate(ref="dim.date", op="eq", parameter="date", value=date),
    ]
    # A1.4 · nF2: không thể lọc theo `dim.shop_official` TRƯỚC khi join sang
    # shop_info. Tách predicate làm hai nhóm là bắt buộc, không phải tối ưu —
    # đặt nhầm nhóm làm bộ lọc rơi âm thầm và trả về toàn bộ thị trường.
    remote_predicates: list[Predicate] = []
    for index, item in enumerate(extra):
        obj = CATALOG.get(item.field_ref)
        if obj is None or item.op not in obj.allowed_filters:
            return None  # a predicate the catalog forbids is out of grammar
        predicate = Predicate(
            ref=item.field_ref, op=item.op,
            parameter=f"p{index}", value=item.value_binding,
        )
        sources = _sources_of(item.field_ref)
        if sources and plan_edges.source not in sources:
            remote_predicates.append(predicate)
        else:
            predicates.append(predicate)
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
    for index, name in enumerate(relations):
        spec = RELATIONS[name]
        node_id = "n3" if index == 0 else f"n3_{index + 1}"
        nodes.append(PlanNode(
            node_id=node_id, op="Join", inputs=(cursor,), relation=name,
            refs=plan_edges.refs_by_edge[name],
            input_grain="listing_snapshot", output_grain="listing_snapshot",
            expected_schema=output, expected_cardinality="<=3341",
        ))
        cursor = node_id

    # Dedupe khi bất kỳ cạnh nào nhân bản dòng trái. INV-DEDUPE-BEFORE-AGGREGATE
    # đã khai sẵn và validator đã kiểm; việc còn thiếu chỉ là chèn node.
    fanout = [RELATIONS[name] for name in relations if RELATIONS[name].fanout_effect != "none"]
    if fanout:
        policies = {spec.dedupe_strategy for spec in fanout}
        if len(policies) > 1:
            # Hai chiến lược khử trùng lặp khác nhau trong một plan: chọn một
            # cái là quyết định thay người về grain nào được giữ.
            return None
        nodes.append(PlanNode(
            node_id="nd", op="Dedupe", inputs=(cursor,),
            dedupe_policy=fanout[0].dedupe_strategy,
            input_grain="listing_snapshot", output_grain="listing_snapshot",
            expected_schema=output, expected_cardinality="<=3341",
        ))
        cursor = "nd"

    if remote_predicates:
        nodes.append(PlanNode(
            node_id="nf2", op="Filter", inputs=(cursor,),
            predicates=tuple(remote_predicates),
            input_grain="listing_snapshot", output_grain="listing_snapshot",
            expected_schema=output, expected_cardinality="<=3341",
        ))
        cursor = "nf2"

    grain = "listing_snapshot"
    if dimensions or counted_unit:
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
            # A1.5: thêm đoạn quan hệ. Không consumer nào parse `synth:` theo vị
            # trí (analytics/tools.py chỉ parse tiền tố `analytical:`), nên đây
            # là thay đổi additive.
            f"{'+'.join(dimensions) or 'nogroup'}:{direction}:{country}:{date}:"
            f"{'+'.join(relations) or 'norel'}:1.1"
        ),
        time_scope=(date,), output_node=cursor, requested_output_shape=output,
        nodes=tuple(nodes),
    )
    return SynthesisResult(
        plan=plan, grammar_path=plan.plan_id, aggregation=aggregation,
        dimensions=tuple(dimensions), relations=relations,
    )
