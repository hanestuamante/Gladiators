"""Executable semantic catalog theo V2 mục 5.5.

Catalog ánh xạ semantic refs sang cột vật lý. Planner chỉ thấy refs; compiler mới
được đọc ``physical``. Coverage manifest dùng cùng catalog để tránh hai nguồn
định nghĩa khác nhau.
"""
from __future__ import annotations


from dataclasses import dataclass, replace
from typing import Literal

from .metrics import METRICS, VALUE_CLASS_RULES
from .tables import PhysicalColumnRef, TableRegistryError, parse_physical

CatalogKind = Literal["entity", "dimension", "measure", "derived_metric", "context"]
Answerability = Literal[
    "exposed_as_dimension", "exposed_as_measure", "proxy_only", "raw_but_unsafe", "absent",
    "context_only",
]
SourceTier = Literal["btc_dataset", "reference", "external"]

# ``answerability`` conflates two questions that have different answers: "may a
# question reach this ref" and "what role does it play in a plan". An entity ref
# names the *unit* a measurement is taken over ("median price of listings"); a
# dimension names the *column* a result is split by ("median price by brand").
# Only the second needs a physical column, but both defaulted to
# ``exposed_as_dimension``, so 10 entity refs advertised themselves as groupable
# while owning nothing to GROUP BY. ``analysis_role`` states the role directly;
# ``answerability`` keeps its existing meaning so fixtures do not shift.
AnalysisRole = Literal[
    "physical_dimension",   # splits a result; must own a physical column
    "analysis_unit",        # names what one row is; countable, not a group key
    "computed_value",       # measured or derived quantity
    "context_only",         # never enters a LogicalQueryPlan
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
    source_tier: SourceTier = "btc_dataset"
    analysis_role: AnalysisRole = "computed_value"
    # Physical column identifying one instance of an analysis unit, for
    # COUNT(DISTINCT ...). Absent means the unit cannot be counted.
    counting_key: str | None = None
    # For a count metric: the entity ref whose instances it counts.
    counts_unit: str | None = None
    # W24-R1: ref này có được xuất hiện trong ``plan.group_by`` không. Mặc định
    # True ⇒ mọi ref cũ giữ nguyên hành vi. ``dim.item_id`` khai False vì gom
    # nhóm theo nó trả về một dòng mỗi listing — đó không phải một câu hỏi, và
    # nó lộ luôn một định danh nội bộ.
    groupable: bool = True
    # Bản đã parse của ``physical``, sinh ở ``_build_catalog``. ``physical`` giữ
    # nguyên một release cho fixture/serializer cũ; writer và compiler mới chỉ
    # đọc ``physical_bindings`` vì chỉ nó biết artifact nào là artifact nào
    # (chuỗi "a.b.csv.c" tách sai là một lỗi im lặng).
    physical_bindings: tuple[PhysicalColumnRef, ...] = ()


def _default_analysis_role(kind: CatalogKind, answerability: Answerability) -> AnalysisRole:
    if answerability == "context_only" or kind == "context":
        return "context_only"
    if kind == "entity":
        return "analysis_unit"
    if kind == "dimension":
        return "physical_dimension"
    return "computed_value"


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
    source_tier: SourceTier = "btc_dataset",
    counting_key: str | None = None,
    counts_unit: str | None = None,
    groupable: bool = True,
) -> CatalogObject:
    if answerability is None:
        answerability = "exposed_as_dimension" if kind in {"entity", "dimension"} else "exposed_as_measure"
    return CatalogObject(
        ref, kind, aliases, physical, type, unit, grain, aggregations, time, filters,
        cardinality, caveats, traps, "docs/design/V2_Unified_Architecture.md",
        value_index, answerability,
        source_tier,
        _default_analysis_role(kind, answerability),
        counting_key,
        counts_unit,
        groupable,
    )


