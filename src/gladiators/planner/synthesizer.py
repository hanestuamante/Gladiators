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

# W30: cận số dòng và cửa sổ ngày khai bằng KÝ HIỆU trên lịch snapshot, không
# bằng con số/ngày của một bản dữ liệu. Ghim cứng thì hằng số đúng trên bộ dữ
# liệu có mặt lúc viết và sai lặng lẽ trên bộ kế tiếp.
from gladiators.domain.calendar import full_window, latest_snapshot

import re
from dataclasses import dataclass
from typing import Literal, TypedDict, get_args

from gladiators.domain.catalog import (
    CATALOG,
    LABEL_REF_BY_UNIT,
    refusal_for_aggregation,
)
from gladiators.domain.metrics import approved_exclusion_predicates, METRICS
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


def _fold_for_guard(value: str) -> str:
    """Dạng đã normalize của một literal, để so với `normalized_question`."""
    from .semantic_parser import normalize

    return normalize(value)


def _has_unbound_qualifier(request: AnalyticalRequest) -> bool:
    """True when the question restricts something the request never bound."""
    text = f" {request.normalized_question} "
    bound = {predicate.field_ref for predicate in request.filters}

    # Một cụm đã thành GIÁ TRỊ của một chiều thì không còn là chữ tự do. Tên
    # shop "Bánh Kẹo Hải Hà - Chính hãng" chứa cụm "chính hãng"; nếu không xoá
    # nó khỏi văn bản, guard này thấy một điều kiện "chưa bind" và từ chối cả
    # câu — trong khi thứ nó thấy chỉ là một phần của cái TÊN mà request đã
    # bind hẳn hoi thành `dim.shop_name`.
    #
    # Đo được: cùng một câu hỏi giá trung bình, shop tên có "Chính hãng" bị
    # `A19-PLAN` còn shop tên không có thì trả lời bình thường — khác biệt nằm
    # ở TÊN, không ở câu hỏi.
    for predicate in request.filters:
        literal = predicate.value_binding
        if isinstance(literal, str) and len(literal) >= 4:
            folded = _fold_for_guard(literal)
            if folded and folded in text:
                text = text.replace(folded, " ")

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

# --- W12.1 · Lý do từ chối có kiểu -------------------------------------------
# 20 lối ``return None`` trong synthesize/_plan_relations/_choose_aggregation,
# mỗi lối một mã. Trước W12, một ca nhận A19-PLAN có ít nhất 21 nguyên nhân khả
# dĩ và trace thu hẹp được ĐÚNG 0 — mọi bảng chẩn đoán đều là kết quả của một
# phiên đọc code bằng tay, tức ảnh chụp chứ không phải cơ chế.
DeclineCode = Literal[
    # Hai lối từ chối thêm ở W-QUERY: cả hai đóng một SỐ 0 GIẢ, tức một câu trả
    # lời `allow` mang con số của một câu hỏi khác.
    "contradictory_equality",
    "multi_entity_comparison",
    "scope_ref_off_base", "no_entity_for_artifact", "relation_path_not_single_edge",
    "relation_left_source_mismatch", "relation_budget_exceeded", "temporal_validity",
    "no_certified_aggregation", "country_missing", "unbound_qualifier",
    "measure_count_not_one", "measure_not_in_catalog", "measure_not_answerable",
    "too_many_dimensions", "too_many_predicates", "aggregation_not_certified",
    "date_count_unsupported", "relation_plan_failed", "ranking_ref_mismatch",
    # W18: giá trị bind ĐƯỢC nhưng plan không diễn đạt NỔI nó — bộ chọn quan hệ
    # thêm một cạnh registry không khai. Tách khỏi `relation_plan_failed` (bộ
    # chọn bỏ cuộc) vì hai nguyên nhân khác nhau phải đọc khác nhau trong trace.
    "relation_grain_invalid",
    "filter_op_forbidden", "dedupe_policy_conflict",
]

DECLINE_CODES: frozenset[str] = frozenset(get_args(DeclineCode))

# Rule id theo mã, chọn theo priority ỔN ĐỊNH chứ không theo thứ tự tình cờ của
# nhánh: khi một lượt decline mang nhiều mã (vd. no_certified_aggregation rồi
# aggregation_not_certified), mã đứng trước trong tuple này quyết định rule.
DECLINE_RULE_PRIORITY: tuple[str, ...] = (
    # Đứng TRƯỚC mọi lý do khác: khi câu hỏi tự mâu thuẫn hoặc nêu hai thực thể,
    # mọi lý do phía sau đều là hệ quả, và nói ra hệ quả thay vì nguyên nhân là
    # đúng thứ `refusal_reason_accuracy` đo.
    "contradictory_equality",
    "multi_entity_comparison",
    "aggregation_not_certified",
    "no_certified_aggregation",
    "measure_not_answerable",
    "measure_not_in_catalog",
    "measure_count_not_one",
    "unbound_qualifier",
    "filter_op_forbidden",
    "ranking_ref_mismatch",
    "date_count_unsupported",
    "temporal_validity",
    "dedupe_policy_conflict",
    "relation_budget_exceeded",
    "relation_left_source_mismatch",
    "relation_path_not_single_edge",
    "no_entity_for_artifact",
    "scope_ref_off_base",
    "relation_plan_failed",
    "relation_grain_invalid",
    "too_many_dimensions",
    "too_many_predicates",
    "country_missing",
)

