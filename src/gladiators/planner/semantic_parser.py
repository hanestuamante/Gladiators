"""P7 AnalyticalRequest contract, catalog slicing và deterministic fallback."""
from __future__ import annotations

from .predicate_ops import ExecutablePredicateOp, canonicalize_predicate_op
from .query_ir import Aggregation

import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from rapidfuzz import fuzz

from gladiators.domain.alias_index import (
    PREFERRED_REF_BY_SURFACE,
    compound_shadowed,
    default_alias_index,
)
from gladiators.domain.catalog import CATALOG, CatalogObject, COUNT_METRIC_BY_SURFACE_REF
from gladiators.domain.qualifiers import match as qualifier_match

# Wordings that make the noun beside them the thing being counted rather than a
# key to group by.
_COUNTING_CUES = ("nhieu nhat", "terbanyak", "most", "bao nhieu", "nhieu san pham", "berapa")

_DATE_ISO = re.compile(r"2026-07-0[1-3]")
_DATE_DAY_MONTH = re.compile(r"(?<![0-9])0?([123])\s*/\s*0?7(?![0-9])")


def extract_date_range(normalized: str) -> list[str]:
    """Return ``[start, end]`` for the snapshot dates named in a normalised text.

    The dataset holds only 2026-07-01..03, so ``2026-07-01`` and the colloquial
    ``01/07`` denote the same snapshot.  A single named date yields ``[d, d]``:
    asking for 01/07 and being handed the 03/07 snapshot is a wrong answer, not
    a defensible default.  Lives here rather than in ``agent.parser`` so both the
    intent parser and the plan synthesizer read dates the same way.
    """
    dates = list(_DATE_ISO.findall(normalized))
    dates += [f"2026-07-0{day}" for day in _DATE_DAY_MONTH.findall(normalized)]
    ordered = sorted(dict.fromkeys(dates))
    return [ordered[0], ordered[-1]] if ordered else []


def normalize(value: str) -> str:
    value = value.lower().replace("đ", "d")
    value = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s:/._-]", " ", value)).strip()


class SemanticBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    surface_text: str
    ref: str | None = None
    unresolved: bool = False
    reason: Literal["catalog_gap", "metric_ungoverned", "data_absent", "unknown"] | None = None


class EntityBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    surface_text: str
    entity_type: Literal["listing", "shop", "brand", "category", "shelf"]
    resolved_key: str | None = None
    candidates: tuple[str, ...] = ()
    status: Literal["resolved", "ambiguous", "unresolved"] = "unresolved"


class AnalyticalPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_ref: str
    # W11.1: dùng CHUẨN chung với IR và catalog. ``le/ge`` từ payload cũ được
    # canonicalize ở biên; ``between``/``isnull`` không còn là op của model —
    # between phải tách gte+lte trước khi dựng, isnull đi lối A19-OP.
    op: ExecutablePredicateOp
    value_binding: Any

    @field_validator("op", mode="before")
    @classmethod
    def _canonicalize(cls, value: str) -> str:
        return canonicalize_predicate_op(str(value))


class AnalyticalTimeScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dates: tuple[str, ...]
    mode: Literal["single_snapshot", "transition", "all_with_caveat"]