_BASE_OBJECTS = [
    _object("entity.country", "entity", ("quốc gia", "country", "negara"), (), grain="country",
            counting_key="country_code"),
    # "gian hàng" đã là một surface của shop ở `agent/entity_extract.py`; thiếu
    # nó ở đây là hai danh sách cùng gọi một khái niệm mà lệch nhau — người dùng
    # gõ từ hệ ĐÃ nhận ở tầng trích thực thể và bị hỏi lại ở tầng catalog.
    _object("entity.shop", "entity", ("shop", "cửa hàng", "gian hàng", "toko"),
            tuple(f"{t}.shop_id" for t in ("products_clean.csv", "shop_info_clean.csv", "category_list_clean.csv", "product_categories_clean.csv", "product_snapshot_metrics.csv", "product_transition_metrics.csv")), grain="shop",
            counting_key="shop_id"),
    _object("entity.brand", "entity", ("thương hiệu", "brand", "merek"), (), grain="brand",
            counting_key="brand"),
    # "mặt hàng"/"hàng hóa" đã nằm trong `_RANKING_SUBJECT` của semantic_parser
    # và trong bảng intent của `agent/parser.py` — tức hệ VỐN coi chúng là cùng
    # một khái niệm với "sản phẩm"; chỉ catalog là chỗ chưa khai. Đo được:
    # "Ở Indonesia có bao nhiêu mặt hàng?" bị A19-CAT *"chưa xác định được chỉ
    # số nào cần đo"* trong khi cùng câu với "sản phẩm" trả 482.
    #
    # KHÔNG thêm "nhãn hàng": nó không xuất hiện ở đâu trong repo, và bịa một
    # cụm mới là mở lại đúng danh sách vô hạn mà W17 tồn tại để đóng.
    _object("entity.product_listing", "entity",
            ("listing", "sản phẩm", "mặt hàng", "hàng hóa", "produk"), (), grain="listing",
            counting_key="product_listing_key"),
    _object("entity.platform_category", "entity", ("danh mục sàn", "platform category"), (), grain="platform_category",
            counting_key="catid_num"),
    _object("entity.shop_category", "entity", ("kệ shop", "shop shelf"), (), grain="shop_category"),
    _object("entity.promotion_id_observation", "entity", ("promotion id quan sát", "promotion id observation", "observasi promo"), (), grain="listing_snapshot"),
    _object("entity.voucher_observation", "entity", ("voucher quan sát", "voucher observation", "observasi voucher"), (), grain="listing_snapshot"),
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
    # W24: THÊM cột trên bảng listing (cùng ref ⇒ không vi phạm luật "một cột
    # thuộc một ref"). Trước đó mọi câu lọc hay HIỆN TÊN shop phải đi quan hệ
    # `belongs_to`, và `_field()` chiếu `physical[0]` nên plan gom theo shop
    # xuất ra `shop_id` — câu trả lời in một định danh nội bộ.
    _object("dim.shop_name", "dimension", ("shop", "cửa hàng", "cua hang", "toko"),
            ("shop_info_clean.csv.shop_name", "products_clean.csv.shop_name"),
            time="static_latest"),
    # W24: catalog trước đây KHÔNG phơi `item_id` dù cột tồn tại, nên không plan
    # nào lọc được về một listing cụ thể và `_has_unbound_qualifier` từ chối mọi
    # câu hỏi nêu mã sản phẩm — đúng logic, nhưng cái nó bảo vệ là một khoảng
    # trống lấp được. `groupable=False`: gom nhóm theo item_id ra một dòng mỗi
    # listing, đó không phải một câu hỏi.
    _object("dim.item_id", "dimension",
            ("mã sản phẩm", "ma san pham", "mã listing", "ma listing",
             "item id", "product code", "kode produk"),
            ("products_clean.csv.item_id",),
            type="string", grain="listing", filters=("eq", "in"), groupable=False),
    _object("dim.platform_category_name", "dimension",
            ("danh mục sàn", "danh mục", "platform category", "category", "kategori"),
            ("category_platform_clean.csv.display_category_name",)),
    _object("dim.shop_category_name", "dimension", ("kệ shop", "shop shelf"), ("category_list_clean.csv.display_name",)),
    _object("dim.shop_official", "dimension", ("official shop", "shop chính hãng"), ("shop_info_clean.csv.is_official_shop_bool",), type="bool", time="static_latest"),
    _object("dim.shop_vacation", "dimension", ("shop nghỉ", "vacation"), ("shop_info_clean.csv.vacation_bool",), type="bool", time="static_latest"),
    _object("dim.shop_category_parent", "dimension", ("kệ cha", "parent shelf"), ("category_list_clean.csv.is_parent_category_bool",), type="bool"),
    _object("dim.shop_category_child", "dimension", ("kệ con", "child shelf"), ("category_list_clean.csv.is_sub_category_bool",), type="bool"),
    _object("dim.display_variation", "dimension", ("phân loại hiển thị", "display variation"),
            ("products_clean.csv.tier_variation_name", "products_clean.csv.tier_variation_options"), traps=(13,)),
    _object("dim.shopee_verified", "dimension", ("shopee verified", "đã xác minh"),
            ("products_clean.csv.shopee_verified_bool",), type="bool"),
    _object("dim.platform_category_has_children", "dimension", ("danh mục có nhánh con", "category has children", "kategori punya subkategori"),
            ("category_platform_clean.csv.has_children_bool",), type="bool"),
    # Phase 6 context namespace is intentionally non-physical. These objects can
    # help routing/catalog slicing but must never compile into SQL (E1/ADR-E1).
    _object(
        "context.campaign_window", "context", ("chiến dịch", "campaign", "kampanye"), (),
        grain="country_date", time="per_calendar_day", answerability="context_only",
        source_tier="external", caveats=(
            "Bối cảnh chiến dịch từ nguồn ngoài; không phải bằng chứng nhân quả cho biến động nội bộ.",
        ),
    ),
    _object(
        "context.theme_day", "context", ("ngày chủ đề", "theme day"), (),
        grain="country_date", time="per_calendar_day", answerability="context_only",
        source_tier="external", caveats=(
            "Ngày chủ đề là context công khai, không phải quan sát từ btc_dataset.",
        ),
    ),
    _object(
        "context.market_event", "context", ("sự kiện thị trường", "market event"), (),
        grain="country_date_window", time="event_window", answerability="context_only",
        source_tier="external", caveats=(
            "Sự kiện thị trường chỉ được dùng làm context_only và phải có provenance.",
        ),
    ),
]


