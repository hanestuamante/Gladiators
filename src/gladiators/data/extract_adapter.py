"""Đưa dump Postgres (``raw_extra_data``) về layout raw canonical.

Vì sao là ADAPTER chứ không phải một pipeline thứ hai: ``pipeline.py`` đã mang
toàn bộ luật làm sạch, kiểm quan hệ, cờ chất lượng và cách dựng metric. Viết
một đường thứ hai cho bộ dữ liệu mới là tạo hai định nghĩa cho cùng một khái
niệm, và chúng sẽ trôi khỏi nhau đúng lúc không ai nhìn. Adapter chỉ đổi HÌNH
DẠNG; mọi phép làm sạch vẫn đi qua một đường duy nhất.

──────────────────────────────────────────────────────────────────────────────
BỐN SỰ THẬT ĐO ĐƯỢC quyết định cách nối (đo trên chính bộ dump, 30/08/2026)
──────────────────────────────────────────────────────────────────────────────

1. **``product_promotions`` LÀ panel ngày, và nó tái lập bộ đóng băng.**
   22 695 dòng = item × ngày, 20 ngày (01→21/07). Trên ba ngày chồng lấn nó cho
   ĐÚNG số listing của ``products_clean`` (581/670/668 vn · 474 id) và 668/668
   giá khớp tới từng đồng. Đây là bằng chứng mạnh nhất có thể có rằng nó chính
   là nguồn mà bộ đóng băng được dựng từ đó ⇒ nó làm XƯƠNG SỐNG của panel.

2. **``products`` và ``products_timeseries`` KHÔNG phải panel** — 1 276 dòng /
   1 276 item, đúng MỘT dòng mỗi item, và ``date`` của chúng bằng ngày CUỐI của
   item đó trong ``product_promotions`` (1276/1276). Tên bảng
   "products_timeseries" mô tả sai chính nó; nối theo tên file là nối sai.

3. **Vì (2), các cột trạng thái chỉ có MỘT quan sát mỗi item.** Trong bộ đóng
   băng, ``rating`` / ``rating_count`` / ``liked_count`` / ``monthly_sold`` /
   ``history_sold`` ĐỔI theo ngày (202–411 trên 671 listing). Bộ mới không có
   thông tin đó cho 19 ngày còn lại. Gắn một quan sát cho cả 20 ngày sẽ dựng ra
   một chuỗi thời gian PHẲNG không có thật — "không đo được" đội lốt "đo được
   và không đổi" (CLAUDE.md §3.1). Vì vậy chúng chỉ được ghi tại ĐÚNG ngày quan
   sát của item, các ngày khác để TRỐNG, kèm cờ ``attributes_observed``.

4. **``shopee_verified`` đổi GRAIN.** Bộ cũ có cờ ở cấp LISTING (576 listing vn
   / 9 id). Bộ mới chỉ có ``shop_info.is_shopee_verified`` ở cấp SHOP (3/20
   shop). Hai đại lượng khác nhau mang một cái tên; ánh xạ cái này thành cái kia
   là bịa. Cột listing-level để TRỐNG; cờ shop-level đi vào ``shop_info`` như
   một cột riêng.

Hai chỗ phải mượn từ bộ tham chiếu, và chúng được ghi rõ là mượn:

* **``brand``** — dump chỉ có ``brand_id``. Bản đồ ``(country, brand_id) → tên``
  lấy từ bộ đóng băng (43 cặp, không cặp nào trỏ hai tên) phủ 1 225/1 276 item;
  41 item còn lại có ``brand_id`` rỗng/0 (thật sự không có brand) và 10 item
  mang ``brand_id`` chưa từng thấy ⇒ để TRỐNG, không đoán.
* **``category_platform``** — taxonomy CẤP SÀN (4 482 dòng, 2 241 mỗi thị
  trường), không phụ thuộc shop hay ngày, và dump không có bảng tương ứng. Chép
  nguyên từ bộ tham chiếu kèm cờ xuất xứ.

``unit_sold`` (0 ở toàn bộ 1 276 dòng) KHÔNG được phát ra: một cột hằng số đi
vào panel là một chỉ số "đo được và bằng 0" trong khi sự thật là không đo được.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

# Bảng của dump → tiền tố tên file (dump đặt tên ``<bảng>_<YYYYMMDDHHMM>.csv``).
EXTRACT_TABLES = (
    "products", "products_timeseries", "product_promotions",
    "product_categories", "categories", "shop_info", "shop_stats",
)

# Cột TRẠNG THÁI: chỉ có một quan sát mỗi item (sự thật #3). Chúng chỉ được ghi
# tại ngày quan sát của item; các ngày khác để trống.
POINT_IN_TIME_COLUMNS = (
    "rating", "rating_count", "rating_count_detail",
    "liked_count", "history_sold", "monthly_sold", "discount_percent",
)

# Cột ĐỊNH DANH: thuộc tính của chính listing, không phải một phép đo theo ngày
# (tên, ảnh, url, phân loại). Gắn cho mọi ngày là đúng.
IDENTITY_COLUMNS = (
    "product_name", "url", "image_url", "images", "seller_flag", "image_overlay",
    "is_ad", "is_sold_out", "ctime", "vouchers", "brand_id",
    "tier_variation_name", "tier_variation_options", "location",
    # Ngành hàng: hai cột này PHẢI có mặt ở đây, nếu không hai nhánh ánh xạ bên
    # dưới im lặng rơi vào else và ``catid``/``global_catids`` ra rỗng — mất dữ
    # liệu mà pipeline vẫn xanh, vì cột trống là hợp lệ về kiểu.
    "shopee_category_id", "global_category_id",
)

# Cột đến TỪ panel promotions — theo ngày, không mượn của ai.
PANEL_COLUMNS = (
    "price", "price_original", "price_before_promo", "promotion_id",
    "promotion_type", "voucher_code", "voucher_discount",
    "voucher_start_time", "voucher_end_time", "voucher_min_spend",
)

# Cột canonical mà dump KHÔNG cấp được, và vì sao. Ghi ở đây thay vì để chúng
# lặng lẽ rỗng — một cột trống không có lời giải thích là một cột không ai biết
# nên chờ dữ liệu hay chờ code.
UNAVAILABLE_COLUMNS = {
    "shopee_verified": "grain đổi: dump chỉ có cờ cấp SHOP, bộ cũ đo cấp LISTING",
    "seller_flag_hash": "ID ảnh CDN của Shopee, không suy được từ seller_flag",
    "image_overlay_hash": "ID ảnh CDN của Shopee, không suy được từ image_overlay",
    "key": "cột endpoint nội bộ của lần thu cũ; dump không mang",
}


class ExtractAdapterError(ValueError):
    """Dump không đúng hình dạng đã khảo sát — dừng, không đoán."""


@dataclass
class AdaptReport:
    """Ghi lại ĐỦ để người đọc tái lập từng quyết định của lần nối này."""

    source: str
    rows_by_dataset: dict[str, int] = field(default_factory=dict)
    dates: dict[str, list[str]] = field(default_factory=dict)
    brand_mapped: int = 0
    brand_unmapped: int = 0
    brand_absent_id: int = 0
    attributes_observed_rows: int = 0
    panel_rows: int = 0
    borrowed: dict[str, str] = field(default_factory=dict)
    unavailable: dict[str, str] = field(default_factory=lambda: dict(UNAVAILABLE_COLUMNS))
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "extract-adapt-report.v1",
            "source": self.source,
            "rows_by_dataset": self.rows_by_dataset,
            "dates": self.dates,
            "panel_rows": self.panel_rows,
            "attributes_observed_rows": self.attributes_observed_rows,
            "brand": {
                "mapped": self.brand_mapped, "unmapped": self.brand_unmapped,
                "absent_brand_id": self.brand_absent_id,
            },
            "borrowed_from_reference": self.borrowed,
            "unavailable_columns": self.unavailable,
            "notes": self.notes,
        }


def _load(source: Path, table: str) -> pd.DataFrame:
    # Hậu tố PHẢI là dấu thời gian thuần số: glob "products_*" bắt luôn
    # "products_timeseries_*", và hai bảng đó có hình dạng khác hẳn nhau — nhận
    # nhầm một cái là nối sai toàn bộ panel.
    matches = sorted(
        path for path in source.glob(f"{table}_*.csv")
        if path.stem[len(table) + 1:].isdigit()
    )
    if not matches:
        raise ExtractAdapterError(f"dump thiếu bảng {table}")
    if len(matches) > 1:
        raise ExtractAdapterError(
            f"{table}: {len(matches)} file cùng tiền tố — không đoán bản nào là bản đúng",
        )
    frame = pd.read_csv(matches[0], dtype=str, keep_default_na=False, encoding="utf-8-sig")
    # ``created_at``/``updated_at`` là dấu thời gian NẠP batch (một giá trị duy
    # nhất cho cả bảng), không phải sự kiện kinh doanh. Để chúng vào panel là
    # đưa một cột hằng số vào chỗ người đọc chờ một phép đo.
    return frame.drop(columns=[c for c in ("created_at", "updated_at") if c in frame])


def _assert_grain(frame: pd.DataFrame, keys: list[str], table: str, *, unique: bool) -> None:
    counts = frame.groupby(keys).size()
    if unique and int(counts.max()) != 1:
        raise ExtractAdapterError(
            f"{table}: khoá {keys} không duy nhất (max {counts.max()} dòng/khoá) — "
            "hình dạng khác lần khảo sát, dừng thay vì nối bừa",
        )


# Dump ghi thời gian dạng ``2025-11-11 02:24:55.000 +0700``; bộ cũ ghi ``ctime``
# và hai mốc voucher bằng GIÂY EPOCH (pipeline khai chúng là NUMERIC_COLUMNS).
# Không đổi đơn vị ở đây thì mỗi dòng sinh một ``INVALID_NUMBER`` và cột số ra
# null — mất dữ liệu mà pipeline vẫn chạy.
EPOCH_COLUMNS = ("ctime", "voucher_start_time", "voucher_end_time")

# Thời điểm ghi dưới dạng CHỮ trong bộ cũ (ISO UTC), không phải số.
ISO_COLUMNS = ("created_at", "last_active_time")


def _to_epoch(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values.replace("", pd.NA), errors="coerce", utc=True, format="mixed")
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    seconds = ((parsed - epoch) // pd.Timedelta(seconds=1)).astype("Int64").mask(parsed.isna())
    # Ô trống phải ra chuỗi RỖNG: "nan" lọt vào CSV sẽ được pipeline chấm là
    # INVALID_NUMBER, tức "có giá trị nhưng hỏng" thay vì "không có giá trị".
    return seconds.astype("string").fillna("")


def _to_iso(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values.replace("", pd.NA), errors="coerce", utc=True, format="mixed")
    return parsed.dt.strftime("%Y-%m-%dT%H:%M:%S+00:00").fillna("")


def _brand_map(reference_products: Path) -> dict[tuple[str, str], str]:
    """``(country, brand_id) → tên brand`` từ bộ tham chiếu.

    Kiểm 1-1 tại chỗ: một ``brand_id`` trỏ hai tên nghĩa là giả định nền của
    phép mượn này sai, và khi đó không được mượn.
    """
    frame = pd.read_csv(reference_products, low_memory=False)
    frame = frame[frame.brand.notna() & frame.brand_id_num.notna()]
    frame = frame.assign(brand_id=frame.brand_id_num.astype("Int64").astype(str))
    per_id = frame.groupby(["country_code", "brand_id"]).brand.nunique()
    ambiguous = per_id[per_id > 1]
    if len(ambiguous):
        raise ExtractAdapterError(
            f"brand_id trỏ nhiều tên trong bộ tham chiếu: {list(ambiguous.index)[:5]} — "
            "phép mượn tên brand không còn hợp lệ",
        )
    pairs = frame.drop_duplicates(["country_code", "brand_id"])
    return {
        (row.country_code, row.brand_id): row.brand for row in pairs.itertuples()
    }


def _write_partition(out: Path, country: str, dataset: str, frame: pd.DataFrame,
                     shop_id: str | None = None) -> None:
    parts = [out, f"country_code={country}", f"dataset={dataset}"]
    if shop_id is not None:
        parts.append(f"shop_id={shop_id}")
    directory = Path(*parts)
    directory.mkdir(parents=True, exist_ok=True)
    frame.to_csv(directory / f"{dataset}.csv", index=False, encoding="utf-8")


def adapt_extract(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    reference_dir: str | Path = "data/processed",
) -> AdaptReport:
    """Sinh layout raw canonical từ dump, trả về báo cáo của lần nối.

    ``reference_dir`` chỉ dùng cho hai phép MƯỢN đã nêu ở docstring module
    (tên brand, taxonomy sàn) — không dùng để lấp bất kỳ số liệu nào.
    """
    source, out = Path(source_dir), Path(output_dir)
    reference = Path(reference_dir)
    report = AdaptReport(source=str(source))

    products = _load(source, "products")
    promotions = _load(source, "product_promotions")
    shop_info = _load(source, "shop_info")
    shop_stats = _load(source, "shop_stats")
    categories = _load(source, "categories")
    product_categories = _load(source, "product_categories")

    # Hình dạng phải khớp lần khảo sát; lệch ⇒ dừng (sự thật #1, #2).
    _assert_grain(products, ["country_code", "shop_id", "item_id"], "products", unique=True)
    _assert_grain(promotions, ["country_code", "shop_id", "item_id", "date"],
                  "product_promotions", unique=True)
    _assert_grain(shop_stats, ["country_code", "shop_id", "date"], "shop_stats", unique=True)
    _assert_grain(shop_info, ["country_code", "shop_id"], "shop_info", unique=True)

    last_seen = promotions.groupby(["country_code", "item_id"]).date.max()
    stated = products.set_index(["country_code", "item_id"]).date
    if not stated.reindex(last_seen.index).eq(last_seen).all():
        raise ExtractAdapterError(
            "products.date không còn bằng ngày cuối của item trong product_promotions "
            "— giả định 'products là ảnh chụp tại ngày cuối' đã sai",
        )

    # ── products: panel = promotions, thuộc tính gắn ĐÚNG chỗ ────────────────
    brand_lookup = _brand_map(reference / "products_clean.csv")
    report.borrowed["brand"] = (
        f"{reference}/products_clean.csv — bản đồ (country, brand_id) → tên, "
        f"{len(brand_lookup)} cặp"
    )

    identity = products[
        ["country_code", "shop_id", "item_id", "date", *IDENTITY_COLUMNS, *POINT_IN_TIME_COLUMNS]
    ].rename(columns={"date": "observed_date"})
    panel = promotions.merge(
        identity, on=["country_code", "shop_id", "item_id"], how="left",
        suffixes=("", "_static"),
    )
    report.panel_rows = len(panel)

    # Sự thật #3: cột trạng thái CHỈ sống ở ngày quan sát của chính item.
    observed = panel.date.eq(panel.observed_date)
    report.attributes_observed_rows = int(observed.sum())
    for column in POINT_IN_TIME_COLUMNS:
        if column in panel.columns:
            panel[column] = panel[column].where(observed, "")
    panel["attributes_observed"] = observed.map({True: "true", False: "false"})

    # Panel giữ giá của promotions; bản tĩnh cùng tên bị bỏ.
    for column in PANEL_COLUMNS:
        static_twin = f"{column}_static"
        if static_twin in panel.columns:
            panel = panel.drop(columns=[static_twin])

    brand_ids = pd.to_numeric(panel.brand_id, errors="coerce").astype("Int64").astype(str)
    panel["brand"] = [
        brand_lookup.get((country, bid), "")
        for country, bid in zip(panel.country_code, brand_ids)
    ]
    has_id = brand_ids.ne("<NA>") & brand_ids.ne("0") & panel.brand_id.ne("")
    per_item = panel.drop_duplicates(["country_code", "item_id"])
    per_item_ids = pd.to_numeric(per_item.brand_id, errors="coerce").astype("Int64").astype(str)
    per_item_has_id = per_item_ids.ne("<NA>") & per_item_ids.ne("0") & per_item.brand_id.ne("")
    report.brand_mapped = int((per_item.brand != "").sum())
    report.brand_unmapped = int((per_item_has_id & per_item.brand.eq("")).sum())
    report.brand_absent_id = int((~per_item_has_id).sum())

    shop_names = shop_info.set_index(["country_code", "shop_id"])
    panel["shop_name"] = [
        shop_names.shop_name.get((c, s), "")
        for c, s in zip(panel.country_code, panel.shop_id)
    ]
    panel["shop_slug"] = ""          # dump không mang username ở bảng shop_info
    panel["platform"] = "Shopee"
    # ``shopee_category_id`` ≡ ``catid`` (1 157/1 157 item chồng lấn khớp) và
    # ``global_category_id`` ĐÃ LÀ chuỗi mảng đường dẫn ngành hàng, giống hệt
    # ``global_catids`` cũ (1 155/1 157). Chép nguyên văn — bọc thêm một lớp
    # ngoặc sẽ dựng ra mảng lồng và làm hỏng array-parser của pipeline.
    # Hai item lệch (vn 25586402460, 26912249516) mang đường dẫn KHÁC hẳn: sàn
    # đổi ngành hàng của chúng sau lần thu cũ. Đó là dữ liệu mới, không phải lỗi
    # ánh xạ ⇒ lấy theo dump.
    panel["catid"] = panel.pop("shopee_category_id")
    panel["global_catids"] = panel.pop("global_category_id")
    panel = panel.rename(columns={
        "history_sold": "history_sold_value", "monthly_sold": "monthly_sold_value",
    })
    for column in EPOCH_COLUMNS:
        if column in panel.columns:
            panel[column] = _to_epoch(panel[column])
    report.notes.append(
        "ctime/voucher_start_time/voucher_end_time đổi sang giây epoch — bộ cũ "
        "dùng epoch và pipeline khai chúng là cột số",
    )
    for column, reason in UNAVAILABLE_COLUMNS.items():
        panel[column] = ""
        report.notes.append(f"products.{column} để trống — {reason}")
    panel = panel.drop(columns=["observed_date"])

    # ── shop: TÁCH GRAIN, không đổi grain ────────────────────────────────────
    #
    # Bộ cũ có ``shop_info`` grain (country, shop) với ĐÚNG một ngày (03/07), và
    # 9 measure trong catalog trỏ thẳng vào ``shop_info_clean.csv.*_num`` với
    # ngữ nghĩa ``static_latest``. Dump cho 20 ngày. Nếu để panel chảy vào
    # ``shop_info`` thì mọi join theo shop nở gấp 20 lần và chín measure đó âm
    # thầm đổi nghĩa — "một grain bị chọn ngầm là một câu hỏi khác bị trả lời
    # ngầm" (CLAUDE.md §3.1). Nên: ``shop_info`` giữ NGUYÊN hình dạng cũ (ảnh
    # chụp tại ngày cuối), còn panel ngày đi ra một dataset MỚI ``shop_stats``.
    shop_identity = shop_info.copy()
    for column in ISO_COLUMNS:
        if column in shop_identity.columns:
            shop_identity[column] = _to_iso(shop_identity[column])
    # ``shop_created_at`` của dump chính là ``created_at`` của bộ cũ (cùng thời
    # điểm, khác múi giờ hiển thị) — giữ tên cũ để schema không gãy.
    if "shop_created_at" in shop_identity.columns:
        shop_identity["created_at"] = _to_iso(shop_identity.pop("shop_created_at"))

    panel_dates = sorted(shop_stats.date.unique())
    latest_stats = shop_stats[shop_stats.date.eq(panel_dates[-1])]
    shops = latest_stats.merge(shop_identity, on=["country_code", "shop_id"], how="left")
    shops["username"] = ""          # dump không mang username của shop
    report.notes.append(
        f"shop_info = ảnh chụp TĨNH tại {panel_dates[-1]} (giữ đúng grain cũ "
        "(country, shop) để 9 measure static_latest không đổi nghĩa); panel 20 "
        "ngày đi ra dataset MỚI shop_stats",
    )

    shop_daily = shop_stats.merge(
        shop_identity[[c for c in ("country_code", "shop_id", "shop_name",
                                   "is_official_shop", "is_shopee_verified",
                                   "is_preferred_plus_seller")
                       if c in shop_identity.columns]],
        on=["country_code", "shop_id"], how="left",
    )

    # ``category_slug`` trong bộ cũ mang ĐÚNG giá trị ``category_id`` (4 054/
    # 4 054) và pipeline khai nó là cột SỐ. Dump dùng cùng tên cho một slug CHỮ
    # ("calming-agent") — cùng tên, khác nghĩa. Giữ nghĩa cũ cho tên cũ, slug
    # chữ ra cột mới: đổi nghĩa một cột đang có là đổi câu trả lời của mọi câu
    # hỏi đã dựa vào nó.
    product_categories = product_categories.rename(
        columns={"category_slug": "category_slug_text"},
    )
    product_categories["category_slug"] = product_categories.category_id
    report.notes.append(
        "product_categories.category_slug giữ nghĩa cũ (= category_id, cột số); "
        "slug chữ của dump ra cột mới category_slug_text",
    )

    # ── category_list ← categories (dump không mang ngày ⇒ khai ngày quan sát) ─
    shelf = categories.rename(columns={
        "category_id": "shop_category_id",
        "parent_category_id": "parent_shop_category_id",
    })
    observation_dates = sorted(promotions.date.unique())
    shelf["date"] = observation_dates[-1]
    report.notes.append(
        "category_list.date = ngày cuối của panel: dump categories không mang ngày, "
        "và gán nó cho mọi ngày sẽ dựng ra một lịch sử kệ hàng không có thật",
    )

    # ── ghi phân vùng ────────────────────────────────────────────────────────
    for country, country_panel in panel.groupby("country_code"):
        for shop_id, one in country_panel.groupby("shop_id"):
            _write_partition(out, country, "products", one, shop_id)
    for country, country_shops in shops.groupby("country_code"):
        for shop_id, one in country_shops.groupby("shop_id"):
            _write_partition(out, country, "shop_info", one, shop_id)
    for country, country_stats in shop_daily.groupby("country_code"):
        for shop_id, one in country_stats.groupby("shop_id"):
            _write_partition(out, country, "shop_stats", one, shop_id)
    for country, country_shelf in shelf.groupby("country_code"):
        for shop_id, one in country_shelf.groupby("shop_id"):
            _write_partition(out, country, "category_list", one, shop_id)
    for country, country_pc in product_categories.groupby("country_code"):
        for shop_id, one in country_pc.groupby("shop_id"):
            _write_partition(out, country, "product_categories", one, shop_id)

    # category_platform: taxonomy cấp sàn, dump không có ⇒ mượn có ghi chú.
    taxonomy = pd.read_csv(reference / "category_platform_clean.csv", low_memory=False)
    keep = [c for c in taxonomy.columns
            if not c.startswith(("path_", "source_")) and not c.endswith("_num")]
    for country, one in taxonomy[keep].groupby("country_code"):
        _write_partition(out, country, "category_platform",
                         one.drop(columns=["country_code"]))
    report.borrowed["category_platform"] = (
        f"{reference}/category_platform_clean.csv — taxonomy cấp sàn, "
        "không phụ thuộc shop/ngày; dump không mang bảng tương ứng"
    )

    report.rows_by_dataset = {
        "products": len(panel), "shop_info": len(shops), "shop_stats": len(shop_daily),
        "category_list": len(shelf), "product_categories": len(product_categories),
        "category_platform": len(taxonomy),
    }
    report.dates = {
        "panel": [observation_dates[0], observation_dates[-1]],
        "shop_stats": sorted(shop_stats.date.unique())[:1] + sorted(shop_stats.date.unique())[-1:],
    }
    report.notes.append(
        "products_timeseries KHÔNG được dùng: 1 dòng/item như products, và cột "
        "unit_sold bằng 0 ở toàn bộ dòng (hằng số ⇒ không phải một phép đo)",
    )
    (out / "ADAPT_REPORT.json").write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report