class AnalyticalRanking(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_by: str
    direction: Literal["asc", "desc"] = "desc"
    top_k: int = Field(default=5, ge=1, le=10)


class AnalyticalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    normalized_question: str
    language: Literal["vi", "id", "unknown"]
    resolved_entities: tuple[EntityBinding, ...] = ()
    requested_measures: tuple[SemanticBinding, ...] = ()
    requested_dimensions: tuple[SemanticBinding, ...] = ()
    filters: tuple[AnalyticalPredicate, ...] = ()
    time_scope: AnalyticalTimeScope
    grouping: tuple[str, ...] = ()
    comparison: dict[str, Any] | None = None
    ranking: AnalyticalRanking | None = None
    requested_grain: Literal["listing", "listing_snapshot", "shop", "shelf", "category", "country", "group"]
    analytical_operators: tuple[str, ...] = ()
    answerability_class: Literal["C1", "C2", "C3", "C4"] = "C1"
    ambiguities: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    requested_output_shape: Literal["scalar", "table", "ranking", "comparison"]
    unsupported_operators: tuple[str, ...] = ()
    # W5.1: phép tổng hợp mà câu hỏi nêu TƯỜNG MINH. Dùng chính kiểu Aggregation
    # của IR thay vì chép một Literal thứ hai — hai danh sách là hai chỗ để
    # chúng lệch nhau. Additive, mặc định None ⇒ fixture cũ không hỏng.
    requested_aggregation: Aggregation | None = None



# W5.1 — cụm nêu TƯỜNG MINH một phép tổng hợp. Hai cue khác nhau cùng xuất hiện
# ⇒ ghi ambiguity và KHÔNG chọn theo thứ tự bảng: chọn theo thứ tự bảng là để
# thứ tự khai báo trả lời hộ một câu hỏi mơ hồ.
_AGGREGATION_CUES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("trung vi", "median"), "median"),
    (("trung binh", "binh quan", "rata rata", "average", "mean"), "mean"),
    (("tong cong", "cong lai", "tong ", "total", "sum"), "sum"),
    # CHỆCH KHỎI SPEC CÓ CHỦ ĐÍCH: bảng §6.2 liệt cả `max`/`min` trần. Đo trên
    # bộ đề thật thì `"max"` trần khớp "iPhone 15 Pro Max" trong dr2607:tc35 và
    # biến một câu phân tích doanh số thành một câu hỏi cực trị — đúng lớp lỗi
    # "$7.7 billion → anchor chiến dịch 7.7" ở CLAUDE.md §3.1. Cụm tiếng Việt và
    # `maximum`/`minimum` không có hình thái đó nên được giữ.
    (("cao nhat", "lon nhat", "toi da", "maximum"), "max"),
    (("thap nhat", "nho nhat", "toi thieu", "minimum"), "min"),
)

# Cực trị chỉ là một CON SỐ khi câu hỏi hỏi một con số. "Price original cao nhất
# tại VN" hôm nay trả về các DÒNG đã xếp hạng và 58 plan bị khoá phụ thuộc điều
# đó; "Giá cao nhất tại Indonesia LÀ BAO NHIÊU" mới là câu hỏi vô hướng. Thiếu
# điều kiện này, năm entry baseline đổi hình mà không câu hỏi nào đổi nghĩa.
_SCALAR_INTERROGATIVE = ("bao nhieu", "berapa", "la bao nhieu", "how much")
# "cao nhất/thấp nhất" chỉ là scalar aggregate khi câu KHÔNG hỏi một chủ thể
# xếp hạng: "listing nào có giá cao nhất" hỏi một DÒNG, còn "giá cao nhất là
# bao nhiêu" hỏi một CON SỐ. Không dùng `ranking is not None` làm dấu hiệu —
# parser suy ranking từ chính cụm so sánh, nên mọi câu có "cao nhất" đều có
# ranking và điều kiện sẽ luôn đúng, tức luật không bao giờ bắn.
_EXTREMUM_AGGREGATIONS = frozenset({"max", "min"})
_RANKING_SUBJECT = re.compile(
    r"\b(listing|san pham|mat hang|hang hoa|shop|cua hang|thuong hieu|brand|"
    r"danh muc|toko|produk|merek|kategori)\b[^?]{0,24}?\b(nao|mana|dengan)\b",
)


def _names_a_ranking_subject(normalized: str) -> bool:
    return bool(_RANKING_SUBJECT.search(normalized))


def _detect_requested_aggregation(
    normalized: str, has_ranking_subject: bool, asks_for_a_number: bool,
) -> tuple[str | None, str | None]:
    """``(aggregation, ambiguity)`` — phép tổng hợp câu hỏi NÊU RA, nếu có."""
    hits: list[str] = []
    for terms, aggregation in _AGGREGATION_CUES:
        if any(term in normalized for term in terms) and aggregation not in hits:
            hits.append(aggregation)
    if has_ranking_subject or not asks_for_a_number:
        hits = [item for item in hits if item not in _EXTREMUM_AGGREGATIONS]
    if not hits:
        return None, None
    if len(hits) > 1:
        return None, (
            "Câu hỏi nêu nhiều phép tổng hợp khác nhau: "
            + ", ".join(hits) + "; không chọn hộ một trong số đó."
        )
    return hits[0], None