# Chỉ aggregation_not_certified có rule chuyên biệt (§17.1); phần còn lại là
# A19-PLAN cho tới khi có work package đặt tên riêng cho chúng.
DECLINE_RULE_BY_CODE: dict[str, str] = {
    code: ("A19-AGGREGATION" if code == "aggregation_not_certified" else "A19-PLAN")
    for code in DECLINE_CODES
}
# Hai lối từ chối của W-QUERY nói về THỰC THỂ, không về kế hoạch: câu hỏi nêu
# hai giá trị cho cùng một chiều, hoặc so sánh hai thực thể mà ngữ pháp phát
# hành chưa diễn đạt được. `A22-ALIGN-ENTITY` nói đúng trở ngại; `A19-PLAN`
# chung chung sẽ khiến người dùng diễn đạt lại và nhận đúng lời từ chối cũ.
DECLINE_RULE_BY_CODE["contradictory_equality"] = "A22-ALIGN-ENTITY"
DECLINE_RULE_BY_CODE["multi_entity_comparison"] = "A22-ALIGN-ENTITY"


class PlanningAttempt(TypedDict):
    """Một nhánh lập kế hoạch: đã thử chưa, và từ chối/không thử vì sao.

    ``tried=False`` bắt buộc kèm lý do trong ``declined`` — nhánh không chạy
    trông giống hệt nhánh chạy rồi thua, và đó chính là ca ans035: lời từ chối
    "không có provider" chỉ sai đường cho một synthesizer chưa bao giờ được thử.
    """

    branch: str
    tried: bool
    declined: list[str]


def _decline(collector: list[str] | None, code: str) -> None:
    """Ghi mã vào collector của CALLER. ``None`` ⇒ hành vi y hệt trước W12.

    Không tạo list con ở hàm trong rồi làm mất lý do: ``_plan_relations`` và
    ``_choose_aggregation`` nhận cùng một collector với ``synthesize``.
    """
    if collector is not None:
        collector.append(code)


def rule_for_declines(codes) -> str:
    """Rule id cho một tập mã, theo priority đã test — không theo thứ tự nhánh."""
    for code in DECLINE_RULE_PRIORITY:
        if code in codes:
            return DECLINE_RULE_BY_CODE[code]
    return "A19-PLAN"




@dataclass(frozen=True)
class _RelationPlan:
    source: str
    edges: tuple[str, ...]                     # tên quan hệ, đã sắp theo B5
    refs_by_edge: dict[str, tuple[str, ...]]   # ref mà mỗi cạnh mang về


def _plan_relations(
    needed: set[str], dimensions: tuple[str, ...], dates: tuple[str, ...],
    decline: list[str] | None = None,
) -> _RelationPlan | None:
    """B1–B5. ``None`` nghĩa là ngoài grammar — không nới để một câu vừa vặn."""
    # B1 · base phủ được nhiều ref nhất; hoà thì giữ thứ tự khai báo.
    def covered(candidate: str) -> int:
        return sum(1 for ref in needed if candidate in (_sources_of(ref) or {candidate}))

    source = max(_BASE_SOURCES, key=covered)
    for scope_ref in ("dim.country", "dim.date"):
        sources = _sources_of(scope_ref)
        if sources and source not in sources:
            _decline(decline, "scope_ref_off_base")
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
            _decline(decline, "no_entity_for_artifact")
            return None
        path = find_path("ProductListing", entity)
        if path is None or len(path) != 1:
            # Hình sao: mọi đường hợp lệ dài đúng 1. Dài hơn nghĩa là registry
            # đã đổi hình, và việc đó cần review chứ không cần code đoán.
            _decline(decline, "relation_path_not_single_edge")
            return None
        spec = path[0]
        if source not in RELATION_LEFT_SOURCES.get(spec.name, ()):
            _decline(decline, "relation_left_source_mismatch")
            return None
        chosen[spec.name] = tuple(refs)

    # B4 · ngân sách và tính hợp lệ thời gian
    if len(chosen) > RELATION_EDGE_BUDGET:
        _decline(decline, "relation_budget_exceeded")
        return None
    for name in chosen:
        spec = RELATIONS[name]
        if spec.temporal_validity == "static_latest_only" and (
            len(dates) > 1 or "dim.date" in dimensions
        ):
            _decline(decline, "temporal_validity")
            return None

    # B5 · thứ tự xác định, không phụ thuộc thứ tự dict
    order = tuple(sorted(
        chosen, key=lambda name: (RELATIONS[name].path_cost, RELATIONS[name].risk, name),
    ))
    return _RelationPlan(source, order, {name: chosen[name] for name in order})