# §3.2: every exposed object needs a Vietnamese alias and at least one English or
# Bahasa alias. Without these a measure is present in the catalogue but
# unreachable from a question -- exposed on paper, absent in practice. The
# technical name stays first so existing ref-shaped lookups keep working.
_MEASURE_ALIASES: dict[str, tuple[str, ...]] = {
    "price": ("giá", "giá bán", "harga"),
    "price_original": ("giá gốc", "giá niêm yết", "original price", "harga asli"),
    "price_before_promo": ("giá trước khuyến mãi", "giá trước giảm", "giá chưa giảm",
                           "price before promo", "harga sebelum promo"),
    # "giảm giá" is the everyday phrasing and was not an alias at all, so
    # longest-match only caught the "giá" nested inside it: the discount concept
    # disappeared and measure.price was bound to a question about discounts.
    # Wording taken from business-dictionary.md Metric 6/7 ("mức giảm giá",
    # "chương trình giảm giá"), not invented here.
    "discount_percent": ("phần trăm giảm giá", "mức giảm giá", "giảm giá",
                         "chương trình giảm giá", "discount", "diskon"),
    # "doanh số" is the everyday Vietnamese word for sales volume and was the
    # single largest alias gap measured over the eval corpus. It is distinct from
    # "doanh thu" (revenue), which belongs to derived.estimated_recent_revenue.
    "monthly_sold": ("lượt bán tháng", "đã bán trong tháng", "doanh số", "lượt bán",
                     "tình hình bán", "monthly sold", "sales", "terjual per bulan",
                     "penjualan"),
    "history_sold": ("lượt bán tích luỹ", "tổng đã bán", "total sold", "total terjual"),
    "voucher_discount": ("giá trị voucher", "mức giảm của voucher", "voucher value", "nilai voucher"),
    "voucher_min_spend": ("giá trị đơn tối thiểu", "chi tiêu tối thiểu", "minimum spend", "minimum belanja"),
    "voucher_start_time": ("thời điểm bắt đầu voucher", "voucher start", "mulai voucher"),
    "voucher_end_time": ("thời điểm kết thúc voucher", "voucher end", "akhir voucher"),
    "rating": ("điểm đánh giá", "sao đánh giá", "đánh giá", "rating", "penilaian"),
    # W4.3: thêm alias TRẦN "lượt đánh giá" — cùng lớp lỗi với "lượt thích".
    "rating_count": ("số lượt đánh giá", "lượt đánh giá", "số đánh giá",
                     "review count", "jumlah ulasan"),
    # W4.3: alias TRẦN — người dùng nói "nhiều lượt thích nhất", không nói "số
    # lượt thích nhiều nhất". "lượt thích" là chuỗi con của "thay đổi lượt
    # thích" (liked_delta); AliasIndex khớp DÀI TRƯỚC và xoá span đã nhận, nên
    # thứ tự đúng được bảo toàn — test khoá cả hai chiều.
    "liked_count": ("số lượt thích", "lượt thích", "lượt yêu thích", "likes",
                    "jumlah suka"),
    "images_count": ("số ảnh", "số lượng hình", "image count", "jumlah gambar"),
    "variation_options_count": ("số phân loại", "số tuỳ chọn hiển thị", "variation count", "jumlah variasi"),
    "vouchers_count": ("số nhãn voucher", "voucher label count", "jumlah voucher"),
    "shop_rating": ("điểm đánh giá shop", "sao của shop", "shop rating", "penilaian toko"),
    "shop_followers": ("số người theo dõi shop", "lượt theo dõi", "người theo dõi",
                       "followers", "follower", "pengikut toko", "pengikut"),
    "shop_items": ("số sản phẩm của shop", "quy mô shop", "shop item count", "jumlah produk toko"),
    "shop_response_rate": ("tỷ lệ phản hồi của shop", "mức phản hồi", "response rate", "tingkat respons"),
    "shop_response_time": ("thời gian phản hồi của shop", "tốc độ phản hồi", "response time", "waktu respons"),
    "shop_rating_good": ("số đánh giá tốt", "đánh giá tích cực", "good reviews", "ulasan baik"),
    "shop_rating_normal": ("số đánh giá trung bình", "đánh giá trung tính", "neutral reviews", "ulasan netral"),
    "shop_rating_bad": ("số đánh giá xấu", "đánh giá tiêu cực", "bad reviews", "ulasan buruk"),
    "shop_cancellation_rate": ("tỷ lệ huỷ đơn của shop", "mức huỷ đơn", "cancellation rate", "tingkat pembatalan"),
    "shop_category_total": ("tổng sản phẩm trong kệ", "số sản phẩm mỗi kệ", "shelf total", "total rak"),
}