# W11.1 — một measure đứng cạnh một từ so sánh là ĐIỀU KIỆN, không phải thứ được
# đo. "bao nhiêu listing giảm giá TRÊN 50%" đo số listing; "giảm giá trên 50%"
# là bộ lọc. Để nó ở cả hai chỗ làm request khai hai measure cho một câu hỏi một
# measure, và synthesizer từ chối vì đúng lý do sai (measure_count_not_one).
# Cụm dài xếp trước: "hon" là đuôi của "lon hon"/"cao hon".
_COMPARISON: tuple[tuple[str, str], ...] = (
    ("lon hon", "gt"), ("cao hon", "gt"), ("nho hon", "lt"), ("thap hon", "lt"),
    ("it nhat", "gte"), ("toi da", "lte"), ("di atas", "gt"), ("di bawah", "lt"),
    ("tren", "gt"), ("duoi", "lt"), ("tu", "gte"), ("hon", "gt"),
)
_PERCENT_MARKERS = ("%", "phan tram", "phần trăm", "persen")


def _comparison_predicates(
    measures: list, normalized: str, raw_question: str,
) -> tuple[list, list]:
    """``(measures còn lại, predicate mới)`` — cả BỐN điều kiện đều bắt buộc.

    1. ≥2 measure đã bind, đúng MỘT có ``counts_unit`` — câu một measure không
       có gì để lọc;
    2. measure không-đếm đứng liền trước một cụm so sánh và một số — "giảm giá"
       trần không được biến thành bộ lọc ``> None``;
    3. toán tử suy ra nằm trong ``allowed_filters`` — catalog cấm thì không lách;
    4. đơn vị của số khớp ``unit`` của measure (đọc từ câu GỐC vì normalizer bỏ
       ``%``) — "trên 50" với measure đơn vị tiền tệ là một câu hỏi KHÁC.

    Không đạt bất kỳ điều kiện nào ⇒ giữ nguyên hành vi hôm nay. Guard MỘT
    CHIỀU, như ``_has_unbound_qualifier``.
    """
    bound = [item for item in measures if item.ref]
    counting = [item for item in bound if CATALOG[item.ref].counts_unit]
    conditions = [item for item in bound if not CATALOG[item.ref].counts_unit]
    if len(bound) < 2 or len(counting) != 1 or not conditions:
        return measures, []

    kept, predicates = list(measures), []
    comparison_alternatives = "|".join(
        re.escape(term) for term, _op in _COMPARISON
    )
    for item in conditions:
        obj = CATALOG[item.ref]
        pattern = re.compile(
            re.escape(normalize(item.surface_text))
            + r"\s+(" + comparison_alternatives + r")\s+(\d+(?:[.,]\d+)?)\b",
        )
        found = pattern.search(normalized)
        if not found:
            continue
        op = next(op for term, op in _COMPARISON if term == found.group(1))
        if op not in obj.allowed_filters:
            continue
        literal = found.group(2).replace(",", ".")
        # Điều kiện 4 — đơn vị của SỐ phải khớp đơn vị của MEASURE, đọc từ câu
        # GỐC vì normalizer đã bỏ "%". Cố ý HẸP: chỉ measure đơn vị percent với
        # một số mang dấu %/phần trăm được áp; "trên 50" trần cạnh một measure
        # tiền tệ là một câu hỏi KHÁC (50 gì? VND? nghìn? phần trăm?) và guard
        # một chiều thì bỏ qua đúng hơn đoán.
        if obj.unit != "percent":
            continue
        raw_folded = raw_question.lower()
        anchor_pos = raw_folded.find(literal.split(".")[0])
        if anchor_pos < 0 or not any(
            marker in raw_folded[anchor_pos: anchor_pos + len(literal) + 16]
            for marker in _PERCENT_MARKERS
        ):
            continue
        number = float(literal)
        predicates.append(AnalyticalPredicate(
            field_ref=item.ref, op=op,
            value_binding=int(number) if number.is_integer() else number,
        ))
        kept = [entry for entry in kept if entry is not item]
    return kept, predicates


