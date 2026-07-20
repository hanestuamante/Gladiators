"""Executable semantic catalog theo V2 mục 5.5.

Catalog ánh xạ semantic refs sang cột vật lý. Planner chỉ thấy refs; compiler mới
được đọc ``physical``. Coverage manifest dùng cùng catalog để tránh hai nguồn
định nghĩa khác nhau.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .metrics import METRICS

CatalogKind = Literal["entity", "dimension", "measure", "derived_metric"]
Answerability = Literal[
    "exposed_as_dimension", "exposed_as_measure", "proxy_only", "raw_but_unsafe", "absent"
]


@dataclass(frozen=True)
class CatalogObject:
    ref: str
    kind: CatalogKind
    aliases: tuple[str, ...]
    physical: tuple[str, ...]
    type: str
    unit: str
    grain: str
    valid_aggregations: tuple[str, ...]
    time_semantics: str
    allowed_filters: tuple[str, ...]
    cardinality: int | None
    caveats: tuple[str, ...]
    traps: tuple[int, ...]
    provenance: str
    value_index: tuple[str, ...] | None
    answerability: Answerability


def _object(
    ref: str,
    kind: CatalogKind,
    aliases: tuple[str, ...],
    physical: tuple[str, ...],
    *,
    type: str = "string",
    unit: str = "dimension",
    grain: str = "listing_snapshot",
    aggregations: tuple[str, ...] = (),
    time: str = "per_snapshot",
    filters: tuple[str, ...] = ("eq", "in"),
    cardinality: int | None = None,
    caveats: tuple[str, ...] = (),
    traps: tuple[int, ...] = (),
    value_index: tuple[str, ...] | None = None,
    answerability: Answerability | None = None,
) -> CatalogObject:
    if answerability is None:
        answerability = "exposed_as_dimension" if kind in {"entity", "dimension"} else "exposed_as_measure"
    return CatalogObject(
        ref, kind, aliases, physical, type, unit, grain, aggregations, time, filters,
        cardinality, caveats, traps, "V2_Unified_Architecture.md", value_index, answerability,
    )


_BASE_OBJECTS = [
    _object("entity.country", "entity", ("quốc gia", "country", "negara"), (), grain="country"),
    _object("entity.shop", "entity", ("shop", "cửa hàng", "toko"),
            tuple(f"{t}.shop_id" for t in ("products_clean.csv", "shop_info_clean.csv", "category_list_clean.csv", "product_categories_clean.csv", "product_snapshot_metrics.csv", "product_transition_metrics.csv")), grain="shop"),
    _object("entity.brand", "entity", ("thương hiệu", "brand", "merek"), (), grain="brand"),
    _object("entity.product_listing", "entity", ("listing", "sản phẩm", "produk"), (), grain="listing"),
    _object("entity.platform_category", "entity", ("danh mục sàn", "platform category"), (), grain="platform_category"),
    _object("entity.shop_category", "entity", ("kệ shop", "shop shelf"), (), grain="shop_category"),
    _object("entity.promotion_id_observation", "entity", ("promotion id quan sát",), (), grain="listing_snapshot"),
    _object("entity.voucher_observation", "entity", ("voucher quan sát",), (), grain="listing_snapshot"),
    _object("entity.content", "entity", ("nội dung listing", "content"), (), grain="listing_snapshot"),
    _object("entity.sales_metric", "entity", ("chỉ số bán", "sales metric"), (), grain="snapshot_or_transition"),
    _object("entity.date_snapshot", "entity", ("snapshot ngày", "date snapshot"), (), grain="snapshot"),
    _object("dim.country", "dimension", ("quốc gia", "thi truong", "country", "negara"),
            tuple(f"{t}.country_code" for t in ("products_clean.csv", "shop_info_clean.csv", "category_list_clean.csv", "product_categories_clean.csv", "category_platform_clean.csv", "product_snapshot_metrics.csv", "product_transition_metrics.csv")),
            cardinality=2, value_index=("vn", "id")),
    _object("dim.date", "dimension", ("ngày", "ngay", "date", "tanggal"),
            tuple(f"{t}.date" for t in ("products_clean.csv", "shop_info_clean.csv", "category_list_clean.csv", "product_categories_clean.csv", "product_snapshot_metrics.csv", "product_transition_metrics.csv")) + ("product_transition_metrics.csv.previous_date",),
            type="date", cardinality=3),
    _object("dim.product_name", "dimension", ("sản phẩm", "san pham", "product", "produk"),
            ("products_clean.csv.product_name", "products_clean.csv.product_name_clean", "product_snapshot_metrics.csv.product_name")),
    _object("dim.brand", "dimension", ("thương hiệu", "thuong hieu", "brand", "merek"), ("products_clean.csv.brand",), traps=()),
    _object("dim.shop_name", "dimension", ("shop", "cửa hàng", "cua hang", "toko"), ("shop_info_clean.csv.shop_name",), time="static_latest"),
    _object("dim.platform_category_name", "dimension", ("danh mục sàn", "platform category"), ("category_platform_clean.csv.display_category_name",)),
    _object("dim.shop_category_name", "dimension", ("kệ shop", "shop shelf"), ("category_list_clean.csv.display_name",)),
    _object("dim.shop_official", "dimension", ("official shop", "shop chính hãng"), ("shop_info_clean.csv.is_official_shop_bool",), type="bool", time="static_latest"),
    _object("dim.shop_vacation", "dimension", ("shop nghỉ", "vacation"), ("shop_info_clean.csv.vacation_bool",), type="bool", time="static_latest"),
    _object("dim.shop_category_parent", "dimension", ("kệ cha", "parent shelf"), ("category_list_clean.csv.is_parent_category_bool",), type="bool"),
    _object("dim.shop_category_child", "dimension", ("kệ con", "child shelf"), ("category_list_clean.csv.is_sub_category_bool",), type="bool"),
    _object("dim.display_variation", "dimension", ("phân loại hiển thị", "display variation"),
            ("products_clean.csv.tier_variation_name", "products_clean.csv.tier_variation_options"), traps=(13,)),
    _object("dim.shopee_verified", "dimension", ("shopee verified", "đã xác minh"),
            ("products_clean.csv.shopee_verified_bool",), type="bool"),
    _object("dim.platform_category_has_children", "dimension", ("danh mục có nhánh con",),
            ("category_platform_clean.csv.has_children_bool",), type="bool"),
]


_MEASURES: dict[str, tuple[tuple[str, ...], str, str, tuple[int, ...], Answerability]] = {
    "price": (("products_clean.csv.price_num", "product_snapshot_metrics.csv.price_num"), "local_currency", "number", (5,), "exposed_as_measure"),
    "price_original": (("products_clean.csv.price_original_num", "product_snapshot_metrics.csv.price_original_num"), "local_currency", "number", (1, 5), "exposed_as_measure"),
    "discount_percent": (("products_clean.csv.discount_percent_num",), "percent", "number", (), "exposed_as_measure"),
    "monthly_sold": (("products_clean.csv.monthly_sold_value_num", "product_snapshot_metrics.csv.monthly_sold_value_num"), "units_recent_window", "number", (4,), "proxy_only"),
    "history_sold": (("products_clean.csv.history_sold_value_num", "product_snapshot_metrics.csv.history_sold_value_num"), "units_cumulative", "number", (4,), "proxy_only"),
    "voucher_discount": (("products_clean.csv.voucher_discount_num", "product_snapshot_metrics.csv.voucher_discount_num"), "local_currency", "number", (19,), "exposed_as_measure"),
    "voucher_min_spend": (("products_clean.csv.voucher_min_spend_num",), "local_currency", "number", (19,), "exposed_as_measure"),
    "voucher_start_time": (("products_clean.csv.voucher_start_time_num",), "timestamp", "number", (19,), "exposed_as_measure"),
    "voucher_end_time": (("products_clean.csv.voucher_end_time_num",), "timestamp", "number", (19,), "exposed_as_measure"),
    "rating": (("products_clean.csv.rating_num", "product_snapshot_metrics.csv.rating_num"), "rating_point", "number", (), "exposed_as_measure"),
    "rating_count": (("products_clean.csv.rating_count_num", "product_snapshot_metrics.csv.rating_count_num"), "ratings", "number", (), "exposed_as_measure"),
    "liked_count": (("products_clean.csv.liked_count_num", "product_snapshot_metrics.csv.liked_count_num"), "likes", "number", (), "exposed_as_measure"),
    "images_count": (("products_clean.csv.images_count",), "images", "integer", (18,), "exposed_as_measure"),
    "variation_options_count": (("products_clean.csv.tier_variation_options_count",), "options", "integer", (13,), "exposed_as_measure"),
    "vouchers_count": (("products_clean.csv.vouchers_count",), "labels", "integer", (19,), "raw_but_unsafe"),
    "shop_rating": (("shop_info_clean.csv.rating_star_num",), "rating_point", "number", (7,), "exposed_as_measure"),
    "shop_followers": (("shop_info_clean.csv.follower_count_num",), "followers", "number", (7,), "exposed_as_measure"),
    "shop_items": (("shop_info_clean.csv.item_count_num",), "items", "number", (7,), "exposed_as_measure"),
    "shop_response_rate": (("shop_info_clean.csv.response_rate_num",), "percent", "number", (7,), "exposed_as_measure"),
    "shop_response_time": (("shop_info_clean.csv.response_time_num",), "time", "number", (7,), "exposed_as_measure"),
    "shop_rating_good": (("shop_info_clean.csv.rating_good_num",), "ratings", "number", (7,), "exposed_as_measure"),
    "shop_rating_normal": (("shop_info_clean.csv.rating_normal_num",), "ratings", "number", (7,), "exposed_as_measure"),
    "shop_rating_bad": (("shop_info_clean.csv.rating_bad_num",), "ratings", "number", (7,), "exposed_as_measure"),
    "shop_cancellation_rate": (("shop_info_clean.csv.cancellation_rate_num",), "percent", "number", (7,), "exposed_as_measure"),
    "shop_category_total": (("category_list_clean.csv.total_num",), "listings", "number", (3,), "exposed_as_measure"),
}

for name, (physical, unit, type_, traps, status) in _MEASURES.items():
    _BASE_OBJECTS.append(_object(
        f"measure.{name}", "measure", (name.replace("_", " "),), physical,
        type=type_, unit=unit, aggregations=("median", "min", "max"),
        filters=("eq", "lt", "lte", "gt", "gte"), traps=traps, answerability=status,
        caveats=("Dùng đúng grain và scope theo metric/relation registry.",),
    ))


_DERIVED_PHYSICAL = {
    "estimated_recent_revenue": ("product_snapshot_metrics.csv.estimated_recent_revenue",),
    "monthly_sold_delta": ("product_transition_metrics.csv.monthly_sold_delta",),
    "history_sold_delta_raw": ("product_transition_metrics.csv.history_sold_delta_raw",),
    "history_sold_decrease_flag": ("product_transition_metrics.csv.history_sold_decrease_flag",),
    "history_sold_delta_clean": ("product_transition_metrics.csv.snapshot_sales_delta_clean",),
    "price_change": ("product_transition_metrics.csv.price_change",),
    "price_change_pct": ("product_transition_metrics.csv.price_change_percent",),
    "discount_point_change": ("product_transition_metrics.csv.discount_point_change",),
    "rating_change": ("product_transition_metrics.csv.rating_change",),
    "rating_count_delta": ("product_transition_metrics.csv.new_rating_count",),
    "liked_delta": ("product_transition_metrics.csv.like_delta",),
    "has_structured_voucher": ("product_snapshot_metrics.csv.has_structured_voucher", "product_transition_metrics.csv.has_structured_voucher", "product_transition_metrics.csv.previous_has_structured_voucher"),
}

for name, spec in METRICS.items():
    _BASE_OBJECTS.append(_object(
        f"derived.{name}", "derived_metric", (name.replace("_", " "),), _DERIVED_PHYSICAL.get(name, ()),
        type="number", unit=spec.unit, grain=spec.grain,
        aggregations=spec.valid_aggregations, filters=("eq", "lt", "lte", "gt", "gte"),
        caveats=spec.caveats, traps=spec.traps,
        answerability="proxy_only" if name in {"estimated_recent_revenue", "monthly_sold_delta", "history_sold_delta_raw", "history_sold_delta_clean"} else "exposed_as_measure",
    ))


def _build_catalog(objects: list[CatalogObject]) -> dict[str, CatalogObject]:
    catalog: dict[str, CatalogObject] = {}
    physical: dict[str, str] = {}
    for obj in objects:
        if obj.ref in catalog:
            raise ValueError(f"Catalog ref trùng: {obj.ref}")
        for column in obj.physical:
            if column in physical:
                raise ValueError(f"Physical column {column} thuộc cả {physical[column]} và {obj.ref}")
            physical[column] = obj.ref
        catalog[obj.ref] = obj
    return catalog


CATALOG = _build_catalog(_BASE_OBJECTS)


def get(ref: str) -> CatalogObject | None:
    return CATALOG.get(ref)


def physical_index() -> dict[str, CatalogObject]:
    return {column: obj for obj in CATALOG.values() for column in obj.physical}


def catalog_slice(refs: tuple[str, ...]) -> tuple[CatalogObject, ...]:
    missing = sorted(set(refs) - CATALOG.keys())
    if missing:
        raise KeyError(f"Semantic refs không tồn tại: {missing}")
    return tuple(CATALOG[ref] for ref in refs)