def _field(ref: str, name: str | None = None, source: str | None = None) -> OutputField:
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
            # W25-R1: đơn vị phân tích chiếu NHÃN của nó, không chiếu khoá.
            # ``entity.shop.physical[0]`` là ``shop_id``; in nó ra là in một
            # định danh nội bộ cho người dùng đọc.
            #
            # Nhưng CHỈ khi cột nhãn có thật trên bảng nguồn của plan — cùng
            # luật với ``compiler._label_column_on``. ``product_snapshot_metrics``
            # có ``shop_id`` mà không có ``shop_name``; đổi tên chiếu ở đây mà
            # compiler không mang được cột sang là hai nửa của một luật lệch
            # nhau, và SQL sinh ra tham chiếu một cột chưa định nghĩa.
            label_ref = LABEL_REF_BY_UNIT.get(ref)
            label = CATALOG[label_ref] if label_ref else None
            if label is not None and source:
                prefix = source + "."
                label = label if any(
                    column.startswith(prefix) for column in label.physical
                ) else None
            name = (label or obj).physical[0].rsplit(".", 1)[1]
    return OutputField(
        name=name,
        type=_TYPE_BY_CATALOG_TYPE.get(obj.type, "string"),
        semantic_ref=ref,
    )


def _bound_refs(items) -> list[str]:
    return [item.ref for item in items if item.ref and not item.unresolved]



def _wants_scalar_aggregate(request: AnalyticalRequest) -> bool:
    """Câu hỏi một CON SỐ TỔNG HỢP trên toàn tập, không phải các DÒNG (W5.2).

    Chỉ True khi câu nêu TƯỜNG MINH một phép tổng hợp. Suy từ việc
    ``_choose_aggregation`` có trả về gì đó thì mọi câu xếp hạng cũng dính: hàm
    đó trả ``"median"`` như một giá trị MẶC ĐỊNH cho mọi measure, kể cả plan chỉ
    ``Rank`` các dòng — 6 trong 58 plan đang bị khoá có hình
    ``Scan→Filter→Rank``, và một node ``Aggregate`` ở đó sẽ gộp cả thị trường
    thành một dòng rồi xếp hạng chính nó.
    """
    return request.requested_aggregation is not None and request.ranking is None



def _share_definition(measure_ref: str):
    """ShareDefinition của một ref derived, nếu metric khai — W11.2."""
    if not measure_ref.startswith("derived."):
        return None
    spec = METRICS.get(measure_ref.split(".", 1)[1])
    return spec.share if spec is not None else None


def _choose_aggregation(
    measure_ref: str, request: AnalyticalRequest, decline: list[str] | None = None,
) -> str | None:
    """Pick an aggregation the catalog actually certifies for this measure.

    §5: ``sum(monthly_sold)`` is rejected because the catalog does not list it.
    A requested aggregation outside ``valid_aggregations`` is a refusal, never a
    silent substitution -- answering a mean question with a median is exactly the
    class of wrong answer this whole layer exists to stop.
    """
    allowed = CATALOG[measure_ref].valid_aggregations
    if not allowed:
        _decline(decline, "no_certified_aggregation")
        return None
    requested = request.requested_aggregation
    if requested is not None:
        # W5.1: yêu cầu một phép tính catalog chưa chứng nhận là một lời TỪ
        # CHỐI, không bao giờ là một phép thay thế. Trả lời câu hỏi trung bình
        # bằng trung vị đúng là lớp sai mà cả tầng này tồn tại để chặn.
        # Không ghi decline ở đây: caller ghi `aggregation_not_certified` ngay
        # khi hàm này trả None, và ghi hai lần trên cùng một đường làm hai lối
        # từ chối KHÁC NHAU trông giống nhau trong trace.
        # W26-R1 sinh LỜI GIẢI THÍCH ở workflow qua ``refusal_for_aggregation``,
        # không ở đây: chỗ này chỉ quyết định có phép nào dùng được không, và
        # ghi decline hai lần trên cùng một đường làm hai lối từ chối KHÁC NHAU
        # trông giống nhau trong trace.
        return requested if requested in allowed else None
    # Không nêu phép tính: giữ nguyên đường mặc định hôm nay, để plan_id của 58
    # plan đang bị khoá không đổi.
    if CATALOG[measure_ref].counts_unit:
        return "count" if "count" in allowed else None
    return "median" if "median" in allowed else allowed[0]