# W4.1 — khung "Số lượng X là bao nhiêu?" và "Có bao nhiêu X?" hỏi cùng một
# thứ. Bộ alias khớp trên cụm DÍNH LIỀN ("bao nhieu shop"), nên khung thứ hai
# làm cụm đó tách ra và câu mất measure. Viết lại NGUYÊN KHUNG và chép `rest`
# nguyên văn: định ngữ ("da xac minh", "chinh hang") nằm trong `rest` nên nó
# không thể rơi mất — đó là điều kiện để phép viết lại này không đổi câu hỏi.
_COUNT_FRAME_VI = re.compile(
    r"^(?P<lead>.*?)\bso luong\s+(?P<rest>.+?)\s+la bao nhieu\b.*$"
)
_COUNT_FRAME_ID = re.compile(
    r"^(?P<lead>.*?)\bjumlah\s+(?P<rest>.+?)\s+(?:adalah\s+)?berapa\b.*$"
)


def _normalise_count_frame(normalized: str) -> tuple[str, bool]:
    """``(câu đã viết lại, có viết lại không)`` — cờ đếm số lần nhánh bắn."""
    for frame in (_COUNT_FRAME_VI, _COUNT_FRAME_ID):
        found = frame.match(normalized)
        if found:
            rewritten = " ".join(
                f"{found.group('lead')} co bao nhieu {found.group('rest')}".split()
            )
            return rewritten, True
    return normalized, False


_EXPLICIT_TOP_N = re.compile(r"\btop\s*(\d{1,2})\b")
# Vietnamese/Indonesian plural markers that ask for a list rather than one row.
# Deliberately narrow: "cac san pham" as a *grouping domain* ("trung binh cua
# cac san pham") must stay scalar, so only markers that introduce the ranked
# subject count. Anything unmatched falls back to top_k=1, the old behaviour.
_PLURAL_MARKERS = ("nhung ", "liet ke ", "danh sach ", "cac san pham nao", "produk apa saja")
DEFAULT_PLURAL_TOP_K = 5


def _requested_top_k(normalized: str) -> int:
    """How many rows the question asks for; 1 unless it says otherwise."""
    explicit = _EXPLICIT_TOP_N.search(normalized)
    if explicit:
        return max(1, min(int(explicit.group(1)), 10))  # AnalyticalRanking caps at 10
    if any(marker in f" {normalized} " for marker in _PLURAL_MARKERS):
        return DEFAULT_PLURAL_TOP_K
    return 1


class CatalogSlicer:
    def __init__(self, catalog: dict[str, CatalogObject] | None = None):
        self.catalog = catalog or CATALOG

    def select(self, query: str, limit: int = 30) -> tuple[CatalogObject, ...]:
        needle = normalize(query)
        scored: list[tuple[float, str, CatalogObject]] = []
        for obj in self.catalog.values():
            haystacks = (obj.ref.replace("_", " "),) + tuple(normalize(alias) for alias in obj.aliases)
            score = max(fuzz.WRatio(needle, text) for text in haystacks if text)
            if any(text and text in needle for text in haystacks):
                score += 25
            scored.append((score, obj.ref, obj))
        scored.sort(key=lambda item: (-item[0], item[1]))
        required_refs = ("dim.country", "dim.date")
        # Reserve room for the scope refs before filling, instead of evicting
        # afterwards: the old code popped from the end, so when *both* were
        # missing the second eviction removed the first one just appended and
        # the slice silently shipped without a country scope.
        missing = [ref for ref in required_refs if ref not in {item[1] for item in scored[:limit]}]
        room = max(limit - len(missing), 0)
        selected = [item[2] for item in scored[:room]]
        selected.extend(self.catalog[ref] for ref in missing)
        return tuple(selected)