_MEASURES: dict[str, tuple[tuple[str, ...], str, str, tuple[int, ...], Answerability]] = {
    "price": (("products_clean.csv.price_num", "product_snapshot_metrics.csv.price_num"), "local_currency", "number", (5,), "exposed_as_measure"),
    "price_original": (("products_clean.csv.price_original_num", "product_snapshot_metrics.csv.price_original_num"), "local_currency", "number", (1, 5), "exposed_as_measure"),
    # Cột `price_before_promo_num` CÓ THẬT và phủ 100% ở cả hai bản dữ liệu,
    # nhưng chưa từng được khai làm semantic object — nên "giá trước khuyến mãi
    # của sản phẩm X" không bind được gì và rơi vào A-NO-EVIDENCE. Cùng đơn vị,
    # cùng bẫy sentinel 999999999 với `price`/`price_original`.
    "price_before_promo": (("products_clean.csv.price_before_promo_num",), "local_currency", "number", (1, 5), "exposed_as_measure"),
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

# ── W26: khai TÍNH CHẤT, suy ra PHÉP ────────────────────────────────────────
#
# ``valid_aggregations`` trước đây là một tuple phẳng gán tay, giống hệt nhau cho
# mọi measure (``median/min/max``). Một bảng phẳng không phát biểu được *vì sao*
# một phép hợp lệ hay không, nên mỗi mục là một quyết định không kiểm lại được và
# lời từ chối chỉ nói được "catalog chưa chứng nhận" — một câu mô tả REGISTRY,
# không mô tả ĐẠI LƯỢNG.
Additivity = Literal[
    "additive", "ordinal", "snapshot_stock", "ratio", "count", "proxy_window",
]

AGGREGATIONS_BY_ADDITIVITY: dict[str, tuple[str, ...]] = {
    # đếm sự vật; cộng qua các dòng có nghĩa
    "additive":       ("sum", "mean", "median", "min", "max"),
    # thang THỨ BẬC: trung bình sao không phải trung bình của gì cả
    "ordinal":        ("median", "min", "max"),
    # cộng giá qua các listing vô nghĩa
    "snapshot_stock": ("median", "mean", "min", "max"),
    "ratio":          ("share", "median", "mean"),
    "count":          ("count",),
    # proxy của một cửa sổ CHƯA XÁC NHẬN — cộng qua snapshot là tính TRÙNG
    "proxy_window":   ("median", "min", "max"),
}

ADDITIVITY_BY_MEASURE: dict[str, str] = {
    "liked_count": "additive", "rating_count": "additive",
    "images_count": "additive", "vouchers_count": "additive",
    "variation_options_count": "additive",
    "rating": "ordinal", "shop_rating": "ordinal",
    # Spec3008 §13.2: cộng giá qua các listing vô nghĩa, nhưng TRUNG BÌNH giá
    # thì có nghĩa — "giá trung bình của listing tại VN" là một đại lượng đọc
    # được. W26-R2: nới đúng phần chứng minh được.
    "price": "snapshot_stock", "price_original": "snapshot_stock",
    "price_before_promo": "snapshot_stock",
    "price_before_promo": "snapshot_stock", "discount_percent": "snapshot_stock",
    "monthly_sold": "proxy_window", "history_sold": "proxy_window",
}

# Lý do có KIỂU cho một phép bị từ chối. Nói về đại lượng, không về bảng.
AGGREGATION_REFUSAL: dict[tuple[str, str], str] = {
    ("ordinal", "mean"): (
        "Điểm đánh giá là thang thứ bậc; trung bình của nó không phải một điểm "
        "đánh giá. Có thể hỏi trung vị."
    ),
    ("ordinal", "sum"): (
        "Điểm đánh giá là thang thứ bậc; cộng các điểm lại không tạo ra một đại "
        "lượng có nghĩa."
    ),
    ("proxy_window", "sum"): (
        "Chỉ số này là proxy của một cửa sổ chưa xác nhận; cộng qua các đợt thu "
        "sẽ tính trùng cùng một lượt bán."
    ),
    ("snapshot_stock", "sum"): (
        "Cộng giá của nhiều listing không tạo ra một mức giá; hãy hỏi trung vị "
        "hoặc tổng giá trị ước tính."
    ),
}


def refusal_for_aggregation(measure_ref: str, aggregation: str) -> str | None:
    """Vì sao phép này không được chứng nhận cho đại lượng này (W26-R1)."""
    name = measure_ref.split(".", 1)[-1]
    additivity = ADDITIVITY_BY_MEASURE.get(name)
    if additivity is None:
        return None
    return AGGREGATION_REFUSAL.get((additivity, aggregation))


for name, (physical, unit, type_, traps, status) in _MEASURES.items():
    caveats = ["Dùng đúng grain và scope theo metric/relation registry."]
    if name in {"price", "price_original", "price_before_promo"}:
        caveats.append("Loại sentinel 999999999 bằng filter < 999999999 trước aggregate hoặc rank.")
    if name in {"monthly_sold", "history_sold"}:
        caveats.append("Đây là proxy hiển thị của sàn, không phải dữ liệu đơn hàng đã kiểm chứng.")
    if name == "variation_options_count":
        caveats.append("Số option hiển thị không phải số SKU.")
    _BASE_OBJECTS.append(_object(
        f"measure.{name}", "measure",
        (name.replace("_", " "),) + _MEASURE_ALIASES.get(name, ()), physical,
        type=type_, unit=unit,
        # W26: phép được chứng nhận SUY RA từ tính chất cộng được, không gán tay.
        # Measure chưa khai tính chất giữ nguyên bộ cũ — nới phải là nới đúng
        # phần chứng minh được, không phải nới cả bảng.
        aggregations=AGGREGATIONS_BY_ADDITIVITY.get(
            ADDITIVITY_BY_MEASURE.get(name, ""), ("median", "min", "max"),
        ),
        filters=("eq", "lt", "lte", "gt", "gte"), traps=traps, answerability=status,
        caveats=tuple(caveats),
    ))


# ── Panel ngày cấp shop (artifact tuỳ chọn ``shop_stats_clean.csv``) ─────────
#
# Chín measure ``measure.shop_*`` ở trên đọc ``shop_info_clean.csv`` — MỘT ảnh
# chụp, ngữ nghĩa ``static_latest``. Lần thu 07/2026 cho một panel 20 ngày, tức
# một đại lượng KHÁC: "điểm shop hôm nay" và "điểm shop tại ngày d" trả lời hai
# câu hỏi khác nhau. Đặt chung một ref sẽ khiến một câu hỏi theo thời gian được
# trả bằng một con số tĩnh mà không ai thấy, nên chúng là ref RIÊNG, grain
# riêng, alias riêng có chữ chỉ thời gian.
#
# Bản dữ liệu chưa thu panel này ⇒ artifact vắng ⇒ compiler chặn tại
# ``available_sources`` và câu hỏi bị từ chối vì THIẾU DỮ LIỆU, không phải vì
# không hiểu câu hỏi.
_SHOP_PANEL: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "shop_daily_rating": ("rating_star_num", "rating_point", "number",
                          ("điểm đánh giá shop theo ngày", "điểm shop từng ngày",
                           "daily shop rating")),
    "shop_daily_followers": ("follower_count_num", "followers", "number",
                             ("người theo dõi shop theo ngày", "lượt theo dõi từng ngày",
                              "daily followers")),
    "shop_daily_items": ("item_count_num", "items", "number",
                         ("số sản phẩm của shop theo ngày", "quy mô shop từng ngày",
                          "daily item count")),
    "shop_daily_response_rate": ("response_rate_num", "percent", "number",
                                 ("tỷ lệ phản hồi theo ngày", "daily response rate")),
    "shop_daily_response_time": ("response_time_num", "time", "number",
                                 ("thời gian phản hồi theo ngày", "daily response time")),
    "shop_daily_cancellation_rate": ("cancellation_rate_num", "percent", "number",
                                     ("tỷ lệ huỷ đơn theo ngày", "daily cancellation rate")),
    "shop_daily_rating_good": ("rating_good_num", "ratings", "number",
                               ("số đánh giá tốt theo ngày", "daily good reviews")),
    "shop_daily_rating_normal": ("rating_normal_num", "ratings", "number",
                                 ("số đánh giá trung bình theo ngày", "daily neutral reviews")),
    "shop_daily_rating_bad": ("rating_bad_num", "ratings", "number",
                              ("số đánh giá xấu theo ngày", "daily bad reviews")),
    "shop_daily_rating_total": ("rating_total_num", "ratings", "number",
                                ("tổng số đánh giá của shop", "tổng lượt đánh giá shop",
                                 "total shop ratings")),
    "shop_daily_following": ("following_count_num", "accounts", "number",
                             ("số tài khoản shop theo dõi", "shop following count")),
}

