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

from dataclasses import dataclass, replace
from typing import Literal, Mapping

Grain = Literal["snapshot", "transition", "group", "pair"]
Dedupe = Literal["none", "one_snapshot_per_listing"]
Aggregation = Literal["count", "sum", "mean", "median", "min", "max", "share"]
# W11.1: cùng chuẩn op với planner — nguồn thật nằm ngay trong domain.
from .predicate_ops import ExecutablePredicateOp as ConstraintOp  # noqa: E402
NullPolicy = Literal["exclude", "false", "propagate"]


ValueClass = Literal[
    "measurement",       # giá trị là một phép đo thật (mặc định, không đổi gì)
    "placeholder",       # ô "không có giá trị" được điền bằng một số
    "display_ceiling",   # trần hiển thị của sàn: giá trị thật >= số này
    "no_observation",    # null bị mã hoá thành 0 (chưa ai đánh giá, chưa ai thích)
]


class ValueClassError(ValueError):
    """Registry lớp giá trị tự mâu thuẫn — nổ lúc import, không lúc chạy."""


@dataclass(frozen=True)
class ValueClassRule:
    """Luật nhận ra một giá trị KHÔNG phải phép đo.

    ``repdigit_nine`` khớp một số nguyên dương mà MỌI chữ số đều là 9 và có ít
    nhất ``min_digits`` chữ số. Luật theo ĐẶC TÍNH, nên nó sống sót qua một lần
    làm mới dữ liệu; một danh sách ID thì không.

    ``decision_id is None`` nghĩa là ĐÃ PHÁT HIỆN, CHƯA DUYỆT: luật đó không
    được loại dòng nào — loại dòng là đổi định nghĩa metric, và đó là quyết
    định của chủ dữ liệu, không phải của code.
    """

    rule_id: str
    ref: str
    kind: Literal["repdigit_nine", "equals", "companion_is_zero"]
    value_class: ValueClass
    min_digits: int | None = None
    values: tuple[float, ...] = ()
    companion_ref: str | None = None
    decision_id: str | None = None      # None = ĐÃ PHÁT HIỆN, CHƯA DUYỆT


@dataclass(frozen=True)
class MetricConstraint:
    """Filter thuộc ĐỊNH NGHĨA metric, không phải predicate của người hỏi.

    Trộn hai thứ này làm "doanh thu ước tính" của một câu hỏi có filter khác với
    "doanh thu ước tính" của câu hỏi kế bên mà không ai thấy. ``decision_id`` bắt
    buộc: một constraint chưa ai duyệt không được lẻn vào định nghĩa.
    """

    constraint_id: str
    ref: str
    op: ConstraintOp
    values: tuple[object, ...]
    null_policy: NullPolicy
    decision_id: str


@dataclass(frozen=True)
class ShareDefinition:
    """Một tỷ lệ cần MẪU SỐ được khai — W11.2 (SolutionSpec2808 §12.3).

    Mẫu số là một quyết định nghiệp vụ: "tỷ lệ listing có giảm giá" có mẫu số là
    TOÀN BỘ listing của scope, không phải listing có dữ liệu giảm giá. Suy "tỷ
    lệ" thành một phép chia ở runtime là để một cách diễn đạt chọn hộ quyết định
    đó trong im lặng.
    """

    condition_ref: str
    condition_op: ConstraintOp
    condition_value: object
    numerator_metric: str
    denominator_metric: str
    scale: Literal[1, 100]
    null_policy: Literal["false", "exclude"]


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
    # --- lineage typed (§E4) ---------------------------------------------
    # ``depends_on`` trộn raw column với metric name nên consumer không biết một
    # cạnh thuộc loại nào, và sáu phụ thuộc metric→metric chỉ nhìn thấy được bằng
    # cách tìm chuỗi trong ``formula``. Substring matching cho impact analysis có
    # cả false positive lẫn false negative và không phát hiện được cycle.
    source_columns: tuple[str, ...] = ()
    source_metrics: tuple[str, ...] = ()
    definition_constraints: tuple[MetricConstraint, ...] = ()
    owner: str = "data-owner"
    tags: tuple[str, ...] = ()
    share: ShareDefinition | None = None