class DeterministicSemanticParser:
    """Fallback P7 bảo thủ; không tạo physical column hoặc join."""

    def __init__(self) -> None:
        self.alias_index = default_alias_index()

    @staticmethod
    def _contains_phrase(normalized: str, phrase: str) -> bool:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", normalized))

    def _link(self, normalized: str, kinds: set[str]) -> list[SemanticBinding]:
        """Lớp mỏng trên ``AliasIndex`` — WP-A4.1.

        Trước đây hàm này giữ bộ khớp alias THỨ HAI, cộng hai bảng seed
        hard-code làm bộ thứ ba. Ba bộ song song nghĩa là một bản vá ở bộ này
        không áp cho bộ kia: bug ``"giá trị"`` → ``measure.price`` từng được vá
        riêng ở đây trong khi vẫn sống nguyên trong ``AliasIndex``.

        Luật khớp dài nhất và ``compound_shadowed`` đã nằm sẵn trong
        ``AliasIndex.find_in``; chỗ này chỉ còn việc phân giải surface trỏ nhiều
        ref bằng ``PREFERRED_REF_BY_SURFACE``.
        """
        accepted: list[tuple[str, str]] = []
        seen_refs: set[str] = set()
        for match in self.alias_index.find_in(normalized, kinds=frozenset(kinds)):
            ref = match.refs[0]
            if match.ambiguous:
                preferred = PREFERRED_REF_BY_SURFACE.get(match.surface)
                # Surface mơ hồ mà không có ưu tiên: chọn một ref theo thứ tự
                # index là trả lời một câu hỏi khác trong im lặng.
                if preferred is None or preferred not in match.refs:
                    continue
                ref = preferred
            if ref in seen_refs or CATALOG[ref].kind not in kinds:
                continue
            accepted.append((match.surface, ref))
            seen_refs.add(ref)
        return [SemanticBinding(surface_text=alias, ref=ref) for alias, ref in accepted]

    def parse(self, text: str, language: str, country: str | None) -> AnalyticalRequest:
        normalized = normalize(text)
        # W4.1: viết lại khung đếm TRƯỚC _link — alias khớp cụm dính liền.
        normalized, count_frame_normalised = _normalise_count_frame(normalized)
        measures = self._link(normalized, {"measure", "derived_metric"})
        dimension_text = normalized
        for measure in measures:
            dimension_text = re.sub(
                rf"(?<![a-z0-9]){re.escape(measure.surface_text)}(?![a-z0-9])",
                " ", dimension_text,
            )
        dimensions = self._link(dimension_text, {"entity", "dimension"})
        if any(
            item.ref and item.ref.startswith("measure.shop_")
            and item.ref != "measure.shop_category_total"
            for item in measures
        ) and not any(item.ref == "entity.shop" for item in dimensions):
            dimensions.append(SemanticBinding(surface_text="shop", ref="entity.shop"))
        unresolved: list[SemanticBinding] = []
        if any(term in normalized for term in ("hieu qua", "tot nhat", "dang mua", "effective", "worth buying")):
            unresolved.append(SemanticBinding(
                surface_text="hiệu quả/tốt nhất", unresolved=True, reason="metric_ungoverned",
            ))
        if any(term in normalized for term in ("url", "image url", "duong dan", "location", "lokasi")):
            unresolved.append(SemanticBinding(
                surface_text="URL/location", unresolved=True, reason="catalog_gap",
            ))
        if any(term in normalized for term in ("profit", "loi nhuan", "conversion", "chuyen doi", "sku")):
            unresolved.append(SemanticBinding(
                surface_text="biến nghiệp vụ không có trong dataset", unresolved=True, reason="data_absent",
            ))
        measures.extend(unresolved)

        unsupported_ops = tuple(
            name for terms, name in (
                (("recursive", "de quy", "lap den khi"), "recursive"),
                (("udf", "ham tu do", "cong thuc tuy y"), "free_expression"),
                (("forecast", "du bao", "ramalan"), "forecast"),
            ) if any(term in normalized for term in terms)
        )
        dates = tuple(dict.fromkeys(extract_date_range(normalized)))
        assumptions: list[str] = []
        if not dates:
            dates = ("2026-07-03",)
            assumptions.append("Mặc định snapshot mới nhất 2026-07-03 cho aggregate cross-sectional.")
        filters = []
        if country:
            filters.append(AnalyticalPredicate(field_ref="dim.country", op="eq", value_binding=country))
        if len(dates) == 1:
            filters.append(AnalyticalPredicate(field_ref="dim.date", op="eq", value_binding=dates[0]))
        # WP-A4.4: điều kiện boolean đã có cột vật lý thì bind thành predicate.
        # Trước đây parse chỉ sinh predicate cho country và date, nên mọi câu có
        # điều kiện đều làm synthesize() trả None — kể cả điều kiện hệ thừa sức
        # lọc. Phủ định được xét trước trong `qualifier_match`.
        # WP-A4.3: giá trị chiều có thật trong dữ liệu thì bind thành predicate.
        # Chỉ bind cho chiều mà câu hỏi ĐÃ nêu tên — xem value_probe.bind_values.
        # Import trễ: `agent/` phụ thuộc `planner/`, nên import ở đầu file tạo
        # vòng qua analytics/tools.py.
        from gladiators.agent.value_probe import bind_values

        for value_ref, literal in bind_values(
            normalized, country,
            frozenset(item.ref for item in dimensions if item.ref),
        ):
            filters.append(AnalyticalPredicate(
                field_ref=value_ref, op="eq", value_binding=literal,
            ))
        # W1.2 bước hai: đơn vị phân tích được NÊU TÊN cụ thể thì thành bộ lọc.
        # "shop" giải thành entity.shop (đơn vị đếm), nên dimension_refs ở trên
        # không chứa dim.shop_name và tên shop không bao giờ được bind — câu
        # "listing CỦA shop X" bị đọc thành "listing THEO TỪNG shop", một câu hỏi
        # khác, trả lời trong im lặng (120 listing thành bảng đếm 10 shop).
        # Khớp 0 hoặc >1 ⇒ không làm gì: câu đang gom nhóm chứ không lọc.
        if country:
            from gladiators.domain.catalog import VALUE_DIMENSION_BY_UNIT

            for unit_binding in list(dimensions):
                dim_ref = VALUE_DIMENSION_BY_UNIT.get(unit_binding.ref or "")
                if dim_ref is None:
                    continue
                named = bind_values(normalized, country, frozenset({dim_ref}))
                if len(named) != 1:
                    continue
                value_ref, literal = named[0]
                filters.append(AnalyticalPredicate(
                    field_ref=value_ref, op="eq", value_binding=literal,
                ))
                # Đơn vị đã thành điều kiện lọc thì không còn là chiều gom nhóm.
                dimensions = [
                    item for item in dimensions if item.ref != unit_binding.ref
                ]
        qualifier_refs: set[str] = set()
        for spec, value, _surface in qualifier_match(normalized):
            filters.append(AnalyticalPredicate(
                field_ref=spec.ref, op="eq", value_binding=value,
            ))
            qualifier_refs.add(spec.ref)
        # Một ref đã thành điều kiện lọc thì KHÔNG còn là thứ được đo. "Bao nhiêu
        # listing CÓ VOUCHER" đo số listing; "có voucher" là điều kiện. Để nó ở
        # cả hai chỗ làm request khai hai measure cho một câu hỏi một measure, và
        # synthesizer từ chối vì đúng lý do sai.
        if qualifier_refs:
            measures = [item for item in measures if item.ref not in qualifier_refs]
            dimensions = [item for item in dimensions if item.ref not in qualifier_refs]

        # W11.1: chạy SAU _link (measure đã bind) và TRƯỚC khi chốt
        # requested_measures/ranking.
        measures, comparison_filters = _comparison_predicates(
            measures, normalized, text,
        )
        filters.extend(comparison_filters)

        # W4.2 — đếm theo CẤU TRÚC, không theo cụm dính liền. Bốn điều kiện đều
        # bắt buộc: measures rỗng (câu "giá trung vị theo brand" không được biến
        # brand thành measure); đúng MỘT ứng viên (hai chiều thì chọn một là
        # chọn hộ người hỏi); LIỀN KỀ từ hỏi số lượng, kiểm bằng boundary regex
        # chứ không phải `in` ("rating theo brand ... có bao nhiêu listing"
        # không được đếm brand); ref nằm trong registry đã duyệt.
        count_frame_ambiguity: str | None = None
        if not measures:
            count_candidates = []
            for item in dimensions:
                if not item.ref or item.ref not in COUNT_METRIC_BY_SURFACE_REF:
                    continue
                surface = normalize(item.surface_text)
                adjacency = re.compile(
                    r"(?:bao nhieu|berapa|how many)\s+" + re.escape(surface) + r"\b",
                )
                if adjacency.search(normalized):
                    count_candidates.append(item)
            if len(count_candidates) == 1:
                chosen = count_candidates[0]
                measures = [SemanticBinding(
                    surface_text=chosen.surface_text,
                    ref=COUNT_METRIC_BY_SURFACE_REF[chosen.ref],
                )]
                dimensions = [item for item in dimensions if item is not chosen]
            elif len(count_candidates) > 1:
                count_frame_ambiguity = (
                    "Câu hỏi số lượng nêu nhiều chiều cùng lúc: "
                    + ", ".join(item.surface_text for item in count_candidates)
                    + "; không chọn hộ một trong số đó."
                )

        descending = any(term in normalized for term in ("cao nhat", "nhieu nhat", "lon nhat", "highest", "tertinggi", "top"))
        ascending = any(term in normalized for term in ("thap nhat", "it nhat", "lowest", "terendah"))
        rank_ref = next((item.ref for item in measures if item.ref), None)
        ranking = AnalyticalRanking(
            order_by=rank_ref, direction="asc" if ascending else "desc",
            top_k=_requested_top_k(normalized),
        ) if rank_ref and (descending or ascending) else None
        # "Cửa hàng nào có nhiều SẢN PHẨM nhất" counts products per shop: the
        # counted noun is the unit, not a second grouping key. It only looked
        # like one because "sản phẩm" binds to dim.product_name while the
        # synonymous "listing" binds to entity.product_listing, so the two
        # phrasings of one question took different paths and A22 rejected the
        # plan for "dropping" a dimension nobody grouped by. The original patch
        # required entity.shop to be present; the concept does not, and two rules
        # for one concept drift apart.
        counted_unit = any(term in normalized for term in _COUNTING_CUES)
        if counted_unit:
            dimensions = [
                SemanticBinding(surface_text=item.surface_text, ref="entity.product_listing")
                if item.ref == "dim.product_name" else item
                for item in dimensions
            ]
        # A5: a unit with no column of its own is not a dimension at all, so it must
        # not be reported as one: A22 would otherwise see the plan "drop" a
        # dimension nobody could have grouped by. entity.shop stays -- owning
        # shop_id is what makes a unit groupable as well as countable.
        dimensions = [
            item for item in dimensions
            if not item.ref or CATALOG[item.ref].analysis_role != "analysis_unit"
            or CATALOG[item.ref].physical
        ]
        grouping = tuple(
            item.ref for item in dimensions
            if item.ref and item.ref not in {"dim.country"} and CATALOG[item.ref].physical
        )
        price_change_table = any(
            term in normalized
            for term in ("gia thay doi", "bien dong gia", "price change", "perubahan harga")
        )
        if price_change_table and "dim.date" not in grouping:
            grouping = (*grouping, "dim.date")
        requested_grain = "shop" if "entity.shop" in grouping else "category" if "dim.platform_category_name" in grouping else "listing" if ranking else "group"
        operators = ["filter"]
        if grouping or any(item.ref == "derived.product_count" for item in measures):
            operators.append("aggregate")
        if ranking:
            operators.append("rank")
        comparison = None
        if any(term in normalized for term in ("so sanh", "compare", "bandingkan")):
            comparison = {"mode": "descriptive_group_comparison"}
            operators.append("compare")
        ambiguities = []
        if count_frame_ambiguity:
            ambiguities.append(count_frame_ambiguity)
        if count_frame_normalised:
            # Khoá đếm (§0.3 ô 4): nhánh viết lại phải đếm được số lần nó bắn.
            assumptions = (*assumptions, "count_frame_normalised")
        requested_aggregation, aggregation_ambiguity = _detect_requested_aggregation(
            normalized, has_ranking_subject=_names_a_ranking_subject(normalized),
            asks_for_a_number=any(
                term in normalized for term in _SCALAR_INTERROGATIVE
            ),
        )
        if aggregation_ambiguity:
            ambiguities.append(aggregation_ambiguity)
        if requested_aggregation is None:
            # W11.2: alias tỷ lệ được bind ⇒ aggregation đến từ ĐỊNH NGHĨA
            # metric, không phải từ từ "tỷ lệ" trần trong câu.
            from gladiators.domain.metrics import METRICS

            for item in measures:
                if item.ref and item.ref.startswith("derived."):
                    spec = METRICS.get(item.ref.split(".", 1)[1])
                    if spec is not None and spec.share is not None:
                        requested_aggregation = "share"
                        break
        if requested_aggregation in _EXTREMUM_AGGREGATIONS and ranking is not None:
            # W5.2: "giá cao nhất LÀ BAO NHIÊU" hỏi một CON SỐ, còn ranking suy
            # ra từ chính cụm "cao nhất" biến nó thành một câu hỏi về các DÒNG.
            # Giữ cả hai thì plan xếp hạng các dòng trong khi câu hỏi yêu cầu
            # một giá trị tổng hợp, và lời từ chối sinh ra nói về measure bị
            # thay chứ không nói về thứ thật sự sai. Đo trước khi đổi: 0 entry
            # trong 60 plan bị khoá thay đổi.
            ranking = None
            requested_grain = "group"
            operators = [item for item in operators if item != "rank"]
        monetary = any(item.ref in {"measure.price", "derived.estimated_recent_revenue"} for item in measures)
        if not country:
            ambiguities.append(
                "Thiếu country cho metric tiền tệ; không được trộn VND và IDR."
                if monetary else "Thiếu country để khóa scope VN hoặc ID."
            )
        return AnalyticalRequest(
            normalized_question=normalized,
            language=language if language in {"vi", "id"} else "unknown",
            requested_measures=tuple(measures), requested_dimensions=tuple(dimensions),
            filters=tuple(filters), time_scope=AnalyticalTimeScope(
                dates=dates, mode="single_snapshot" if len(dates) == 1 else "all_with_caveat",
            ), grouping=grouping, comparison=comparison, ranking=ranking, requested_grain=requested_grain,
            analytical_operators=tuple(operators), ambiguities=tuple(ambiguities),
            assumptions=tuple(assumptions),
            requested_output_shape="ranking" if ranking else "scalar" if not grouping else "table",
            unsupported_operators=unsupported_ops,
            requested_aggregation=requested_aggregation,
        )