def _synthesize_window_count(
    request, country, measure_ref, dimensions, extra, dates, decline,
):
    """``COUNT(DISTINCT key)`` trên MỘT cửa sổ nhiều ngày — một truy vấn, không phải nhiều.

    Khác ``_synthesize_two_endpoint``: hàm kia so hai mốc và trả về ba số (đầu,
    cuối, chênh); hàm này trả về MỘT số cho cả cửa sổ. Hai hình dạng đó trả lời
    hai câu hỏi khác nhau, và trước đây câu thứ hai không có đường nào.

    Không group theo ngày: gom theo ngày rồi cộng lại chính là phép đếm trùng
    mà hàm này tồn tại để tránh.
    """
    counted_unit = CATALOG[measure_ref].counts_unit
    needed = {counted_unit or measure_ref, *dimensions,
              *(item.field_ref for item in extra), "dim.date"}
    plan_edges = _plan_relations(needed, dimensions, tuple(dates), decline=decline)
    if plan_edges is None:
        return None
    source = plan_edges.source
    base = measure_ref.rsplit(".", 1)[-1]
    output = (OutputField(name=base, type="number", semantic_ref=measure_ref),)

    predicates = [
        Predicate(ref="dim.country", op="eq", parameter="country", value=country),
        Predicate(ref="dim.date", op="in", parameter="dates", value=list(dates)),
    ]
    for index, item in enumerate(extra):
        obj = CATALOG.get(item.field_ref)
        if obj is None or item.op not in obj.allowed_filters:
            _decline(decline, "filter_op_forbidden")
            return None
        predicates.append(Predicate(
            ref=item.field_ref, op=item.op, parameter=f"p{index}",
            value=item.value_binding,
        ))

    # KHÔNG chiếu `dim.date`. Nó chỉ cần cho vị từ lọc, còn chiếu nó ra làm
    # mỗi dòng mang một ngày — và tầng evidence đọc đúng cột đó rồi khai con số
    # này "quan sát tại ngày X", trong khi nó nói về cả cửa sổ. A22 tin lời khai
    # và chặn một câu trả lời đúng.
    scan_refs = tuple(dict.fromkeys(
        [counted_unit or measure_ref, *dimensions]
    ))
    nodes = (
        PlanNode(node_id="n1", op="Scan", source=source, refs=scan_refs,
                 input_grain="listing_snapshot", output_grain="listing_snapshot",
                 expected_schema=output, expected_cardinality="<=snapshot_rows"),
        PlanNode(node_id="n2", op="Filter", inputs=("n1",),
                 predicates=tuple(predicates),
                 input_grain="listing_snapshot", output_grain="listing_snapshot",
                 expected_schema=output, expected_cardinality="<=snapshot_rows"),
        PlanNode(node_id="n3", op="Aggregate", inputs=("n2",),
                 refs=(measure_ref,), group_by=tuple(dimensions),
                 aggregation="count", input_grain="listing_snapshot",
                 output_grain="group", expected_schema=output,
                 expected_cardinality="1" if not dimensions else "<=snapshot_rows"),
    )
    plan = LogicalQueryPlan(
        plan_id=(
            f"synth:{measure_ref}:count:{'+'.join(dimensions) or 'nogroup'}:"
            f"none:{country}:{dates[0]}..{dates[-1]}:window:1.1"
        ),
        time_scope=tuple(dates), output_node="n3",
        requested_output_shape=output, nodes=nodes,
    )
    return SynthesisResult(
        plan=plan, grammar_path="window_count", aggregation="count",
        dimensions=tuple(dimensions), relations=(),
    )


def _synthesize_two_endpoint(
    request: AnalyticalRequest, country: str, measure_ref: str,
    dimensions: list[str], extra, dates: list[str], decline,
) -> SynthesisResult | None:
    """Plan hai đầu mút (W6.2). Bốn điều kiện ĐỀU bắt buộc; hụt cái nào ⇒ None.

    So hai mốc VÀ gom nhóm là hai chiều tự do — vượt grammar; join + temporal
    cùng lúc cũng vậy. Không plan cũ nào có hai mốc (hôm nay trả None), nên đây
    là MỞ RỘNG thuần: không entry baseline nào đổi.
    """
    if request.ranking is not None or dimensions:
        _decline(decline, "date_count_unsupported")
        return None
    aggregation = _choose_aggregation(measure_ref, request, decline=decline)
    if aggregation is None:
        _decline(decline, "aggregation_not_certified")
        return None
    counted_unit = CATALOG[measure_ref].counts_unit
    needed = {measure_ref, *(p.field_ref for p in extra)}
    if counted_unit:
        needed.discard(measure_ref)
    plan_edges = _plan_relations(needed, [], tuple(dates), decline=decline)
    if plan_edges is None or plan_edges.edges:
        # remote predicate / join + temporal vượt grammar.
        _decline(decline, "relation_plan_failed")
        return None
    source = plan_edges.source
    d0, d1 = dates
    base = measure_ref.rsplit(".", 1)[-1]

    intermediate = (
        OutputField(name="date", type="date", semantic_ref="dim.date"),
        OutputField(name=f"{base}_at_date", type="number", semantic_ref=measure_ref),
    )
    output = (
        OutputField(name=f"{base}_start", type="number", semantic_ref=measure_ref),
        OutputField(name=f"{base}_end", type="number", semantic_ref=measure_ref),
        OutputField(name=f"{base}_delta", type="number", semantic_ref=measure_ref),
    )

    predicates = [
        Predicate(ref="dim.country", op="eq", parameter="country", value=country),
        Predicate(ref="dim.date", op="in", parameter="dates", value=list(dates)),
    ]
    for index, item in enumerate(extra):
        obj = CATALOG.get(item.field_ref)
        if obj is None or item.op not in obj.allowed_filters:
            _decline(decline, "filter_op_forbidden")
            return None
        predicates.append(Predicate(
            ref=item.field_ref, op=item.op, parameter=f"p{index}",
            value=item.value_binding,
        ))
    for ref, op, value in approved_exclusion_predicates(measure_ref):
        predicates.append(Predicate(
            ref=ref, op=op, parameter="price_sentinel", value=value,
        ))

    scan_refs = tuple(dict.fromkeys(
        ([counted_unit] if counted_unit else [measure_ref]) + ["dim.date"]
    ))
    nodes = (
        PlanNode(node_id="n1", op="Scan", source=source, refs=scan_refs,
                 input_grain="listing_snapshot", output_grain="listing_snapshot",
                 expected_schema=intermediate, expected_cardinality="<=snapshot_rows"),
        PlanNode(node_id="n2", op="Filter", inputs=("n1",),
                 predicates=tuple(predicates),
                 input_grain="listing_snapshot", output_grain="listing_snapshot",
                 expected_schema=intermediate, expected_cardinality="<=snapshot_rows"),
        PlanNode(node_id="n4", op="Aggregate", inputs=("n2",),
                 refs=(measure_ref,), group_by=("dim.date",),
                 aggregation=aggregation, input_grain="listing_snapshot",
                 output_grain="date", expected_schema=intermediate,
                 expected_cardinality="2"),
        PlanNode(node_id="n6", op="TemporalCompare", inputs=("n4",),
                 refs=(measure_ref,), time_scope=(d0, d1),
                 input_grain="date", output_grain="country_window",
                 expected_schema=output, expected_cardinality="1"),
    )
    plan = LogicalQueryPlan(
        plan_id=f"synth:{measure_ref}:{aggregation}:temporal:none:{country}:{d0}..{d1}:norel:1.1",
        time_scope=(d0, d1), output_node="n6", requested_output_shape=output,
        nodes=nodes,
    )
    return SynthesisResult(
        plan=plan, grammar_path="two_endpoint_compare", aggregation=aggregation,
        dimensions=(), relations=(),
    )