for name, (column, unit, type_, aliases) in _SHOP_PANEL.items():
    _BASE_OBJECTS.append(_object(
        f"measure.{name}", "measure",
        (name.replace("_", " "),) + aliases,
        (f"shop_stats_clean.csv.{column}",),
        type=type_, unit=unit, grain="shop_snapshot",
        aggregations=("median", "min", "max"),
        filters=("eq", "lt", "lte", "gt", "gte"),
        answerability="exposed_as_measure",
        caveats=(
            "Grain là (shop, ngày) — KHÔNG phải listing; đừng gộp với measure ở "
            "cấp listing mà không đi qua relation.",
            "Chỉ có ở bản dữ liệu đã thu shop_stats; bản cũ chỉ có ảnh chụp tĩnh "
            "trong measure.shop_* tương ứng.",
        ),
    ))


# §3.2: same rule as measures -- a derived metric with only its technical name
# cannot be reached from a Vietnamese question, which is how a governed metric
# ends up looking absent to the user.
_DERIVED_ALIASES: dict[str, tuple[str, ...]] = {
    "estimated_recent_revenue": ("doanh thu ước tính", "doanh thu proxy", "doanh thu",
                                 "estimated revenue", "revenue", "pendapatan perkiraan",
                                 "pendapatan"),
    "monthly_sold_delta": ("thay đổi lượt bán tháng", "biến động lượt bán",
                           "biến động doanh số", "thay đổi doanh số", "biến động bán",
                           "monthly sold change", "perubahan penjualan"),
    "history_sold_delta_raw": ("thay đổi lượt bán tích luỹ", "cumulative sold change"),
    "history_sold_delta_clean": ("thay đổi lượt bán đã làm sạch", "clean sold change"),
    "history_sold_decrease_flag": ("cờ lượt bán giảm", "sold decrease flag"),
    "price_change": ("thay đổi giá", "biến động giá", "price change", "perubahan harga"),
    "price_change_pct": ("phần trăm thay đổi giá", "mức biến động giá", "price change percent"),
    "discount_point_change": ("thay đổi điểm giảm giá", "discount point change"),
    "voucher_state_transition": ("thay đổi trạng thái voucher", "voucher state change"),
    "rating_change": ("thay đổi điểm đánh giá", "rating change"),
    "rating_count_delta": ("số đánh giá mới", "new ratings"),
    "liked_delta": ("thay đổi lượt thích", "likes change"),
    # Bare concept words ("voucher", "khuyến mãi") had no binding at all, so a
    # question like "So sánh voucher tại Việt Nam" resolved to nothing and routed
    # as unknown even though T3 answers it. Longest-alias-first matching means
    # the more specific phrases above still win where they appear.
    # W8.3: surface chung "có voucher"/"voucher" nằm trên CẢ HAI ref — alias
    # collision là CÓ CHỦ ĐÍCH: _link thấy hai ứng viên và fail-closed bằng
    # A-ANALYTICAL-AMBIGUITY thay vì chọn thầm một khái niệm. KHÔNG thêm chúng
    # vào PREFERRED_REF_BY_SURFACE.
    "has_structured_voucher": ("voucher có cấu trúc", "mã voucher có cấu trúc",
                               "có voucher", "có mã giảm giá", "voucher",
                               "mã giảm giá", "has voucher", "punya voucher"),
    "has_voucher_label": ("có nhãn voucher", "voucher hiển thị", "nhãn voucher",
                          "có voucher", "voucher", "has voucher",
                          "has voucher label"),
    "has_promo": ("có khuyến mãi", "đang khuyến mãi", "khuyến mãi", "promotion",
                  "promo", "has promotion", "ada promo"),
    # W11.2: alias khớp CẢ CỤM, không khớp "tỷ lệ" trần — "tỷ lệ" một mình không
    # nói mẫu số là gì, và một tỷ lệ không có mẫu số khai báo là đúng thứ
    # INV-PROXY-NOT-VERIFIED-SALES và _lineage_gaps tồn tại để chặn.
    "discounted_listing_count": ("số listing có giảm giá", "số listing giảm giá",
                                 "jumlah listing diskon"),
    "discounted_listing_rate": ("tỷ lệ listing có giảm giá", "tỷ lệ listing giảm giá",
                                "phần trăm listing giảm giá",
                                "phần trăm listing có giảm giá",
                                "persentase listing diskon"),
    "discount_bucket": ("nhóm mức giảm giá", "khoảng giảm giá", "discount bucket"),
    "median_monthly_sold": ("lượt bán trung vị", "median monthly sold"),
    "median_estimated_recent_revenue": ("doanh thu ước tính trung vị", "median estimated revenue"),
    "product_count": ("số listing", "số sản phẩm", "bao nhiêu listing", "bao nhiêu sản phẩm",
                      "listing count", "how many listing", "jumlah produk", "berapa listing",
                      "berapa produk"),
    "shop_count": ("số shop", "số cửa hàng", "bao nhiêu shop", "bao nhiêu cửa hàng",
                   "shop count", "berapa toko", "jumlah toko"),
    "brand_count": ("số thương hiệu", "bao nhiêu thương hiệu", "brand count", "jumlah merek"),
    "category_count": ("số danh mục", "bao nhiêu danh mục", "category count", "jumlah kategori"),
    "descriptive_gap_vs_baseline": ("chênh lệch so với nhóm nền", "gap versus baseline"),
    "descriptive_gap_median_sold": ("chênh lệch lượt bán trung vị", "median sold gap"),
    "text_sim": ("độ tương đồng tiêu đề", "title similarity"),
    "category_overlap_depth": ("độ trùng danh mục", "category overlap"),
    "brand_match": ("trùng thương hiệu", "brand match"),
    "price_distance": ("khoảng cách giá", "price distance"),
    "same_shelf_bonus": ("cùng kệ shop", "same shelf"),
    "similarity_score": ("điểm tương đồng", "sản phẩm tương tự", "sản phẩm giống",
                         "tương tự", "giống", "đối thủ cạnh tranh", "đối thủ",
                         "similarity score", "skor kemiripan", "similar",
                         "competitor", "mirip", "serupa", "pesaing"),
    "voucher_rate": ("tỷ lệ có voucher", "voucher rate"),
    "median_discount_ratio": ("tỷ lệ giảm giá trung vị", "median discount ratio"),
    "voucher_profile_score": ("điểm hồ sơ voucher", "voucher profile score"),
}

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
    # W11.2: cờ giảm giá dùng quan sát đã materialize, không suy lại từ
    # discount tại query time.
    "has_promo": ("product_snapshot_metrics.csv.has_displayed_discount",),
}
# W8.3 — CHỆCH KHỎI SPEC CÓ CHỦ ĐÍCH: spec muốn _DERIVED_PHYSICAL ánh xạ
# has_voucher_label → vouchers_count, nhưng bất biến "một cột vật lý thuộc đúng
# một ref" (có trước W8.3, bảo vệ physical_index mà _project_relation đọc) chặn
# — cột đó đã thuộc measure.vouchers_count. Cùng predicate đạt được bằng cách
# cho QUALIFIER nhãn bind thẳng measure.vouchers_count với op gte 1; ref
# derived.has_voucher_label giữ vai trò KHÁI NIỆM cho alias/ambiguity.