def classify_a19(request: AnalyticalRequest) -> tuple[str, str, str] | None:
    """Trả ``(action, rule_id, reason)`` hoặc None nếu request được admit vào P8."""
    if request.ambiguities:
        return "clarify", "A-ANALYTICAL-AMBIGUITY", "; ".join(request.ambiguities)
    if request.unsupported_operators:
        return "abstain", "A19-OP", "IR hiện không hỗ trợ operator: " + ", ".join(request.unsupported_operators)
    unresolved = [item for item in request.requested_measures + request.requested_dimensions if item.unresolved]
    if any(item.reason == "metric_ungoverned" for item in unresolved):
        return "clarify", "A19-METRIC", "Metric nghiệp vụ chưa có định nghĩa được duyệt; có thể chuyển sang so sánh mô tả nếu bạn xác nhận."
    if any(item.reason == "catalog_gap" for item in unresolved):
        return "abstain", "A19-CAT", "Trường dữ liệu được hỏi chưa được mở cho truy vấn."
    if any(item.reason == "data_absent" for item in unresolved):
        return "abstain", "A-DATA-ABSENT", "Dataset không có biến nghiệp vụ được yêu cầu."
    if not any(item.ref for item in request.requested_measures):
        return "clarify", "A19-CAT", "Chưa xác định được chỉ số nào cần đo từ câu hỏi."
    return None


def classify_complexity(request: AnalyticalRequest) -> Literal["L0", "L1", "L2", "L3", "L4"]:
    """Phân lớp bảo thủ từ semantic contract; không dựa vào lời tự khai của LLM planner."""
    resolved_measures = sum(bool(item.ref) for item in request.requested_measures)
    if request.comparison and (resolved_measures >= 2 or len(request.grouping) >= 2):
        return "L4"
    if request.comparison or len(request.grouping) >= 2:
        return "L3"
    if request.ranking or request.grouping or "aggregate" in request.analytical_operators:
        return "L2"
    if request.filters:
        return "L1"
    return "L0"
