"""Executable relation/schema graph theo V2 mục 5.2.

Registry này là nơi duy nhất khai báo join hợp lệ. Planner chỉ chọn semantic
objects; compiler tìm đường join deterministic trên graph và không thể tự tạo
edge, đặc biệt không có edge ShopCategory ↔ PlatformCategory.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from heapq import heappop, heappush
from typing import Literal

from .tables import ArtifactName, PhysicalColumnRef

Cardinality = Literal["1:1", "1:N", "N:1", "N:M"]
FanoutEffect = Literal["none", "duplicates_left_rows", "duplicates_right_rows"]
TemporalValidity = Literal["per_snapshot", "static_latest_only"]
# ``inline`` = quan hệ mô tả cột đã nằm sẵn trên left frame, không sinh JOIN.
# ``left_join`` = thực sự nối sang một bảng khác.
ExecutionMode = Literal["inline", "left_join"]


@dataclass(frozen=True)
class JoinKey:
    left: PhysicalColumnRef
    right: PhysicalColumnRef


@dataclass(frozen=True)
class RelationBinding:
    """Nguồn DUY NHẤT cho phần vật lý của một relation (§E2).

    Trước đây compiler giữ ``_PHYSICAL_JOIN_KEYS`` mạnh hơn registry, nên review
    và pathfinding nhìn một contract còn SQL thi hành contract khác — hai relation
    đã lệch thật. ``mode`` là discriminator: inline không được có right source
    hay key, nên một relation inline không thể bị compile thành JOIN với key giả.
    """

    mode: ExecutionMode
    left_sources: tuple[ArtifactName, ...]
    right_source: ArtifactName | None = None
    join_keys: tuple[JoinKey, ...] = ()
    projection_id: str | None = None


def _keys(left_table: ArtifactName, right_table: ArtifactName,
          *pairs: tuple[str, str]) -> tuple[JoinKey, ...]:
    return tuple(
        JoinKey(PhysicalColumnRef(left_table, left), PhysicalColumnRef(right_table, right))
        for left, right in pairs
    )


@dataclass(frozen=True)
class RelationSpec:
    name: str
    left: str
    right: str
    source: str
    join_keys: tuple[tuple[str, str], ...]
    scope: tuple[str, ...]
    interpretation: str
    traps: tuple[int, ...]
    cardinality: Cardinality
    direction: str
    input_grain: str
    output_grain: str
    fanout_effect: FanoutEffect
    dedupe_strategy: str | None
    temporal_validity: TemporalValidity
    coverage: str
    path_cost: int
    risk: int
    binding: RelationBinding | None = None


_RELATION_SPECS = [
    RelationSpec(
        "belongs_to", "ProductListing", "Shop", "products_clean.csv + shop_info_clean.csv",
        (("country_code", "country_code"), ("shop_id", "shop_id")), ("country_code", "shop_id"),
        "Shop là latest/static enrichment tại 2026-07-03, không phải thuộc tính đồng thời từng ngày.",
        (7,), "N:1", "left_preserve:ProductListing", "listing_snapshot", "listing_snapshot",
        "none", None, "static_latest_only", "shop_info có 20 shop, chỉ một snapshot", 1, 1,
        RelationBinding(
            "left_join", (ArtifactName.PRODUCTS,), ArtifactName.SHOP_INFO,
            _keys(ArtifactName.PRODUCTS, ArtifactName.SHOP_INFO,
                  ("country_code", "country_code"), ("shop_id", "shop_id")),
            projection_id="belongs_to",
        ),
    ),
    RelationSpec(
        "observed_at", "ProductListing", "DateSnapshot", "products_clean.csv",
        (("date", "date"),), ("country_code", "shop_id", "item_id", "date"),
        "Một dòng là một listing-snapshot; số dòng không phải số listing.",
        (12, 20), "N:1", "left_preserve:ProductListing", "listing_snapshot", "listing_snapshot",
        "none", None, "per_snapshot", "3341 snapshot của 1157 listing; panel không cân bằng", 1, 1,
        RelationBinding("inline", (ArtifactName.PRODUCTS,)),
    ),
    RelationSpec(
        "in_platform_category", "ProductListing", "PlatformCategory", "products_clean.csv + category_platform_clean.csv",
        (("country_code", "path_country_code"), ("category_id", "category_id")), ("country_code",),
        "Chỉ nối platform category trong cùng country; catid là top-level, cuối global_catids là leaf.",
        (2,), "N:1", "left_preserve:ProductListing", "listing_snapshot", "listing_snapshot_category",
        "none", None, "per_snapshot", "0 orphan category path đã quan sát", 1, 1,
        # §E2.1: `products_clean.csv.category_id` KHÔNG tồn tại; key thật là
        # catid_num → category_id_num, và country nối country_code chứ không
        # phải path_country_code (cột provenance).
        RelationBinding(
            "left_join", (ArtifactName.PRODUCTS,), ArtifactName.CATEGORY_PLATFORM,
            _keys(ArtifactName.PRODUCTS, ArtifactName.CATEGORY_PLATFORM,
                  ("country_code", "country_code"), ("catid_num", "category_id_num")),
            projection_id="in_platform_category",
        ),
    ),
    RelationSpec(
        "in_shop_category", "ProductListing", "ShopCategory", "product_categories_clean.csv + category_list_clean.csv",
        (("country_code", "country_code"), ("shop_id", "shop_id"), ("category_id", "shop_category_id"), ("date", "date")),
        ("country_code", "shop_id", "date"),
        "Multi-membership chỉ hợp lệ ở cấp kệ; aggregate shop/thị trường phải dedupe về listing.",
        (2, 3), "N:M", "left_preserve:ProductListing", "listing_snapshot", "listing_snapshot_x_shelf",
        "duplicates_left_rows", "one_row_per_listing", "per_snapshot",
        "5 orphan; 1132 snapshot thiếu mapping nên dùng left join", 3, 3,
        # §E2.1: join chạy trên biến thể _num của category id, không phải cột text.
        RelationBinding(
            "left_join", (ArtifactName.PRODUCT_CATEGORIES,), ArtifactName.CATEGORY_LIST,
            _keys(ArtifactName.PRODUCT_CATEGORIES, ArtifactName.CATEGORY_LIST,
                  ("country_code", "country_code"), ("shop_id", "shop_id"),
                  ("category_id_num", "shop_category_id_num"), ("date", "date")),
            projection_id="in_shop_category",
        ),
    ),
    RelationSpec(
        # §E2.1: key cũ khai `raw_brand`, cột không tồn tại ở BẤT KỲ bảng nào.
        # Nó chưa gây sai số chỉ vì relation này inline nên compiler bỏ qua join;
        # đổi adapter là key giả đi thẳng vào SQL. Brand nằm sẵn trên left frame.
        "has_brand", "ProductListing", "Brand", "products_clean.csv",
        (("brand", "brand"),), ("country_code",),
        "Brand là raw attribute; không suy brand từ title và không coi là canonical identity.",
        (), "N:1", "left_preserve:ProductListing", "listing_snapshot", "listing_snapshot",
        "none", None, "per_snapshot", "nullable raw brand", 1, 1,
        RelationBinding("inline", (ArtifactName.PRODUCTS,)),
    ),
    RelationSpec(
        "observed_promotion_id", "ProductListing", "PromotionIdObservation", "products_clean.csv",
        (("promotion_id_num", "promotion_id_num"),), ("country_code", "shop_id", "item_id", "date"),
        "Observation theo snapshot; ID khác 0 không chứng minh promotion tạo discount.",
        (19,), "N:M", "left_preserve:ProductListing", "listing_snapshot", "listing_snapshot",
        "none", None, "per_snapshot", "promotion_id=0 là sentinel ở 874 dòng", 2, 2,
        RelationBinding("inline", (ArtifactName.PRODUCTS,)),
    ),
    RelationSpec(
        "observed_structured_voucher", "ProductListing", "VoucherObservation", "products_clean.csv",
        (("voucher_code", "voucher_code"),), ("country_code", "shop_id", "item_id", "date"),
        "Voucher là observation theo listing snapshot, không phải voucher master cố định theo item.",
        (19,), "1:N", "left_preserve:ProductListing", "listing_snapshot", "listing_snapshot_voucher",
        "none", None, "per_snapshot", "structured voucher chỉ quan sát ở VN", 2, 2,
        RelationBinding("inline", (ArtifactName.PRODUCTS,)),
    ),
    RelationSpec(
        "has_content", "ProductListing", "Content", "products_clean.csv",
        (("product_snapshot_key", "product_snapshot_key"),), ("country_code", "shop_id", "item_id", "date"),
        "images_count chỉ là feature đếm; không suy chất lượng content từ số ảnh.",
        (18,), "1:1", "left_preserve:ProductListing", "listing_snapshot", "listing_snapshot",
        "none", None, "per_snapshot", "content denormalized trên products", 1, 1,
        RelationBinding("inline", (ArtifactName.PRODUCTS,)),
    ),
    RelationSpec(
        "has_display_variation", "ProductListing", "Content", "products_clean.csv",
        (("product_snapshot_key", "product_snapshot_key"),), ("country_code", "shop_id", "item_id", "date"),
        "Variation chỉ là text hiển thị; không định danh hoặc theo dõi SKU.",
        (13,), "1:1", "left_preserve:ProductListing", "listing_snapshot", "listing_snapshot",
        "none", None, "per_snapshot", "không có sku_id/giá/tồn kho theo option", 1, 2,
        RelationBinding("inline", (ArtifactName.PRODUCTS,)),
    ),
    RelationSpec(
        "has_sales_metric", "ProductListing", "SalesMetric", "product_snapshot_metrics.csv + product_transition_metrics.csv",
        (("product_listing_key", "product_listing_key"),), ("country_code", "shop_id", "item_id"),
        "Sales fields là proxy và phải dùng Metric Registry để tính/diễn giải.",
        (4,), "1:N", "left_preserve:ProductListing", "listing", "listing_snapshot_or_transition",
        "duplicates_left_rows", "metric_grain_required", "per_snapshot", "snapshot và transition metrics", 2, 2,
        RelationBinding(
            "left_join", (ArtifactName.PRODUCTS,), ArtifactName.SNAPSHOT_METRICS,
            _keys(ArtifactName.PRODUCTS, ArtifactName.SNAPSHOT_METRICS,
                  ("product_listing_key", "product_listing_key")),
            projection_id="has_sales_metric",
        ),
    ),
]


def _build_registry(specs: list[RelationSpec]) -> dict[str, RelationSpec]:
    registry: dict[str, RelationSpec] = {}
    for spec in specs:
        if spec.name in registry:
            raise ValueError(f"Relation trùng tên: {spec.name}")
        if not spec.join_keys or not spec.scope or spec.path_cost < 1 or spec.risk < 0:
            raise ValueError(f"RelationSpec không hợp lệ: {spec.name}")
        if spec.fanout_effect != "none" and not spec.dedupe_strategy:
            raise ValueError(f"Relation fanout thiếu dedupe_strategy: {spec.name}")
        if spec.binding is None:
            raise ValueError(f"Relation thiếu binding vật lý: {spec.name}")
        if not spec.binding.left_sources:
            raise ValueError(f"Relation thiếu left source: {spec.name}")
        # Với relation có JOIN thật, ``join_keys`` được SINH từ binding thay vì
        # khai lần hai. Đây là chỗ đã drift: registry nói `category_id` còn SQL
        # chạy `catid_num`, và không ai so hai bên (§E2.1).
        if spec.binding.mode == "left_join":
            spec = replace(spec, join_keys=tuple(
                (key.left.column, key.right.column) for key in spec.binding.join_keys
            ))
        registry[spec.name] = spec
    return registry


RELATIONS = _build_registry(_RELATION_SPECS)

# Compatibility maps — SINH từ binding. Consumer cũ đọc tên artifact dạng chuỗi;
# không có literal thứ hai nào để lệch khỏi binding.
RELATION_LEFT_SOURCES: dict[str, tuple[str, ...]] = {
    name: tuple(source.value for source in spec.binding.left_sources)
    for name, spec in RELATIONS.items()
    if spec.binding is not None
}
INLINE_RELATIONS: frozenset[str] = frozenset(
    name for name, spec in RELATIONS.items()
    if spec.binding is not None and spec.binding.mode == "inline"
)
JOIN_RELATIONS: frozenset[str] = frozenset(RELATIONS) - INLINE_RELATIONS


def get(name: str) -> RelationSpec | None:
    return RELATIONS.get(name)


def find_path(left: str, right: str) -> tuple[RelationSpec, ...] | None:
    """Tìm đường join được phép, theo chiều khai báo và tổng path_cost nhỏ nhất."""
    if left == right:
        return ()
    queue: list[tuple[int, str, tuple[str, ...]]] = [(0, left, ())]
    best: dict[str, int] = {left: 0}
    while queue:
        cost, entity, names = heappop(queue)
        if entity == right:
            return tuple(RELATIONS[name] for name in names)
        if cost != best.get(entity):
            continue
        for relation in RELATIONS.values():
            if relation.left != entity:
                continue
            next_cost = cost + relation.path_cost
            if next_cost >= best.get(relation.right, 10**9):
                continue
            best[relation.right] = next_cost
            heappush(queue, (next_cost, relation.right, names + (relation.name,)))
    return None