# Which analysis unit each count metric counts. The compiler reads the physical
# key from the entity rather than matching a ref name, so adding a countable unit
# is a catalog edit, not another branch in ``_column_for``.
# W4.2 — chiều nào, khi đứng ngay sau một từ để hỏi số lượng, là "đếm đơn vị
# nào". Đếm shop_name phân biệt KHÔNG bằng đếm shop: metric đích mang
# counts_unit riêng (entity.shop → counting_key shop_id) và phép đếm vẫn chạy
# trên khoá đó.
# W25-R1 — KHOÁ GOM NHÓM và NHÃN HIỂN THỊ là HAI thứ.
#
# Gom nhóm theo ``shop_id`` là đúng: nó là khoá. Nhưng ``_field()`` đặt tên cột
# chiếu bằng ``physical[0]``, nên plan gom theo shop chiếu ra ``shop_id`` và câu
# trả lời in ``108166524`` thay vì tên shop — một định danh NỘI BỘ rò ra ngoài
# (``INV-NO-INTERNAL-VOCABULARY``).
LABEL_REF_BY_UNIT: dict[str, str] = {
    "entity.shop": "dim.shop_name",
    "entity.brand": "dim.brand",
    "entity.platform_category": "dim.platform_category_name",
    "entity.product_listing": "dim.product_name",
}