def synthesize(
    request: AnalyticalRequest, country: str, *,
    decline: list[str] | None = None,
) -> SynthesisResult | None:
    """Build a plan for the release grammar, or ``None`` when out of grammar.

    ``decline`` là tham số RA tuỳ chọn (W12.1): mỗi lối ``return None`` ghi tên
    nó vào đây trước khi trả về. Không đổi kiểu trả về, vì 58 plan đang bị khoá
    bởi ``test_synthesizer_equivalence`` và mọi caller sẽ phải sửa. Caller không
    truyền ``decline`` nhận hành vi Y HỆT hôm nay — đó là điều kiện để W12 vào
    được trước W4–W11 mà không đụng vào chúng.
    """
    if not country:
        _decline(decline, "country_missing")
        return None  # country is mandatory; cross-market needs the decomposer
    if _has_unbound_qualifier(request):
        _decline(decline, "unbound_qualifier")
        return None
    # HAI GIÁ TRỊ `eq` TRÊN CÙNG MỘT CHIỀU LÀ MỘT MÂU THUẪN, KHÔNG PHẢI MỘT BỘ LỌC.
    #
    # "Giá trung bình của shop A **so với** shop B" bind hai predicate
    # `dim.shop_name eq A` và `dim.shop_name eq B`, rồi AND chúng lại. Không
    # dòng nào vừa thuộc A vừa thuộc B, nên plan chạy sạch sẽ và trả về 0 dòng —
    # và hệ nói `allow` kèm *"không có dòng nào thoả điều kiện"*.
    #
    # Đó là một SỐ 0 GIẢ: nó trông như một sự thật về dữ liệu (hai shop này
    # không có sản phẩm chung) trong khi sự thật là câu hỏi đã bị dịch sai. Mọi
    # lớp sau đều thấy hợp lệ — bộ lọc có chạy, evidence có thật, verifier khớp.
    #
    # Ngữ pháp phát hành chưa có phép so sánh nhiều thực thể, nên lối đúng là
    # TỪ CHỐI và nói ra điều đó, chứ không phải trả một con số của một câu hỏi
    # khác.
    _by_ref: dict[str, set] = {}
    for predicate in request.filters:
        if predicate.op == "eq":
            _by_ref.setdefault(predicate.field_ref, set()).add(
                str(predicate.value_binding),
            )
    if any(len(values) > 1 for values in _by_ref.values()):
        _decline(decline, "contradictory_equality")
        return None
    # SO SÁNH HAI THỰC THỂ chưa có trong ngữ pháp phát hành, và nó KHÔNG tự lộ
    # ra thành hai predicate. "Giá TB của shop A **so với** shop B" chỉ bind
    # được MỘT tên; chữ của tên còn lại nằm lại trong câu và bị đọc thành điều
    # kiện — ở ca đo được, "Nestlé **Chính hãng**" sinh ra
    # `dim.shop_official = True`, và Richy không phải official shop, nên plan
    # trả 0 dòng rồi hệ nói `allow` kèm "không có dòng nào thoả điều kiện".
    #
    # Lại là một SỐ 0 GIẢ, và lần này nguy hơn: nó trông như một sự thật về hai
    # shop, trong khi thứ hỏng là câu hỏi đã bị dịch thành một câu khác. Có cụm
    # so sánh + có một bộ lọc giá trị ⇒ TỪ CHỐI, để A22 nói đúng trở ngại.
    _comparison_cue = any(
        cue in request.normalized_question
        for cue in ("so voi", "so sanh", "doi chieu", "hay shop", "hay cua hang",
                    "versus", " vs ", "compared to", "dibandingkan")
    )
    if _comparison_cue and any(
        predicate.field_ref not in ("dim.country", "dim.date")
        and isinstance(predicate.value_binding, str)
        for predicate in request.filters
    ):
        _decline(decline, "multi_entity_comparison")
        return None

    measures = _bound_refs(request.requested_measures)
    if len(measures) != 1:
        _decline(decline, "measure_count_not_one")
        return None
    measure_ref = measures[0]
    if measure_ref not in CATALOG:
        _decline(decline, "measure_not_in_catalog")
        return None
    if CATALOG[measure_ref].answerability in {"absent", "context_only"}:
        _decline(decline, "measure_not_answerable")
        return None

    # A unit of analysis carries no column to GROUP BY. Keeping it here produced a
    # plan the validator accepted and the compiler could not build.
    dimensions = [
        ref for ref in _bound_refs(request.requested_dimensions)
        if ref not in SCOPE_REFS and CATALOG[ref].physical
    ]
    dimensions = list(dict.fromkeys(dimensions))
    if len(dimensions) > MAX_DIMENSIONS:
        _decline(decline, "too_many_dimensions")
        return None

    extra = [p for p in request.filters if p.field_ref not in SCOPE_REFS]
    if len(extra) > MAX_EXTRA_PREDICATES:
        _decline(decline, "too_many_predicates")
        return None

    aggregation = _choose_aggregation(measure_ref, request, decline=decline)
    if aggregation is None:
        _decline(decline, "aggregation_not_certified")
        return None

    dates = tuple(request.time_scope.dates) if request.time_scope else ()
    if len(dates) == 2:
        # W6.2 — so hai mốc là một hình plan riêng, đủ điều kiện mới nhận.
        return _synthesize_two_endpoint(
            request, country, measure_ref, dimensions, extra,
            sorted(dates), decline,
        )
    if len(dates) != 1:
        # NGOẠI LỆ CÓ CƠ SỞ, không phải nới luật. Luật ngay dưới đúng cho phép
        # gộp: lấy trung bình/trung vị qua nhiều snapshot là trộn nhiều lát cắt
        # thành một con số không ai kiểm được. Nhưng ĐẾM PHÂN BIỆT tự khử trùng
        # theo định nghĩa — `COUNT(DISTINCT k)` trên 5 ngày đếm mỗi k đúng một
        # lần, đúng bằng thứ câu hỏi yêu cầu.
        #
        # Hai ca đo được mà nó mở ra, cả hai đều KHÔNG bẻ câu được:
        #   "shop X xuất hiện trong bao nhiêu ngày"  → COUNT(DISTINCT date) = 18
        #   "có bao nhiêu listing từ 1/7 đến 5/7"    → COUNT(DISTINCT key) = 701
        # Bẻ ra rồi cộng lại cho ra 3283 — đúng số học, sai câu hỏi (f1a1258).
        # Chúng cần MỘT truy vấn, không phải nhiều truy vấn cộng lại.
        if aggregation == "count" and CATALOG[measure_ref].counts_unit:
            return _synthesize_window_count(
                request, country, measure_ref, dimensions, extra,
                sorted(dates), decline,
            )
        # Multi-snapshot aggregation is a decomposition question (§8.6
        # union_scope), not something to average over silently.
        _decline(decline, "date_count_unsupported")
        return None
    date = dates[0]

    # --- source and relation ------------------------------------------------
    counted_unit = CATALOG[measure_ref].counts_unit
    share = _share_definition(measure_ref)
    needed = {measure_ref, *dimensions, *(p.field_ref for p in extra)}
    # GIỚI HẠN ĐÃ BIẾT của W25, ghi ra thay vì để người sau tự phát hiện:
    # nhãn chỉ chiếu được khi nó có cột trên CHÍNH bảng nguồn của plan.
    # ``product_snapshot_metrics.csv`` có ``shop_id`` mà không có ``shop_name``,
    # nên plan sinh từ nó vẫn chiếu khoá. Ba lối đã thử và vì sao bỏ:
    #   * ép nhãn thành một ref plan phải phủ ⇒ bộ chọn quan hệ thêm cạnh
    #     ``has_sales_metric`` và plan ra INVALID ("grain Join không khớp",
    #     "fanout thiếu dedupe") — đổi một chỗ rò lấy một plan không chạy được;
    #   * thêm ``shop_name`` vào artifact snapshot_metrics ⇒ đổi
    #     ``dataset_version`` của bộ đóng băng, tức phá một bất biến;
    #   * bật W25-R2 (validator chặn định danh nội bộ) ⇒ biến một câu hỏi TRẢ
    #     LỜI ĐƯỢC thành một lời từ chối.
    # Nên W25 đóng chỗ rò ở mọi plan sinh từ ``products_clean.csv`` (gồm ca
    # h0038 mà nó tồn tại để đóng) và KHÔNG đóng ở nhánh snapshot_metrics.
    if counted_unit:
        needed.discard(measure_ref)  # counted, not scanned
    if share is not None:
        # W11.2 §12.3.1: rate ref không có physical — closure thay nó bằng
        # condition_ref và counting key của mẫu số.
        needed.discard(measure_ref)
        needed.add(share.condition_ref)
    plan_edges = _plan_relations(needed, dimensions, (date,), decline=decline)
    if plan_edges is None:
        _decline(decline, "relation_plan_failed")
        return None
    source = plan_edges.source
    relations = plan_edges.edges

    ranking = request.ranking
    if ranking and ranking.order_by != measure_ref:
        _decline(decline, "ranking_ref_mismatch")
        return None

    # --- output contract ----------------------------------------------------
    fields: list[OutputField] = [_field(ref, source=source) for ref in dimensions]
    if not dimensions and ranking:
        # A listing-level ranking has to name the thing it ranked.
        fields.append(_field("dim.product_name", "product_name"))
    if share is not None:
        # Thứ tự cố định của hợp đồng share: tử số, mẫu số, tỷ lệ.
        fields.append(_field(f"derived.{share.numerator_metric}", share.numerator_metric))
        fields.append(_field(f"derived.{share.denominator_metric}", share.denominator_metric))
        fields.append(_field(measure_ref, measure_ref.split(".")[-1]))
    else:
        measure_name = "listing_count" if measure_ref == "derived.product_count" else measure_ref.split(".")[-1]
        fields.append(_field(measure_ref, measure_name))
    output = tuple(fields)

    scan_refs = tuple(dict.fromkeys(
        [ref for ref in (*dimensions, measure_ref)
         if (not counted_unit or ref != measure_ref) and (share is None or ref != measure_ref)]
        + (["dim.product_name"] if (not dimensions and ranking) else [])
        + ([counted_unit] if counted_unit else [])
        # Share: quét cờ điều kiện và đơn vị đếm, nhưng KHÔNG project chúng ra
        # output cuối — output là hợp đồng ba ref tử/mẫu/tỷ lệ.
        + ([share.condition_ref, "entity.product_listing"] if share is not None else [])
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
            _decline(decline, "filter_op_forbidden")
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
    # W14.2: luật đã DUYỆT của BẤT KỲ measure nào đều thành predicate, theo cùng
    # một đường. Trước đây một measure được bảo vệ bằng một câu `if` còn tám
    # measure kia không, và không ai thấy sự chênh đó vì nó không phải một hàng
    # trong bảng. Measure chưa khai luật nào thì không có predicate nào — y hệt
    # hôm nay, nên không measure nào đổi hành vi vì bản thân thay đổi này.
    for ref, op, value in approved_exclusion_predicates(measure_ref):
        predicates.append(Predicate(
            ref=ref, op=op, parameter="price_sentinel", value=value,
        ))

    nodes: list[PlanNode] = [
        PlanNode(
            node_id="n1", op="Scan", source=source, refs=scan_refs,
            input_grain="listing_snapshot", output_grain="listing_snapshot",
            expected_schema=output, expected_cardinality="<=snapshot_rows",
        ),
        PlanNode(
            node_id="n2", op="Filter", inputs=("n1",), predicates=tuple(predicates),
            input_grain="listing_snapshot", output_grain="listing_snapshot",
            expected_schema=output, expected_cardinality="<=snapshot_rows",
        ),
    ]
    cursor = "n2"
    for index, name in enumerate(relations):
        spec = RELATIONS[name]
        node_id = "n3" if index == 0 else f"n3_{index + 1}"
        # Grain và dedupe ĐỌC TỪ REGISTRY, không viết cứng. Bản cũ khai
        # `listing_snapshot → listing_snapshot` cho MỌI cạnh và không khai
        # `dedupe_policy` bao giờ — mà validator so đúng hai thứ đó với registry
        # (`grain_mismatch`, `fanout_risk`). Bốn cạnh left_join khai bốn cặp
        # khác nhau, nên chỉ `belongs_to` tình cờ khớp và ba cạnh còn lại KHÔNG
        # BAO GIỜ dựng nổi plan hợp lệ:
        #
        #   belongs_to            listing_snapshot → listing_snapshot        (khớp)
        #   in_platform_category  listing_snapshot → listing_snapshot_category
        #   in_shop_category      listing_snapshot → listing_snapshot_x_shelf
        #   has_sales_metric      listing          → listing_snapshot_or_transition
        #
        # Đó là lý do thật của ba lần thử hỏng ghi trong comment W25 ("grain
        # Join không khớp", "fanout thiếu dedupe") — không phải một giới hạn của
        # dữ liệu, mà là plan tự khai sai về chính cạnh nó dùng.
        nodes.append(PlanNode(
            node_id=node_id, op="Join", inputs=(cursor,), relation=name,
            refs=plan_edges.refs_by_edge[name],
            input_grain=spec.input_grain, output_grain=spec.output_grain,
            dedupe_policy=(
                spec.dedupe_strategy if spec.fanout_effect != "none" else None
            ),
            expected_schema=output, expected_cardinality="<=snapshot_rows",
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
            _decline(decline, "dedupe_policy_conflict")
            return None
        nodes.append(PlanNode(
            node_id="nd", op="Dedupe", inputs=(cursor,),
            dedupe_policy=fanout[0].dedupe_strategy,
            input_grain="listing_snapshot", output_grain="listing_snapshot",
            expected_schema=output, expected_cardinality="<=snapshot_rows",
        ))
        cursor = "nd"

    if remote_predicates:
        nodes.append(PlanNode(
            node_id="nf2", op="Filter", inputs=(cursor,),
            predicates=tuple(remote_predicates),
            input_grain="listing_snapshot", output_grain="listing_snapshot",
            expected_schema=output, expected_cardinality="<=snapshot_rows",
        ))
        cursor = "nf2"

    grain = "listing_snapshot"
    if dimensions or counted_unit or _wants_scalar_aggregate(request):
        nodes.append(PlanNode(
            node_id="n4", op="Aggregate", inputs=(cursor,), refs=(measure_ref,),
            group_by=tuple(dimensions), aggregation=aggregation,
            input_grain="listing_snapshot",
            output_grain="group" if dimensions else "country_snapshot",
            expected_schema=output,
            expected_cardinality="<=snapshot_rows" if dimensions else "1",
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
            expected_cardinality="<=snapshot_rows",
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
    # Một giá trị bind được KHÔNG có nghĩa là plan diễn đạt được nó. Khi ref của
    # predicate không nằm trên bảng nguồn, bộ chọn quan hệ thêm một cạnh mà
    # registry không khai — plan ra `grain_mismatch`/`fanout_risk` và chỉ nổ ở
    # compiler. Chặn ở đây, và HẸP: chỉ ba mã về QUAN HỆ.
    #
    # Không chặn mọi mã: `wrong_filter` (invariant sentinel) đã tồn tại trên một
    # số plan TRƯỚC work package này, và chặn nó ở đây là lấy đi một plan mà
    # commit này không hề đụng tới.
    from .validator import validate_plan

    relation_issues = {"grain_mismatch", "fanout_risk", "wrong_join_path"}
    verdict = validate_plan(plan)
    if any(issue.code in relation_issues for issue in verdict.issues):
        _decline(decline, "relation_grain_invalid")
        return None
    return SynthesisResult(
        plan=plan, grammar_path=plan.plan_id, aggregation=aggregation,
        dimensions=tuple(dimensions), relations=relations,
    )


def has_unbound_condition_marker(request: AnalyticalRequest) -> bool:
    """Chỉ marker ĐIỀU KIỆN chưa bind, KHÔNG tính nhánh mã sản phẩm.

    ``_has_unbound_qualifier`` gộp cả hai: điều kiện chưa bind và câu nêu một mã
    listing cụ thể. Nhánh mã đã có lối từ chối riêng của nó (A22, khoá bởi ca
    TC39), nên phép kiểm ở tầng template phải hẹp hơn — nếu không nó cướp mất
    một chẩn đoán đang đúng.
    """
    text = f" {request.normalized_question} "
    bound = {predicate.field_ref for predicate in request.filters}
    for surface in sorted(_QUALIFIER_MARKER_REF, key=len, reverse=True):
        if _QUALIFIER_MARKER_REF[surface] in bound and surface in text:
            text = text.replace(surface, " ")
    for marker in _UNBOUND_QUALIFIER_MARKERS:
        if f" {marker} " not in text and not text.rstrip().endswith(f" {marker}"):
            continue
        ref = _QUALIFIER_MARKER_REF.get(marker)
        if ref is not None and ref in bound:
            continue
        return True
    return False


# Ref mà MỌI template đã chứng nhận đều diễn đạt được. Bất cứ predicate nào nằm
# ngoài tập này mà rơi vào đường template sẽ bị BỎ ÂM THẦM.
TEMPLATE_EXPRESSIBLE_REFS = frozenset({"dim.country", "dim.date"})


def unexpressible_filters(request: AnalyticalRequest) -> tuple[str, ...]:
    """Predicate ĐÃ BIND mà template không có chỗ diễn đạt.

    Bổ đôi với ``has_unbound_condition_marker``: hàm kia bắt điều kiện chưa
    bind được, hàm này bắt điều kiện ĐÃ bind mà đường template làm rơi mất.

    Ca đã đo (tìm ra bằng kiểm biến hình, WP-B7): "Số lượng listing đã xác minh
    tại Indonesia ngày 03/07 là bao nhiêu?" bind đúng
    ``dim.shopee_verified = True``, nhưng câu không khớp surface measure nào nên
    bộ sinh kế hoạch bỏ cuộc, template đếm-tất-cả tiếp quản, và hệ trả **474**
    thay vì **3** — một con số sai, không kèm tín hiệu nào. Cùng câu hỏi diễn đạt
    kiểu "Có bao nhiêu listing đã xác minh…?" trả đúng 3.
    """
    if request is None:
        return ()
    return tuple(sorted({
        predicate.field_ref for predicate in request.filters
        if predicate.field_ref not in TEMPLATE_EXPRESSIBLE_REFS
    }))
