"""P7 AnalyticalRequest contract, catalog slicing và deterministic fallback."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from rapidfuzz import fuzz

from gladiators.domain.catalog import CATALOG, CatalogObject


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
    op: Literal["eq", "ne", "in", "lt", "le", "gt", "ge", "between", "isnull"]
    value_binding: Any


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

    MEASURES = (
        (("doanh thu", "revenue", "pendapatan"), "derived.estimated_recent_revenue"),
        (("gia", "price", "harga"), "measure.price"),
        (("luot ban", "monthly sold", "penjualan"), "measure.monthly_sold"),
        (("bao nhieu listing", "how many listing", "berapa listing", "bao nhieu san pham", "berapa produk"), "derived.product_count"),
        (("rating", "danh gia"), "measure.rating"),
        (("follower", "nguoi theo doi", "pengikut"), "measure.shop_followers"),
    )
    DIMENSIONS = (
        (("shop", "cua hang", "toko"), "entity.shop"),
        (("ngay", "date", "tanggal"), "dim.date"),
        (("quoc gia", "thi truong", "country", "negara"), "dim.country"),
        (("brand", "thuong hieu", "merek"), "dim.brand"),
        (("danh muc", "category", "kategori"), "dim.platform_category_name"),
    )

    @staticmethod
    def _contains_phrase(normalized: str, phrase: str) -> bool:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", normalized))

    def _link(
        self, normalized: str, seeds: tuple[tuple[tuple[str, ...], str], ...],
        kinds: set[str],
    ) -> list[SemanticBinding]:
        candidates: list[tuple[int, int, str, str]] = []
        for terms, ref in seeds:
            for term in terms:
                alias = normalize(term)
                if alias and self._contains_phrase(normalized, alias):
                    candidates.append((-len(alias.split()), 0, alias, ref))
        for obj in CATALOG.values():
            if obj.kind not in kinds:
                continue
            for term in obj.aliases:
                alias = normalize(term)
                if alias and self._contains_phrase(normalized, alias):
                    candidates.append((-len(alias.split()), 1, alias, obj.ref))
        candidates.sort(key=lambda item: (item[0], item[1], -len(item[2]), item[3]))
        accepted: list[tuple[str, str]] = []
        seen_refs: set[str] = set()
        for _, _, alias, ref in candidates:
            if ref in seen_refs:
                continue
            # Longest-match wins: ``shop rating`` suppresses the nested generic
            # ``rating``; seed priority resolves same-surface entity/dim aliases.
            if any(alias == chosen for chosen, _ in accepted):
                continue
            residual = normalized
            for chosen, _ in accepted:
                if self._contains_phrase(chosen, alias):
                    residual = re.sub(
                        rf"(?<![a-z0-9]){re.escape(chosen)}(?![a-z0-9])", " ", residual,
                    )
            if not self._contains_phrase(residual, alias):
                continue
            accepted.append((alias, ref))
            seen_refs.add(ref)
        return [SemanticBinding(surface_text=alias, ref=ref) for alias, ref in accepted]

    def parse(self, text: str, language: str, country: str | None) -> AnalyticalRequest:
        normalized = normalize(text)
        # "giá trị" means "value", not the price measure. Keep explicit
        # "price/giá" elsewhere available to the linker.
        measure_text = re.sub(r"\bgia tri\b", "value", normalized)
        measures = self._link(measure_text, self.MEASURES, {"measure", "derived_metric"})
        dimension_text = normalized
        for measure in measures:
            dimension_text = re.sub(
                rf"(?<![a-z0-9]){re.escape(measure.surface_text)}(?![a-z0-9])",
                " ", dimension_text,
            )
        dimensions = self._link(dimension_text, self.DIMENSIONS, {"entity", "dimension"})
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

        descending = any(term in normalized for term in ("cao nhat", "nhieu nhat", "lon nhat", "highest", "tertinggi", "top"))
        ascending = any(term in normalized for term in ("thap nhat", "it nhat", "lowest", "terendah"))
        rank_ref = next((item.ref for item in measures if item.ref), None)
        ranking = AnalyticalRanking(
            order_by=rank_ref, direction="asc" if ascending else "desc",
            top_k=_requested_top_k(normalized),
        ) if rank_ref and (descending or ascending) else None
        grouping = tuple(item.ref for item in dimensions if item.ref and item.ref not in {"dim.country"})
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