COUNT_METRIC_BY_SURFACE_REF: dict[str, str] = {
    "dim.brand":                  "derived.brand_count",
    "entity.brand":               "derived.brand_count",
    "dim.shop_name":              "derived.shop_count",
    "entity.shop":                "derived.shop_count",
    "dim.platform_category_name": "derived.category_count",
    "entity.platform_category":   "derived.category_count",
    "dim.product_name":           "derived.product_count",
    "entity.product_listing":     "derived.product_count",
}

_COUNTS_UNIT = {
    "product_count": "entity.product_listing",
    "discounted_listing_count": "entity.product_listing",
    "shop_count": "entity.shop",
    "brand_count": "entity.brand",
    "category_count": "entity.platform_category",
}

for name, spec in METRICS.items():
    _BASE_OBJECTS.append(_object(
        f"derived.{name}", "derived_metric",
        (name.replace("_", " "),) + _DERIVED_ALIASES.get(name, ()),
        _DERIVED_PHYSICAL.get(name, ()),
        type="number", unit=spec.unit, grain=spec.grain,
        aggregations=spec.valid_aggregations, filters=("eq", "lt", "lte", "gt", "gte"),
        caveats=spec.caveats, traps=spec.traps,
        answerability="proxy_only" if name in {"estimated_recent_revenue", "monthly_sold_delta", "history_sold_delta_raw", "history_sold_delta_clean"} else "exposed_as_measure",
        counts_unit=_COUNTS_UNIT.get(name),
    ))


class CatalogError(ValueError):
    """Raised at import when the catalog contradicts itself. Build-breaking by design."""


# W1.2 · Chiều mang TÊN của một đơn vị phân tích. Câu hỏi nêu tên shop dùng
# surface "shop", mà surface đó giải thành entity.shop (đơn vị đếm) chứ không
# phải dim.shop_name (chiều mang tên) — nên giá trị không bao giờ được bind và
# câu "listing CỦA shop X" bị đọc thành "listing THEO TỪNG shop": một câu hỏi
# khác, trả lời trong im lặng. Đo được: 120 listing của Richy - Chi nhánh Miền
# Nam bị trả thành bảng đếm theo 10 shop.
VALUE_DIMENSION_BY_UNIT: dict[str, str] = {
    "entity.shop": "dim.shop_name",
    "entity.brand": "dim.brand",
    "entity.platform_category": "dim.platform_category_name",
}


