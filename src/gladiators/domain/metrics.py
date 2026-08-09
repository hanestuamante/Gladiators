"""Metric registry as code — nguồn DUY NHẤT cho định nghĩa metric (V2 mục 5.1).

Mọi metric/định nghĩa nghiệp vụ sống ở đúng một nơi (quyết định khóa #3). Tool và
planner chỉ ĐỌC registry, không định nghĩa lại công thức. Mỗi entry khai báo 6
trường bắt buộc: name, grain, unit, dedupe, caveats, traps — cộng valid_aggregations
để planner biết phép aggregate nào hợp lệ (mục 7.5).

`caveats` là bắt buộc chèn vào evidence payload (không phải tùy chọn của generator).
`traps` trỏ về số hiệu bẫy dữ liệu (mục 0.6) mà metric này xử lý — dùng cho bảng
traceability mục 5.4.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Grain = Literal["snapshot", "transition", "group", "pair"]
Dedupe = Literal["none", "one_snapshot_per_listing"]
Aggregation = Literal["count", "sum", "mean", "median", "min", "max", "share"]


@dataclass(frozen=True)
class MetricSpec:
    name: str
    grain: Grain
    unit: str
    dedupe: Dedupe
    caveats: tuple[str, ...]
    traps: tuple[int, ...]
    depends_on: tuple[str, ...] = ()           # cột nguồn (contract projection, mục 4.2)
    valid_aggregations: tuple[Aggregation, ...] = ()
    formula: str = ""                          # mô tả công thức (tài liệu; compute ở analytics layer)


_METRIC_SPECS = [
    MetricSpec(
        name="monthly_sold_delta", grain="transition", unit="units_recent_window",
        dedupe="none", traps=(4, 15, 20), depends_on=("monthly_sold_value_num",),
        formula="msv(T) - msv(T-1)",
        caveats=("lượt bán gần đây theo Shopee hiển thị, cửa sổ chưa xác nhận",
                 "cần ≥2 snapshot hợp lệ của cùng listing; giảm không tự động là lỗi"),
    ),
    MetricSpec(
        name="history_sold_delta_raw", grain="transition", unit="units_cumulative",
        dedupe="none", traps=(4,), depends_on=("history_sold_value_num",),
        formula="hsv(T) - hsv(T-1); flag khi <0; clean = raw nếu ≥0, ngược lại null",
        caveats=("proxy lũy kế hiển thị; history_sold_decrease_flag đánh dấu anomaly (88/2136, toàn VN)",
                 "khi flag=True cấm diễn giải 'lượng bán mới phát sinh'; loại khỏi phép cộng incremental"),
    ),
    MetricSpec(
        name="history_sold_decrease_flag", grain="transition", unit="bool",
        dedupe="none", traps=(4,), depends_on=("history_sold_value_num",),
        formula="history_sold_delta_raw < 0",
        caveats=("data-quality anomaly, không phải bằng chứng lượt bán thực tế giảm",),
    ),
    MetricSpec(
        name="history_sold_delta_clean", grain="transition", unit="units_cumulative",
        dedupe="none", traps=(4,), depends_on=("history_sold_value_num",),
        formula="history_sold_delta_raw nếu >= 0, ngược lại null",
        caveats=("transition có history_sold_decrease_flag=True bị loại khỏi phép cộng incremental",),
    ),
    MetricSpec(
        name="price_change", grain="transition", unit="local_currency",
        dedupe="none", traps=(5,), depends_on=("price_num",),
        formula="p(T) - p(T-1)",
        caveats=("loại 3 dòng sentinel price=999999999 trước khi tính",),
    ),
    MetricSpec(
        name="price_change_pct", grain="transition", unit="percent",
        dedupe="none", traps=(5,), depends_on=("price_num",),
        formula="100 * (p(T)-p(T-1)) / p(T-1); p(T-1) ∈ {0,NaN} → null + flag chia-0",
        caveats=("loại sentinel trước; chia-0 trả null có flag",),
    ),
    MetricSpec(
        name="discount_point_change", grain="transition", unit="percent_point",
        dedupe="none", traps=(), depends_on=("discount_percent_num",),
        formula="dp(T) - dp(T-1)",
        caveats=("missing chỉ fill 0 khi price == price_original (307 dòng); ngược lại giữ null + flag",),
    ),
    MetricSpec(
        name="voucher_state_transition", grain="transition", unit="state",
        dedupe="none", traps=(19,),
        depends_on=("voucher_discount_num", "voucher_min_spend_num", "voucher_code"),
        formula="so trạng thái structured voucher giữa 2 snapshot",
        caveats=("NaN-vs-NaN phải loại trước khi đếm 'đổi' (tránh đếm nhầm 1125 transition)",),
    ),
    MetricSpec(
        name="rating_change", grain="transition", unit="rating_point",
        dedupe="none", traps=(), depends_on=("rating_num",),
        formula="rating(T) - rating(T-1)", caveats=("NaN → loại transition",),
    ),
    MetricSpec(
        name="rating_count_delta", grain="transition", unit="ratings",
        dedupe="none", traps=(), depends_on=("rating_count_num",),
        formula="rating_count(T) - rating_count(T-1)", caveats=("NaN → loại transition",),
    ),
    MetricSpec(
        name="liked_delta", grain="transition", unit="likes",
        dedupe="none", traps=(), depends_on=("liked_count_num",),
        formula="liked_count(T) - liked_count(T-1)", caveats=("NaN → loại transition",),
    ),
    MetricSpec(
        name="estimated_recent_revenue", grain="snapshot", unit="local_currency",
        dedupe="one_snapshot_per_listing", traps=(4, 5),
        depends_on=("price_num", "monthly_sold_value_num"),
        valid_aggregations=("median", "sum", "mean"),
        formula="price_num * monthly_sold_value_num",
        caveats=("luôn label 'ước tính'; không phải doanh thu/GMV",
                 "monthly_sold là proxy; CẤM cộng qua 3 snapshot; loại sentinel trước"),
    ),
    MetricSpec(
        name="has_structured_voucher", grain="snapshot", unit="bool",
        dedupe="one_snapshot_per_listing", traps=(19,),
        depends_on=("voucher_discount_num",), valid_aggregations=("count", "share"),
        formula="voucher_discount_num > 0 (NaN ⇒ False)",
        caveats=("1580/1580 dòng True đều thuộc VN; ID=0 → so VN-ID nhóm voucher = abstain (A11)",),
    ),
    MetricSpec(
        name="has_voucher_label", grain="snapshot", unit="bool",
        dedupe="none", traps=(19,), depends_on=("vouchers_count",),
        formula="vouchers_count > 0",
        caveats=("label UI hỗn hợp (Pilih Lokal, Add-on Deal) ≠ structured voucher; KHÔNG dùng lập nhóm chính",),
    ),
    MetricSpec(
        name="has_promo", grain="snapshot", unit="bool",
        dedupe="none", traps=(19,), depends_on=("discount_percent_num",),
        formula="discount_percent_num > 0",
        caveats=("G9: mọi dòng có voucher đều has_promo=True ⇒ chỉ 3 nhóm thực tế; CẤM dựng 4 nhóm",),
    ),
    MetricSpec(
        name="discount_bucket", grain="snapshot", unit="bucket",
        dedupe="one_snapshot_per_listing", traps=(), depends_on=("discount_percent_num",),
        valid_aggregations=("count", "share"),
        formula="bins discount_percent_num: {0} (0,10] (10,20] (20,40] (40,100]",
        caveats=("không gọi là 'promotion'; bins đề xuất, DR1 chốt sau EDA",),
    ),
    MetricSpec(
        name="median_monthly_sold", grain="group", unit="units_recent_window",
        dedupe="one_snapshot_per_listing", traps=(4,),
        depends_on=("monthly_sold_value_num",), valid_aggregations=("median",),
        formula="median trong nhóm tại 1 snapshot đã chọn, cùng country",
        caveats=("median (không mean) chống outlier; luôn báo sample size; proxy hiển thị",),
    ),
    MetricSpec(
        name="median_estimated_recent_revenue", grain="group", unit="local_currency",
        dedupe="one_snapshot_per_listing", traps=(4, 5),
        depends_on=("price_num", "monthly_sold_value_num"), valid_aggregations=("median",),
        formula="median(estimated_recent_revenue) trong nhóm",
        caveats=("revenue là proxy 'ước tính'; 1 snapshot + dedupe listing; không so chéo VN-ID (G12)",),
    ),
    MetricSpec(
        name="product_count", grain="group", unit="listings",
        dedupe="one_snapshot_per_listing", traps=(3, 12), valid_aggregations=("count",),
        formula="count listing trong nhóm sau dedupe về grain products",
        caveats=("1 snapshot + dedupe listing; group theo kệ được double count nhưng tổng phải dedupe",),
    ),
    # "Count the distinct instances of X" was modelled for exactly one entity, so
    # "có bao nhiêu shop ở VN" bound no measure at all and fell to A19-CAT even
    # though shop_id sits in the data. One spec per countable unit, all reading
    # their key from the entity's catalog entry rather than a compiler special-case.
    MetricSpec(
        name="shop_count", grain="group", unit="shops",
        dedupe="one_snapshot_per_listing", traps=(), valid_aggregations=("count",),
        formula="count distinct shop_id trong nhóm tại 1 snapshot",
        caveats=("đếm shop quan sát được trong dataset, không phải toàn bộ shop trên sàn",),
    ),
    MetricSpec(
        name="brand_count", grain="group", unit="brands",
        dedupe="one_snapshot_per_listing", traps=(), valid_aggregations=("count",),
        formula="count distinct brand trong nhóm tại 1 snapshot",
        caveats=("brand là raw attribute chưa chuẩn hoá; listing thiếu brand không được đếm",),
    ),
    MetricSpec(
        name="category_count", grain="group", unit="categories",
        dedupe="one_snapshot_per_listing", traps=(2,), valid_aggregations=("count",),
        formula="count distinct catid_num trong nhóm tại 1 snapshot",
        caveats=("đếm danh mục sàn gắn với listing quan sát được, không phải toàn bộ cây danh mục",),
    ),
    MetricSpec(
        name="descriptive_gap_vs_baseline", grain="group", unit="same_as_source_metric",
        dedupe="one_snapshot_per_listing", traps=(9, 19),
        formula="median(nhóm) - median(baseline không voucher cùng scope)",
        caveats=("wording thuần quan sát 'khác biệt mô tả'; CẤM 'hiệu quả/gây ra/tác động'",),
    ),
    MetricSpec(
        name="text_sim", grain="pair", unit="score_0_1",
        dedupe="one_snapshot_per_listing", traps=(16,), depends_on=("product_name_clean",),
        formula="cosine similarity trên embedding title đã kiểm chứng",
        caveats=("điểm gần nhau theo title, không chứng minh cùng sản phẩm",),
    ),
    MetricSpec(
        name="category_overlap_depth", grain="pair", unit="score_0_1",
        dedupe="one_snapshot_per_listing", traps=(2,), depends_on=("global_catids",),
        formula="|path_a ∩ path_b| / max(|path_a|, |path_b|)",
        caveats=("chỉ dùng platform category path cùng country; không nối shop category",),
    ),
    MetricSpec(
        name="brand_match", grain="pair", unit="score_0_1",
        dedupe="one_snapshot_per_listing", traps=(), depends_on=("brand",),
        formula="1 nếu raw brand bằng nhau; 0 nếu khác; 0.5 nếu thiếu",
        caveats=("brand là raw attribute, không phải canonical brand identity",),
    ),
    MetricSpec(
        name="price_distance", grain="pair", unit="score_0_1",
        dedupe="one_snapshot_per_listing", traps=(5,), depends_on=("price_num",),
        formula="1 - min(1, abs(pa-pb)/pa)",
        caveats=("pa null, <=0 hoặc sentinel thì loại candidate ở blocking",),
    ),
    MetricSpec(
        name="same_shelf_bonus", grain="pair", unit="score_0_1",
        dedupe="one_snapshot_per_listing", traps=(2, 3),
        formula="overlap shop shelf khi hai listing cùng shop",
        caveats=("membership qua in_shop_category; không đồng nhất shop shelf với platform category",),
    ),
    MetricSpec(
        name="similarity_score", grain="pair", unit="score_0_1",
        dedupe="one_snapshot_per_listing", traps=(16,),
        depends_on=("product_name_clean", "global_catids", "price_num", "brand"),
        formula="Σ wᵢ·(text_sim, category_overlap_depth, brand_match, price_distance, same_shelf_bonus)",
        caveats=("'tương tự' theo thành phần điểm — không khẳng định cùng mẫu (không có nhãn same-product)",),
    ),
    # --- voucher_profile_rank_v1 (V2 §2.8, T-11) — descriptive multi-signal, KHÔNG causal ---
    MetricSpec(
        name="voucher_rate", grain="group", unit="share_0_1",
        dedupe="one_snapshot_per_listing", traps=(9, 19),
        depends_on=("has_structured_voucher",),
        formula="share(has_structured_voucher) per shop @ 1 snapshot",
        caveats=("tỷ lệ listing có structured voucher tại một snapshot; không nói gì về hiệu quả",),
    ),
    MetricSpec(
        name="median_discount_ratio", grain="group", unit="ratio_0_1",
        dedupe="one_snapshot_per_listing", traps=(9, 19),
        depends_on=("voucher_discount_num", "price_num"),
        formula="median(voucher_discount_num / price_num) trên dòng có voucher, price>0",
        caveats=("độ sâu giảm giá mô tả; voucher_discount là mức giảm hiển thị, chưa xác nhận điều kiện áp dụng",),
    ),
    MetricSpec(
        name="descriptive_gap_median_sold", grain="group", unit="units_recent_window",
        dedupe="one_snapshot_per_listing", traps=(4, 9, 19),
        depends_on=("monthly_sold_value_num", "has_structured_voucher"),
        formula="median(monthly_sold | voucher) - median(monthly_sold | không voucher) trong CÙNG shop",
        caveats=("chênh lệch mô tả tại 1 snapshot trong cùng shop; hai nhóm khác cơ cấu sản phẩm/giá — không phải bằng chứng nhân quả",),
    ),
    MetricSpec(
        name="voucher_profile_score", grain="group", unit="score_0_1",
        dedupe="one_snapshot_per_listing", traps=(9, 19),
        depends_on=("has_structured_voucher", "voucher_discount_num", "price_num", "monthly_sold_value_num"),
        formula=(
            "voucher_profile_rank_v1: 0.4·norm(voucher_rate) + 0.3·norm(median_discount_ratio) "
            "+ 0.3·norm(descriptive_gap_median_sold); min-max normalize trên các shop đủ điều kiện "
            "(n_listings ≥ 5, có đủ cả hai nhóm voucher/không-voucher)"
        ),
        caveats=(
            "ranking mô tả theo định nghĩa voucher_profile_rank_v1, không đo hiệu quả nhân quả",
            "weights 0.4/0.3/0.3 chờ DR1/Lead phê duyệt (T-11) — chỉ phục vụ khi cờ bật",
            "shop dưới ngưỡng sample hoặc thiếu một nhóm bị loại khỏi ranking và được đếm riêng",
        ),
    ),
]


def _build_registry(specs: list[MetricSpec]) -> dict[str, MetricSpec]:
    registry: dict[str, MetricSpec] = {}
    for spec in specs:
        if spec.name in registry:
            raise ValueError(f"Metric trùng tên: {spec.name}")
        if not spec.name or not spec.unit or not spec.formula or not spec.caveats:
            raise ValueError(f"MetricSpec thiếu contract bắt buộc: {spec.name!r}")
        registry[spec.name] = spec
    return registry


METRICS: dict[str, MetricSpec] = _build_registry(_METRIC_SPECS)


def get(name: str) -> MetricSpec | None:
    return METRICS.get(name)


def names() -> tuple[str, ...]:
    return tuple(METRICS)