_METRIC_SPECS = [
    MetricSpec(
        name="monthly_sold_delta", grain="transition", unit="units_recent_window",
        dedupe="none", traps=(4, 15, 20), depends_on=("monthly_sold_value_num",),
        source_columns=("monthly_sold_value_num",), owner="data-engineering",
        tags=("transition", "sales_proxy"),
        formula="msv(T) - msv(T-1)",
        caveats=("lượt bán gần đây theo Shopee hiển thị, cửa sổ chưa xác nhận",
                 "cần ≥2 snapshot hợp lệ của cùng listing; giảm không tự động là lỗi"),
    ),
    MetricSpec(
        name="history_sold_delta_raw", grain="transition", unit="units_cumulative",
        dedupe="none", traps=(4,), depends_on=("history_sold_value_num",),
        source_columns=("history_sold_value_num",), owner="data-engineering",
        tags=("transition", "sales_proxy"),
        formula="hsv(T) - hsv(T-1); flag khi <0; clean = raw nếu ≥0, ngược lại null",
        caveats=("proxy lũy kế hiển thị; history_sold_decrease_flag đánh dấu anomaly (88/2136, toàn VN)",
                 "khi flag=True cấm diễn giải 'lượng bán mới phát sinh'; loại khỏi phép cộng incremental"),
    ),
    MetricSpec(
        name="history_sold_decrease_flag", grain="transition", unit="bool",
        dedupe="none", traps=(4,), depends_on=("history_sold_value_num",),
        source_metrics=("history_sold_delta_raw",), owner="data-engineering",
        tags=("transition", "data_quality"),
        formula="history_sold_delta_raw < 0",
        caveats=("data-quality anomaly, không phải bằng chứng lượt bán thực tế giảm",),
    ),
    MetricSpec(
        name="history_sold_delta_clean", grain="transition", unit="units_cumulative",
        dedupe="none", traps=(4,), depends_on=("history_sold_value_num",),
        source_metrics=("history_sold_delta_raw",), owner="data-engineering",
        tags=("transition", "sales_proxy"),
        formula="history_sold_delta_raw nếu >= 0, ngược lại null",
        caveats=("transition có history_sold_decrease_flag=True bị loại khỏi phép cộng incremental",),
    ),
    MetricSpec(
        name="price_change", grain="transition", unit="local_currency",
        dedupe="none", traps=(5,), depends_on=("price_num",),
        source_columns=("price_num",), owner="data-owner", tags=("transition", "price"),
        formula="p(T) - p(T-1)",
        caveats=("loại 3 dòng sentinel price=999999999 trước khi tính",),
    ),
    MetricSpec(
        name="price_change_pct", grain="transition", unit="percent",
        dedupe="none", traps=(5,), depends_on=("price_num",),
        source_columns=("price_num",), owner="data-owner", tags=("transition", "price"),
        formula="100 * (p(T)-p(T-1)) / p(T-1); p(T-1) ∈ {0,NaN} → null + flag chia-0",
        caveats=("loại sentinel trước; chia-0 trả null có flag",),
    ),
    MetricSpec(
        name="discount_point_change", grain="transition", unit="percent_point",
        dedupe="none", traps=(), depends_on=("discount_percent_num",),
        source_columns=("discount_percent_num",), owner="data-owner",
        tags=("transition", "discount"),
        formula="dp(T) - dp(T-1)",
        caveats=("missing chỉ fill 0 khi price == price_original (307 dòng); ngược lại giữ null + flag",),
    ),
    MetricSpec(
        name="voucher_state_transition", grain="transition", unit="state",
        dedupe="none", traps=(19,),
        depends_on=("voucher_discount_num", "voucher_min_spend_num", "voucher_code"),
        source_columns=("voucher_discount_num", "voucher_min_spend_num", "voucher_code"),
        owner="data-owner", tags=("transition", "voucher"),
        formula="so trạng thái structured voucher giữa 2 snapshot",
        caveats=("NaN-vs-NaN phải loại trước khi đếm 'đổi' (tránh đếm nhầm 1125 transition)",),
    ),
    MetricSpec(
        name="rating_change", grain="transition", unit="rating_point",
        dedupe="none", traps=(), depends_on=("rating_num",),
        source_columns=("rating_num",), owner="data-engineering", tags=("transition",),
        formula="rating(T) - rating(T-1)", caveats=("NaN → loại transition",),
    ),
    MetricSpec(
        name="rating_count_delta", grain="transition", unit="ratings",
        dedupe="none", traps=(), depends_on=("rating_count_num",),
        source_columns=("rating_count_num",), owner="data-engineering", tags=("transition",),
        formula="rating_count(T) - rating_count(T-1)", caveats=("NaN → loại transition",),
    ),
    MetricSpec(
        name="liked_delta", grain="transition", unit="likes",
        dedupe="none", traps=(), depends_on=("liked_count_num",),
        source_columns=("liked_count_num",), owner="data-engineering", tags=("transition",),
        formula="liked_count(T) - liked_count(T-1)", caveats=("NaN → loại transition",),
    ),
    MetricSpec(
        name="estimated_recent_revenue", grain="snapshot", unit="local_currency",
        dedupe="one_snapshot_per_listing", traps=(4, 5),
        depends_on=("price_num", "monthly_sold_value_num"),
        source_columns=("price_num", "monthly_sold_value_num"),
        owner="data-owner", tags=("snapshot", "revenue_proxy", "price"),
        valid_aggregations=("median", "sum", "mean"),
        formula="price_num * monthly_sold_value_num",
        caveats=("luôn label 'ước tính'; không phải doanh thu/GMV",
                 "monthly_sold là proxy; CẤM cộng qua 3 snapshot; loại sentinel trước"),
    ),
    MetricSpec(
        name="has_structured_voucher", grain="snapshot", unit="bool",
        dedupe="one_snapshot_per_listing", traps=(19,),
        depends_on=("voucher_discount_num",), valid_aggregations=("count", "share"),
        source_columns=("voucher_discount_num",), owner="data-owner",
        tags=("snapshot", "voucher", "vn_only"),
        definition_constraints=(
            MetricConstraint(
                constraint_id="structured-voucher-positive", ref="measure.voucher_discount",
                op="gt", values=(0,), null_policy="false",
                decision_id="existing-metric-contract",
            ),
        ),
        formula="voucher_discount_num > 0 (NaN ⇒ False)",
        caveats=("1580/1580 dòng True đều thuộc VN; ID=0 → so VN-ID nhóm voucher = abstain (A11)",),
    ),
    MetricSpec(
        name="has_voucher_label", grain="snapshot", unit="bool",
        dedupe="none", traps=(19,), depends_on=("vouchers_count",),
        source_columns=("vouchers_count",), owner="data-owner", tags=("snapshot", "voucher"),
        formula="vouchers_count > 0",
        caveats=("label UI hỗn hợp (Pilih Lokal, Add-on Deal) ≠ structured voucher; KHÔNG dùng lập nhóm chính",),
    ),
    MetricSpec(
        # W11.2: dùng quan sát ĐÃ MATERIALIZE thay vì suy lại từ discount tại
        # query time — hai công thức của cùng một cờ là hai chỗ để chúng lệch.
        name="has_promo", grain="snapshot", unit="bool",
        dedupe="one_snapshot_per_listing", traps=(19,),
        depends_on=("has_displayed_discount",),
        source_columns=("has_displayed_discount",), owner="data-owner",
        tags=("snapshot", "discount"),
        formula="has_displayed_discount; null theo null_policy của consumer",
        caveats=("G9: mọi dòng có voucher đều has_promo=True ⇒ chỉ 3 nhóm thực tế; CẤM dựng 4 nhóm",),
    ),
    MetricSpec(
        name="discounted_listing_count", grain="group", unit="listings",
        dedupe="one_snapshot_per_listing", traps=(),
        source_columns=("product_listing_key",), source_metrics=("has_promo",),
        valid_aggregations=("count",), owner="data-engineering",
        tags=("group", "count", "discount"),
        formula="count distinct listing where has_promo=True",
        caveats=("Đếm cờ giảm giá hiển thị tại đúng một snapshot.",),
    ),
    MetricSpec(
        name="discounted_listing_rate", grain="group", unit="percent",
        dedupe="one_snapshot_per_listing", traps=(),
        source_metrics=("discounted_listing_count", "product_count"),
        valid_aggregations=("share",), owner="data-owner",
        tags=("group", "share", "discount"),
        formula="100 * discounted_listing_count / product_count",
        share=ShareDefinition(
            condition_ref="derived.has_promo", condition_op="eq",
            condition_value=True,
            numerator_metric="discounted_listing_count",
            denominator_metric="product_count",
            scale=100, null_policy="false",
        ),
        caveats=("Mẫu số là toàn bộ listing trong scope; cờ giảm giá null được tính là không có cờ.",),
    ),
    MetricSpec(
        name="discount_bucket", grain="snapshot", unit="bucket",
        dedupe="one_snapshot_per_listing", traps=(), depends_on=("discount_percent_num",),
        valid_aggregations=("count", "share"),
        source_columns=("discount_percent_num",), owner="data-owner",
        tags=("snapshot", "discount", "pending_decision"),
        formula="bins discount_percent_num: {0} (0,10] (10,20] (20,40] (40,100]",
        caveats=("không gọi là 'promotion'; bins đề xuất, DR1 chốt sau EDA",),
    ),
    MetricSpec(
        name="median_monthly_sold", grain="group", unit="units_recent_window",
        dedupe="one_snapshot_per_listing", traps=(4,),
        depends_on=("monthly_sold_value_num",), valid_aggregations=("median",),
        source_columns=("monthly_sold_value_num",), owner="data-owner",
        tags=("group", "sales_proxy"),
        formula="median trong nhóm tại 1 snapshot đã chọn, cùng country",
        caveats=("median (không mean) chống outlier; luôn báo sample size; proxy hiển thị",),
    ),
    MetricSpec(
        name="median_estimated_recent_revenue", grain="group", unit="local_currency",
        dedupe="one_snapshot_per_listing", traps=(4, 5),
        depends_on=("price_num", "monthly_sold_value_num"), valid_aggregations=("median",),
        source_metrics=("estimated_recent_revenue",), owner="data-owner",
        tags=("group", "revenue_proxy"),
        formula="median(estimated_recent_revenue) trong nhóm",
        caveats=("revenue là proxy 'ước tính'; 1 snapshot + dedupe listing; không so chéo VN-ID (G12)",),
    ),
    MetricSpec(
        name="product_count", grain="group", unit="listings",
        dedupe="one_snapshot_per_listing", traps=(3, 12), valid_aggregations=("count",),
        source_columns=("product_listing_key",), owner="data-engineering", tags=("group", "count"),
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
        source_columns=("shop_id",), owner="data-engineering", tags=("group", "count"),
        formula="count distinct shop_id trong nhóm tại 1 snapshot",
        caveats=("đếm shop quan sát được trong dataset, không phải toàn bộ shop trên sàn",),
    ),
    MetricSpec(
        name="brand_count", grain="group", unit="brands",
        dedupe="one_snapshot_per_listing", traps=(), valid_aggregations=("count",),
        source_columns=("brand",), owner="data-engineering", tags=("group", "count"),
        formula="count distinct brand trong nhóm tại 1 snapshot",
        caveats=("brand là raw attribute chưa chuẩn hoá; listing thiếu brand không được đếm",),
    ),
    MetricSpec(
        name="category_count", grain="group", unit="categories",
        dedupe="one_snapshot_per_listing", traps=(2,), valid_aggregations=("count",),
        source_columns=("catid_num",), owner="data-engineering", tags=("group", "count", "category"),
        formula="count distinct catid_num trong nhóm tại 1 snapshot",
        caveats=("đếm danh mục sàn gắn với listing quan sát được, không phải toàn bộ cây danh mục",),
    ),
    MetricSpec(
        name="descriptive_gap_vs_baseline", grain="group", unit="same_as_source_metric",
        dedupe="one_snapshot_per_listing", traps=(9, 19),
        # Template áp lên một metric khác: nguồn là tham số, không phải cột cố
        # định — nên lineage kết thúc ở tool chứ không ở column (unit của nó
        # cũng nói đúng thế: "same_as_source_metric").
        owner="data-owner", tags=("group", "observational", "tool_computed"),
        formula="median(nhóm) - median(baseline không voucher cùng scope)",
        caveats=("wording thuần quan sát 'khác biệt mô tả'; CẤM 'hiệu quả/gây ra/tác động'",),
    ),
    MetricSpec(
        name="text_sim", grain="pair", unit="score_0_1",
        dedupe="one_snapshot_per_listing", traps=(16,), depends_on=("product_name_clean",),
        source_columns=("product_name_clean",), owner="architecture", tags=("pair", "similarity"),
        formula="cosine similarity trên embedding title đã kiểm chứng",
        caveats=("điểm gần nhau theo title, không chứng minh cùng sản phẩm",),
    ),
    MetricSpec(
        name="category_overlap_depth", grain="pair", unit="score_0_1",
        dedupe="one_snapshot_per_listing", traps=(2,), depends_on=("global_catids",),
        source_columns=("global_catids",), owner="architecture", tags=("pair", "similarity", "category"),
        formula="|path_a ∩ path_b| / max(|path_a|, |path_b|)",
        caveats=("chỉ dùng platform category path cùng country; không nối shop category",),
    ),
    MetricSpec(
        name="brand_match", grain="pair", unit="score_0_1",
        dedupe="one_snapshot_per_listing", traps=(), depends_on=("brand",),
        source_columns=("brand",), owner="architecture", tags=("pair", "similarity"),
        formula="1 nếu raw brand bằng nhau; 0 nếu khác; 0.5 nếu thiếu",
        caveats=("brand là raw attribute, không phải canonical brand identity",),
    ),
    MetricSpec(
        name="price_distance", grain="pair", unit="score_0_1",
        dedupe="one_snapshot_per_listing", traps=(5,), depends_on=("price_num",),
        source_columns=("price_num",), owner="architecture", tags=("pair", "similarity", "price"),
        formula="1 - min(1, abs(pa-pb)/pa)",
        caveats=("pa null, <=0 hoặc sentinel thì loại candidate ở blocking",),
    ),
    MetricSpec(
        name="same_shelf_bonus", grain="pair", unit="score_0_1",
        dedupe="one_snapshot_per_listing", traps=(2, 3),
        source_columns=("shop_id", "category_id_num"), owner="architecture",
        tags=("pair", "similarity", "shop_category"),
        formula="overlap shop shelf khi hai listing cùng shop",
        caveats=("membership qua in_shop_category; không đồng nhất shop shelf với platform category",),
    ),
    MetricSpec(
        name="similarity_score", grain="pair", unit="score_0_1",
        dedupe="one_snapshot_per_listing", traps=(16,),
        depends_on=("product_name_clean", "global_catids", "price_num", "brand"),
        # Năm cạnh này trước đây chỉ nhìn thấy được bằng cách tìm chuỗi trong
        # ``formula``; ``depends_on`` liệt kê cột nguồn của các thành phần chứ
        # không phải chính các thành phần.
        source_metrics=("text_sim", "category_overlap_depth", "brand_match",
                        "price_distance", "same_shelf_bonus"),
        owner="architecture", tags=("pair", "similarity", "composite"),
        formula="Σ wᵢ·(text_sim, category_overlap_depth, brand_match, price_distance, same_shelf_bonus)",
        caveats=("'tương tự' theo thành phần điểm — không khẳng định cùng mẫu (không có nhãn same-product)",),
    ),
    # --- voucher_profile_rank_v1 (V2 §2.8, T-11) — descriptive multi-signal, KHÔNG causal ---
    MetricSpec(
        name="voucher_rate", grain="group", unit="share_0_1",
        dedupe="one_snapshot_per_listing", traps=(9, 19),
        depends_on=("has_structured_voucher",),
        source_metrics=("has_structured_voucher",), owner="data-owner",
        tags=("group", "voucher", "observational", "vn_only"),
        formula="share(has_structured_voucher) per shop @ 1 snapshot",
        caveats=("tỷ lệ listing có structured voucher tại một snapshot; không nói gì về hiệu quả",),
    ),
    MetricSpec(
        name="median_discount_ratio", grain="group", unit="ratio_0_1",
        dedupe="one_snapshot_per_listing", traps=(9, 19),
        depends_on=("voucher_discount_num", "price_num"),
        source_columns=("voucher_discount_num", "price_num"), owner="data-owner",
        tags=("group", "voucher", "discount", "observational"),
        formula="median(voucher_discount_num / price_num) trên dòng có voucher, price>0",
        caveats=("độ sâu giảm giá mô tả; voucher_discount là mức giảm hiển thị, chưa xác nhận điều kiện áp dụng",),
    ),
    MetricSpec(
        name="descriptive_gap_median_sold", grain="group", unit="units_recent_window",
        dedupe="one_snapshot_per_listing", traps=(4, 9, 19),
        depends_on=("monthly_sold_value_num", "has_structured_voucher"),
        source_columns=("monthly_sold_value_num",),
        source_metrics=("has_structured_voucher",), owner="data-owner",
        tags=("group", "voucher", "sales_proxy", "observational", "vn_only"),
        formula="median(monthly_sold | voucher) - median(monthly_sold | không voucher) trong CÙNG shop",
        caveats=("chênh lệch mô tả tại 1 snapshot trong cùng shop; hai nhóm khác cơ cấu sản phẩm/giá — không phải bằng chứng nhân quả",),
    ),
    MetricSpec(
        name="voucher_profile_score", grain="group", unit="score_0_1",
        dedupe="one_snapshot_per_listing", traps=(9, 19),
        depends_on=("has_structured_voucher", "voucher_discount_num", "price_num", "monthly_sold_value_num"),
        # ``depends_on`` cũ chỉ thấy has_structured_voucher, trong khi công thức
        # dùng ba metric con. Caveat VN-only của has_structured_voucher tới đây
        # qua voucher_rate; không có lineage này thì nó không truyền được.
        source_metrics=("voucher_rate", "median_discount_ratio", "descriptive_gap_median_sold"),
        owner="data-owner",
        tags=("group", "voucher", "composite", "observational", "pending_decision"),
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


class MetricGraphError(ValueError):
    """Raised at import khi lineage không resolve, tự tham chiếu hoặc có cycle."""


@dataclass(frozen=True)
class MetricImpact:
    changed: tuple[str, ...]
    direct_consumers: tuple[str, ...]
    transitive_consumers: tuple[str, ...]
    affected_constraints: tuple[str, ...]
    inherited_caveats: tuple[tuple[str, str], ...]   # (source_metric, caveat)


@dataclass(frozen=True)
class MetricGraph:
    """DAG metric→metric đã kiểm, cộng cạnh metric→column.

    Không parse ``formula``. Substring matching có false positive ("rate" nằm
    trong một tên dài hơn), false negative (đổi cách viết công thức) và không
    bao giờ phát hiện được cycle.
    """

    specs: Mapping[str, MetricSpec]
    consumers: Mapping[str, tuple[str, ...]]      # metric -> metric dùng nó
    cycles: tuple[tuple[str, ...], ...] = ()

    def edge_count(self) -> int:
        return sum(len(spec.source_metrics) for spec in self.specs.values())

    def ancestors(self, metric: str) -> tuple[str, ...]:
        """Mọi metric mà ``metric`` phụ thuộc vào, theo path."""
        seen: list[str] = []
        stack = list(self.specs[metric].source_metrics)
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.append(current)
            stack.extend(self.specs[current].source_metrics)
        return tuple(sorted(seen))

    def descendants(self, metric: str) -> tuple[str, ...]:
        seen: list[str] = []
        stack = list(self.consumers.get(metric, ()))
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.append(current)
            stack.extend(self.consumers.get(current, ()))
        return tuple(sorted(seen))

    def impact_of(self, metric: str) -> MetricImpact:
        if metric not in self.specs:
            raise MetricGraphError(f"Metric không tồn tại: {metric}")
        direct = tuple(sorted(self.consumers.get(metric, ())))
        transitive = self.descendants(metric)
        affected = tuple(sorted(
            constraint.constraint_id
            for name in (metric,) + transitive
            for constraint in self.specs[name].definition_constraints
        ))
        return MetricImpact(
            changed=(metric,), direct_consumers=direct,
            transitive_consumers=transitive, affected_constraints=affected,
            inherited_caveats=self.effective_caveats(metric),
        )

    def effective_caveats(self, metric: str) -> tuple[tuple[str, str], ...]:
        """Caveat của chính metric cộng caveat truyền lên theo lineage.

        Trả về cặp ``(metric nguồn, caveat)`` và dedupe theo cặp: chép text vào
        metric cha làm mất chỗ caveat sinh ra, và mất chỗ sinh ra thì không ai
        biết caveat còn đúng hay không khi metric nguồn đổi.
        """
        if metric not in self.specs:
            raise MetricGraphError(f"Metric không tồn tại: {metric}")
        pairs: list[tuple[str, str]] = []
        for name in (metric,) + self.ancestors(metric):
            for caveat in self.specs[name].caveats:
                if (name, caveat) not in pairs:
                    pairs.append((name, caveat))
        return tuple(pairs)


def _find_cycles(specs: Mapping[str, MetricSpec]) -> tuple[tuple[str, ...], ...]:
    cycles: list[tuple[str, ...]] = []
    state: dict[str, int] = {}   # 0 = đang thăm, 1 = xong

    def walk(name: str, path: tuple[str, ...]) -> None:
        if state.get(name) == 1:
            return
        if state.get(name) == 0:
            cycles.append(path[path.index(name):] + (name,))
            return
        state[name] = 0
        for parent in specs[name].source_metrics:
            walk(parent, path + (name,))
        state[name] = 1

    for name in sorted(specs):
        walk(name, ())
    return tuple(cycles)


def build_metric_graph(specs: Mapping[str, MetricSpec]) -> MetricGraph:
    consumers: dict[str, list[str]] = {name: [] for name in specs}
    for name, spec in specs.items():
        if name in spec.source_metrics:
            raise MetricGraphError(f"{name}: metric phụ thuộc chính nó")
        unknown = [parent for parent in spec.source_metrics if parent not in specs]
        if unknown:
            raise MetricGraphError(f"{name}: source metric không tồn tại: {unknown}")
        overlap = set(spec.source_columns) & set(spec.source_metrics)
        if overlap:
            raise MetricGraphError(f"{name}: token vừa là column vừa là metric: {sorted(overlap)}")
        # Lineage phải kết thúc ở một cột thật hoặc ở một tool đã khai; metric
        # không có cả hai là metric không truy được nguồn.
        if not spec.source_columns and not spec.source_metrics and "tool_computed" not in spec.tags:
            raise MetricGraphError(f"{name}: không có lineage tới column hoặc tool")
        for constraint in spec.definition_constraints:
            if not constraint.decision_id:
                raise MetricGraphError(
                    f"{name}: constraint {constraint.constraint_id} thiếu decision_id"
                )
        for parent in spec.source_metrics:
            consumers[parent].append(name)

    cycles = _find_cycles(specs)
    if cycles:
        raise MetricGraphError(f"Metric graph có cycle: {cycles}")
    return MetricGraph(
        specs=dict(specs),
        consumers={name: tuple(sorted(value)) for name, value in consumers.items()},
    )


def _check_legacy_tokens(graph: MetricGraph) -> None:
    """Mọi token ``depends_on`` cũ phải được lineage mới phủ.

    ``depends_on`` được giữ nguyên byte-for-byte một release và trở thành legacy
    không authoritative. Nó không cần đủ mọi cạnh, nhưng nếu nó nhắc một thứ mà
    lineage mới không với tới thì một trong hai đang sai.
    """
    for name, spec in graph.specs.items():
        reachable_metrics = set(graph.ancestors(name))
        reachable_columns = set(spec.source_columns)
        for parent in reachable_metrics:
            reachable_columns |= set(graph.specs[parent].source_columns)
        unclassified = [
            token for token in spec.depends_on
            if token not in reachable_columns and token not in reachable_metrics
        ]
        if unclassified:
            raise MetricGraphError(
                f"{name}: legacy depends_on không được lineage phủ: {unclassified}"
            )


def _build_registry(specs: list[MetricSpec]) -> dict[str, MetricSpec]:
    registry: dict[str, MetricSpec] = {}
    for spec in specs:
        if spec.name in registry:
            raise ValueError(f"Metric trùng tên: {spec.name}")
        if not spec.name or not spec.unit or not spec.formula or not spec.caveats:
            raise ValueError(f"MetricSpec thiếu contract bắt buộc: {spec.name!r}")
        if not spec.owner:
            raise ValueError(f"MetricSpec thiếu owner: {spec.name}")
        registry[spec.name] = spec
    for spec in registry.values():
        _check_share_definition(spec, registry)
    return registry


def _check_share_definition(spec: MetricSpec, registry: dict[str, MetricSpec]) -> None:
    """Bất biến của một tỷ lệ đã khai — nổ lúc import, không lúc chạy.

    CHỆCH KHỎI SPEC CÓ CHỦ ĐÍCH: spec §12.3 đòi iff hai chiều (`share is not
    None` ⟺ `"share" in valid_aggregations`). Chiều "share trong
    valid_aggregations ⇒ phải có ShareDefinition" tự phản trên registry thật:
    ``has_structured_voucher`` và ``discount_bucket`` đã chứng nhận ``share``
    theo nghĩa AVG-trên-bool/bucket từ trước W11 và đang chạy đúng; ép chúng
    khai ShareDefinition là đổi hợp đồng của metric không có lỗi đo được nào.
    Giữ chiều còn lại — mọi ShareDefinition mới đều bị kiểm đủ.
    """
    share = spec.share
    if share is None:
        return
    if "share" not in spec.valid_aggregations:
        raise ValueError(f"{spec.name}: có ShareDefinition thì phải chứng nhận 'share'")
    numerator = registry.get(share.numerator_metric)
    denominator = registry.get(share.denominator_metric)
    if numerator is None or denominator is None:
        raise ValueError(f"{spec.name}: tử/mẫu không tồn tại trong registry")
    if "count" not in denominator.valid_aggregations and share.denominator_metric != "product_count":
        raise ValueError(f"{spec.name}: mẫu số phải là một count metric")
    if numerator.grain != spec.grain or numerator.dedupe != spec.dedupe:
        raise ValueError(f"{spec.name}: tử số khác grain/dedupe với tỷ lệ")
    expected_scale = 100 if spec.unit == "percent" else 1
    if share.scale != expected_scale:
        raise ValueError(f"{spec.name}: scale {share.scale} không khớp unit {spec.unit}")


METRICS: dict[str, MetricSpec] = _build_registry(_METRIC_SPECS)
METRIC_GRAPH: MetricGraph = build_metric_graph(METRICS)
_check_legacy_tokens(METRIC_GRAPH)


def get(name: str) -> MetricSpec | None:
    return METRICS.get(name)


def names() -> tuple[str, ...]:
    return tuple(METRICS)


def impact_of(metric: str) -> MetricImpact:
    return METRIC_GRAPH.impact_of(metric)


def effective_caveats(metric: str) -> tuple[tuple[str, str], ...]:
    return METRIC_GRAPH.effective_caveats(metric)


# --- Lớp giá trị (W14.1, SolutionSpec2808 §15.5) ---------------------------
#
# Một hằng số `PRICE_SENTINEL` trong source bảo vệ ĐÚNG MỘT measure, tám measure
# còn lại không được bảo vệ, và không ai thấy sự chênh đó vì nó là một câu `if`
# chứ không phải một hàng trong bảng. Registry này biến nó thành bảng.
VALUE_CLASS_RULES: tuple[ValueClassRule, ...] = (
    # Hằng số đang chạy, di trú NGUYÊN VĂN. decision_id ghi đúng xuất xứ của nó
    # — một literal trong source, không phải một quyết định có chữ ký. Ghi như
    # vậy để lần review đầu tiên nhìn thấy sự thật đó.
    ValueClassRule("price-sentinel-legacy", "measure.price", "equals",
                   "placeholder", values=(999_999_999,),
                   decision_id="legacy-source-literal"),
    # PHÁT HIỆN, CHƯA DUYỆT: decision_id=None ⇒ KHÔNG loại dòng nào, chỉ chặn
    # câu trả lời mà giá trị biên rơi vào đây (§15.7).
    ValueClassRule("price-repdigit-nine", "measure.price", "repdigit_nine",
                   "placeholder", min_digits=7, decision_id=None),
    ValueClassRule("price-original-repdigit-nine", "measure.price_original",
                   "repdigit_nine", "placeholder", min_digits=7, decision_id=None),
    ValueClassRule("rating-no-observation", "measure.rating", "companion_is_zero",
                   "no_observation", companion_ref="measure.rating_count",
                   decision_id=None),
)


def _check_value_class_rules(rules: tuple[ValueClassRule, ...]) -> None:
    """Kiểm phần KHÔNG cần catalog. Phần cần catalog kiểm ở ``catalog.py`` ngay
    sau khi ``CATALOG`` dựng xong — catalog import module này, nên kiểm ref ở
    đây là một vòng import, và một kiểm chạy muộn hơn import là một kiểm không
    tồn tại với người vừa gõ sai một ref."""
    seen: set[str] = set()
    for rule in rules:
        if rule.rule_id in seen:
            raise ValueClassError(f"rule_id trùng: {rule.rule_id}")
        seen.add(rule.rule_id)
        if rule.kind == "repdigit_nine" and (rule.min_digits or 0) < 3:
            raise ValueClassError(f"{rule.rule_id}: repdigit_nine cần min_digits >= 3")
        if rule.kind == "equals" and not rule.values:
            raise ValueClassError(f"{rule.rule_id}: equals cần values không rỗng")
        if rule.kind == "companion_is_zero" and rule.companion_ref is None:
            raise ValueClassError(f"{rule.rule_id}: companion_is_zero cần companion_ref")


def matches_value_class(rule: ValueClassRule, value: object,
                        companion: object | None = None) -> bool:
    """Giá trị này có rơi vào luật không. Không đọc tiêu đề, không đoán nghiệp vụ."""
    if rule.kind == "companion_is_zero":
        try:
            return float(companion) == 0.0 if companion is not None else False
        except (TypeError, ValueError):
            return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    if rule.kind == "equals":
        return any(number == float(item) for item in rule.values)
    # repdigit_nine: nguyên dương, mọi chữ số đều là 9, đủ số chữ số.
    if number <= 0 or number != int(number):
        return False
    digits = str(int(number))
    return len(digits) >= (rule.min_digits or 0) and set(digits) == {"9"}


def value_class_rules_for(ref: str) -> tuple[ValueClassRule, ...]:
    return tuple(rule for rule in VALUE_CLASS_RULES if rule.ref == ref)


def approved_exclusion_predicates(ref: str) -> tuple[tuple[str, str, object], ...]:
    """``(ref, op, value)`` cho những luật ĐÃ DUYỆT của một measure.

    Chỉ luật có ``decision_id`` mới thành predicate. Với registry khởi tạo, hàm
    trả đúng ``price < 999999999`` cho ``measure.price`` và RỖNG cho mọi ref
    khác — tức không measure nào đổi hành vi vì bản thân thay đổi này.

    Trả tuple thuần thay vì ``Predicate`` để ``domain`` không phụ thuộc
    ``planner``; call site dựng object của tầng nó.
    """
    predicates: list[tuple[str, str, object]] = []
    for rule in VALUE_CLASS_RULES:
        if rule.ref != ref or rule.decision_id is None:
            continue
        if rule.kind == "equals":
            for value in rule.values:
                predicates.append((ref, "lt", value))
    return tuple(predicates)


_check_value_class_rules(VALUE_CLASS_RULES)