def _build_catalog(objects: list[CatalogObject]) -> dict[str, CatalogObject]:
    catalog: dict[str, CatalogObject] = {}
    physical: dict[str, str] = {}
    for obj in objects:
        if obj.ref in catalog:
            raise CatalogError(f"Catalog ref trùng: {obj.ref}")
        for column in obj.physical:
            if column in physical:
                raise CatalogError(f"Physical column {column} thuộc cả {physical[column]} và {obj.ref}")
            physical[column] = obj.ref
        # Parse ngay tại build: một mapping trỏ artifact không tồn tại phải làm
        # import fail, không đợi tới lúc compile một câu hỏi cụ thể.
        try:
            bindings = tuple(parse_physical(column) for column in obj.physical)
        except TableRegistryError as exc:
            raise CatalogError(f"{obj.ref}: {exc}") from exc
        obj = replace(obj, physical_bindings=bindings)
        # A2: a ref that claims it can be grouped by must own a column to group
        # by. Without this the contradiction only surfaced at compile time, as an
        # uncaught CompilationError rather than a decision with a rule_id.
        if obj.analysis_role == "physical_dimension" and not obj.physical:
            raise CatalogError(
                f"{obj.ref} khai physical_dimension nhưng không có cột vật lý nào để GROUP BY."
            )
        if obj.counts_unit and obj.counts_unit not in {item.ref for item in objects}:
            raise CatalogError(f"{obj.ref} đếm đơn vị không tồn tại: {obj.counts_unit}")
        catalog[obj.ref] = obj
    for obj in catalog.values():
        if obj.counts_unit and not catalog[obj.counts_unit].counting_key:
            raise CatalogError(
                f"{obj.ref} đếm {obj.counts_unit} nhưng đơn vị đó không có counting_key."
            )
    return catalog


CATALOG = _build_catalog(_BASE_OBJECTS)

# W1.2: kiểm VALUE_DIMENSION_BY_UNIT lúc import, theo đúng khuôn _build_catalog —
# một ánh xạ trỏ ref không tồn tại (hoặc chiều không có cột vật lý để lọc) phải
# fail build, không đợi tới lúc một câu hỏi cụ thể chạm vào nó.
for _unit_ref, _dim_ref in VALUE_DIMENSION_BY_UNIT.items():
    if _unit_ref not in CATALOG:
        raise CatalogError(f"VALUE_DIMENSION_BY_UNIT: đơn vị không tồn tại: {_unit_ref}")
    if _dim_ref not in CATALOG:
        raise CatalogError(f"VALUE_DIMENSION_BY_UNIT: chiều không tồn tại: {_dim_ref}")
    if not CATALOG[_dim_ref].physical:
        raise CatalogError(
            f"VALUE_DIMENSION_BY_UNIT: {_dim_ref} không có cột vật lý — không lọc được"
        )


# W4.2: mọi khoá/giá trị của bảng đếm-theo-chiều phải tồn tại, và metric đích
# phải là một metric ĐẾM — gõ sai một ref phải nổ lúc import, không phải lúc
# một câu hỏi vô tình chạm vào nó.
for _unit_ref, _label_ref in LABEL_REF_BY_UNIT.items():
    if _unit_ref not in CATALOG or _label_ref not in CATALOG:
        raise CatalogError(
            f"LABEL_REF_BY_UNIT trỏ tới ref không tồn tại: {_unit_ref} → {_label_ref}",
        )
    if not CATALOG[_label_ref].physical:
        raise CatalogError(
            f"LABEL_REF_BY_UNIT: nhãn {_label_ref} không có cột vật lý nào để chiếu",
        )

for _surface_ref, _count_ref in COUNT_METRIC_BY_SURFACE_REF.items():
    if _surface_ref not in CATALOG or _count_ref not in CATALOG:
        raise CatalogError(
            f"COUNT_METRIC_BY_SURFACE_REF trỏ tới ref không tồn tại: "
            f"{_surface_ref} -> {_count_ref}",
        )
    if not CATALOG[_count_ref].counts_unit:
        raise CatalogError(
            f"COUNT_METRIC_BY_SURFACE_REF: {_count_ref} không phải metric đếm",
        )

# W14.1: ref của mọi ValueClassRule phải TỒN TẠI. Kiểm ở đây thay vì trong
# metrics.py vì module này import module đó — kiểm ngược lại là một vòng import.
for _rule in VALUE_CLASS_RULES:
    for _ref in (_rule.ref, _rule.companion_ref):
        if _ref is not None and _ref not in CATALOG:
            raise CatalogError(
                f"ValueClassRule {_rule.rule_id} trỏ tới ref không có trong catalog: {_ref}",
            )

# Reverse of ``counts_unit``: the metric that counts a given analysis unit.
COUNT_METRIC_BY_UNIT: dict[str, str] = {
    obj.counts_unit: ref for ref, obj in CATALOG.items() if obj.counts_unit
}


def counting_column(ref: str) -> str | None:
    """Physical column for COUNT(DISTINCT ...) behind a count metric or unit."""
    obj = CATALOG.get(ref)
    if obj is None:
        return None
    if obj.counts_unit:
        return CATALOG[obj.counts_unit].counting_key
    return obj.counting_key


def get(ref: str) -> CatalogObject | None:
    return CATALOG.get(ref)


def physical_index() -> dict[str, CatalogObject]:
    return {column: obj for obj in CATALOG.values() for column in obj.physical}


def catalog_slice(refs: tuple[str, ...]) -> tuple[CatalogObject, ...]:
    missing = sorted(set(refs) - CATALOG.keys())
    if missing:
        raise KeyError(f"Semantic refs không tồn tại: {missing}")
    return tuple(CATALOG[ref] for ref in refs)
