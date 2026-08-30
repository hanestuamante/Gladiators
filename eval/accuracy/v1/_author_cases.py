#!/usr/bin/env python3
"""Soạn 100 case cho benchmark accuracy v1 — Giai đoạn A (TC_formulation §4).

Chạy MỘT lần để sinh dev.json/holdout.json/manifest.json; giữ lại làm provenance.
Mọi con số đến từ ``oracle.py`` (thuần pandas); script này KHÔNG import
gladiators và không đọc suite kỳ vọng nào của repo.

Split dev/holdout theo hash của ``paraphrase_group`` — hai cách diễn đạt của
cùng một câu không bao giờ nằm hai bên ranh giới (leakage qua paraphrase).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import oracle  # noqa: E402  — oracle độc lập, không phải gladiators

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

D3 = "2026-07-03"
TABLES = oracle.Tables()

_counter = 0


def _nid() -> str:
    global _counter
    _counter += 1
    return f"acc-v1-{_counter:04d}"


def fact(metric, key, *, unit, country, value_type="integer", grain="listing",
         date_start=D3, date_end=None, group=None, filters=(), tol=("exact", 0)):
    return {
        "metric": metric, "oracle_fact_key": key, "value": None,
        "value_type": value_type, "unit": unit, "country": country,
        "date_start": date_start, "date_end": date_end or date_start,
        "grain": grain, "group": group, "filters": list(filters),
        "tolerance": {"kind": tol[0], "value": tol[1]},
    }


def case(question, *, answerability, action, category, language="vi",
         group_id, country=None, oracle_id=None, params=None, facts=(),
         entity_text=None, turns=None, slots=(), refusal_class=None,
         accepted_actions=None, forbidden_values=(), tags=()):
    filled = []
    if oracle_id:
        values = oracle.compute(oracle_id, params or {}, TABLES)
        for f in facts:
            f = dict(f)
            f["value"] = values[f["oracle_fact_key"]]
            filled.append(f)
    return {
        "id": _nid(), "split": None, "language": language,
        "category": category, "question": question, "turns": turns,
        "paraphrase_group": group_id, "entity_text": entity_text,
        "country": country,
        "answerability": answerability, "expected_action": action,
        "accepted_actions": accepted_actions or [action],
        "expected_clarification_slots": list(slots),
        "expected_refusal_reason_class": refusal_class,
        "expected_facts": filled,
        "forbidden_values": list(forbidden_values),
        "oracle": {
            "oracle_id": oracle_id, "params": params or {},
            "artifact_hash": oracle.ARTIFACT_SHA256["products_clean.csv"][:16],
            "reproduction_ref": "eval/accuracy/v1/oracle.py",
        } if oracle_id else None,
        "annotation_status": "pending_independent_review",
        "author_read_source_code_before_seal": True,  # nhiễm — khai thật, xem manifest
        "tags": list(tags),
    }


C: list[dict] = []
A = "directly_answerable"

# ─── ĐẾM CƠ BẢN ─────────────────────────────────────────────────────────────
lc = lambda c: fact("listing_count", "listing_count", unit="listings", country=c)
C += [
    case("Có bao nhiêu listing tại Việt Nam ngày 03/07?", answerability=A,
         action="allow", category="count", group_id="g_listing_vn", country="vn",
         oracle_id="listing_count", params={"country": "vn"}, facts=[lc("vn")]),
    case("Tổng số listing đang có mặt trên thị trường Việt Nam vào ngày 03/07 là bao nhiêu?",
         answerability=A, action="allow", category="count", group_id="g_listing_vn",
         country="vn", oracle_id="listing_count", params={"country": "vn"}, facts=[lc("vn")]),
    case("Berapa jumlah listing di Indonesia pada tanggal 03/07?", answerability=A,
         action="allow", category="count", language="id", group_id="g_listing_id",
         country="id", oracle_id="listing_count", params={"country": "id"}, facts=[lc("id")]),
    case("How many listings are there in Indonesia on 2026-07-03?", answerability=A,
         action="allow", category="count", language="en", group_id="g_listing_id",
         country="id", oracle_id="listing_count", params={"country": "id"}, facts=[lc("id")]),
    case("Có bao nhiêu shop ở Việt Nam?", answerability=A, action="allow",
         category="count", group_id="g_shop_vn", country="vn",
         oracle_id="shop_count", params={"country": "vn"},
         facts=[fact("shop_count", "shop_count", unit="shops", country="vn", grain="shop")]),
    case("co bao nhieu shop o viet nam?", answerability=A, action="allow",
         category="count", language="vi_no_diacritic", group_id="g_shop_vn",
         country="vn", oracle_id="shop_count", params={"country": "vn"},
         facts=[fact("shop_count", "shop_count", unit="shops", country="vn", grain="shop")]),
    case("Berapa banyak toko di Indonesia?", answerability=A, action="allow",
         category="count", language="id", group_id="g_shop_id", country="id",
         oracle_id="shop_count", params={"country": "id"},
         facts=[fact("shop_count", "shop_count", unit="shops", country="id", grain="shop")]),
    case("How many shops are there in Indonesia?", answerability=A, action="allow",
         category="count", language="en", group_id="g_shop_id", country="id",
         oracle_id="shop_count", params={"country": "id"},
         facts=[fact("shop_count", "shop_count", unit="shops", country="id", grain="shop")]),
    case("Có bao nhiêu thương hiệu khác nhau tại Việt Nam ngày 03/07?", answerability=A,
         action="allow", category="count", group_id="g_brandcount_vn", country="vn",
         oracle_id="brand_count", params={"country": "vn"},
         facts=[fact("brand_count", "brand_count", unit="brands", country="vn", grain="brand")]),
    case("Số thương hiệu phân biệt đang bán ở Việt Nam ngày 03/07 là bao nhiêu?",
         answerability=A, action="allow", category="count", group_id="g_brandcount_vn",
         country="vn", oracle_id="brand_count", params={"country": "vn"},
         facts=[fact("brand_count", "brand_count", unit="brands", country="vn", grain="brand")]),
    case("Indonesia ngày 03/07 có bao nhiêu thương hiệu khác nhau?", answerability=A,
         action="allow", category="count", group_id="g_brandcount_id", country="id",
         oracle_id="brand_count", params={"country": "id"},
         facts=[fact("brand_count", "brand_count", unit="brands", country="id", grain="brand")]),
    case("Có bao nhiêu listing tại Việt Nam ngày 01/07?", answerability=A,
         action="allow", category="count", group_id="g_date_0701_vn", country="vn",
         oracle_id="listing_count", params={"country": "vn", "date": "2026-07-01"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     date_start="2026-07-01")]),
]

# ─── ĐẾM CÓ LỌC ─────────────────────────────────────────────────────────────
C += [
    case("Có bao nhiêu listing của thương hiệu Bibica tại Việt Nam ngày 03/07?",
         answerability=A, action="allow", category="filter",
         group_id="g_bibica", country="vn", entity_text="Bibica",
         oracle_id="brand_listing_count", params={"country": "vn", "brand": "Bibica"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     filters=["brand=Bibica"])]),
    case("Bibica đang có bao nhiêu listing ở Việt Nam vào ngày 03/07?",
         answerability=A, action="allow", category="filter",
         group_id="g_bibica", country="vn", entity_text="Bibica",
         oracle_id="brand_listing_count", params={"country": "vn", "brand": "Bibica"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     filters=["brand=Bibica"])]),
    case("Thương hiệu ORION có bao nhiêu listing tại Việt Nam ngày 03/07?",
         answerability=A, action="allow", category="filter",
         group_id="g_orion_vn", country="vn", entity_text="ORION",
         oracle_id="brand_listing_count", params={"country": "vn", "brand": "ORION"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     filters=["brand=ORION"])]),
    case("Berapa banyak listing merek GLAD2GLOW di Indonesia pada 03/07?",
         answerability=A, action="allow", category="filter", language="id",
         group_id="g_glad2glow_brand", country="id", entity_text="GLAD2GLOW",
         oracle_id="brand_listing_count", params={"country": "id", "brand": "GLAD2GLOW"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="id",
                     filters=["brand=GLAD2GLOW"])]),
    case('Có bao nhiêu listing của shop "Richy - Chi nhánh Miền Nam" tại Việt Nam ngày 03/07?',
         answerability=A, action="allow", category="filter",
         group_id="g_richy_shop", country="vn", entity_text="Richy - Chi nhánh Miền Nam",
         oracle_id="shop_listing_count",
         params={"country": "vn", "shop_name": "Richy - Chi nhánh Miền Nam"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     filters=["shop=Richy - Chi nhánh Miền Nam"])]),
    case('Shop "Richy - Chi nhánh Miền Nam" bán bao nhiêu listing ở Việt Nam ngày 03/07?',
         answerability=A, action="allow", category="filter",
         group_id="g_richy_shop", country="vn", entity_text="Richy - Chi nhánh Miền Nam",
         oracle_id="shop_listing_count",
         params={"country": "vn", "shop_name": "Richy - Chi nhánh Miền Nam"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     filters=["shop=Richy - Chi nhánh Miền Nam"])]),
    case('Có bao nhiêu listing của shop "Glad2Glow Official Store" tại Indonesia ngày 03/07?',
         answerability=A, action="allow", category="filter",
         group_id="g_glad2glow_shop", country="id", entity_text="Glad2Glow Official Store",
         oracle_id="shop_listing_count",
         params={"country": "id", "shop_name": "Glad2Glow Official Store"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="id",
                     filters=["shop=Glad2Glow Official Store"])]),
    case("Có bao nhiêu listing đã xác minh tại Việt Nam ngày 03/07?", answerability=A,
         action="allow", category="filter", group_id="g_verified_vn", country="vn",
         oracle_id="verified_count", params={"country": "vn"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     filters=["shopee_verified=true"])]),
    case("co bao nhieu listing da xac minh tai viet nam ngay 03/07?", answerability=A,
         action="allow", category="filter", language="vi_no_diacritic",
         group_id="g_verified_vn", country="vn",
         oracle_id="verified_count", params={"country": "vn"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     filters=["shopee_verified=true"])]),
    case("Có bao nhiêu listing giảm giá trên 50% tại Việt Nam ngày 03/07?",
         answerability=A, action="allow", category="filter",
         group_id="g_disc50_vn", country="vn",
         oracle_id="discount_over", params={"country": "vn", "threshold": 50},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     filters=["discount_percent>50"])]),
    case("Indonesia ngày 03/07 có bao nhiêu listing giảm giá trên 50%?",
         answerability=A, action="allow", category="filter",
         group_id="g_disc50_id", country="id",
         oracle_id="discount_over", params={"country": "id", "threshold": 50},
         facts=[fact("listing_count", "listing_count", unit="listings", country="id",
                     filters=["discount_percent>50"])]),
]

# ─── TỔNG HỢP ───────────────────────────────────────────────────────────────
C += [
    case("Giá trung vị tại Việt Nam ngày 03/07 là bao nhiêu?", answerability=A,
         action="allow", category="aggregate", group_id="g_medprice_vn", country="vn",
         oracle_id="median_price", params={"country": "vn"},
         facts=[fact("median_price", "median_price", unit="VND", country="vn",
                     value_type="decimal", tol=("absolute", 0.5))]),
    case("Cho tôi mức giá trung vị của các listing Việt Nam ngày 03/07.",
         answerability=A, action="allow", category="aggregate",
         group_id="g_medprice_vn", country="vn",
         oracle_id="median_price", params={"country": "vn"},
         facts=[fact("median_price", "median_price", unit="VND", country="vn",
                     value_type="decimal", tol=("absolute", 0.5))]),
    case("Giá trung vị tại Indonesia ngày 03/07 là bao nhiêu?", answerability=A,
         action="allow", category="aggregate", group_id="g_medprice_id", country="id",
         oracle_id="median_price", params={"country": "id"},
         facts=[fact("median_price", "median_price", unit="IDR", country="id",
                     value_type="decimal", tol=("absolute", 0.5))]),
    case("gia trung vi tai indonesia ngay 03/07 la bao nhieu?", answerability=A,
         action="allow", category="aggregate", language="vi_no_diacritic",
         group_id="g_medprice_id", country="id",
         oracle_id="median_price", params={"country": "id"},
         facts=[fact("median_price", "median_price", unit="IDR", country="id",
                     value_type="decimal", tol=("absolute", 0.5))]),
    case("Điểm đánh giá trung vị tại Việt Nam ngày 03/07 là bao nhiêu?",
         answerability=A, action="allow", category="aggregate",
         group_id="g_medrating_vn", country="vn",
         oracle_id="median_rating", params={"country": "vn"},
         facts=[fact("median_rating", "median_rating", unit="stars", country="vn",
                     value_type="decimal", tol=("absolute", 0.005))]),
    case("Điểm đánh giá trung vị tại Indonesia ngày 03/07 là bao nhiêu?",
         answerability=A, action="allow", category="aggregate",
         group_id="g_medrating_id", country="id",
         oracle_id="median_rating", params={"country": "id"},
         facts=[fact("median_rating", "median_rating", unit="stars", country="id",
                     value_type="decimal", tol=("absolute", 0.005))]),
    case("Trung bình mỗi listing tại Việt Nam ngày 03/07 có bao nhiêu ảnh?",
         answerability=A, action="allow", category="aggregate",
         group_id="g_meanimg_vn", country="vn",
         oracle_id="mean_images", params={"country": "vn"},
         facts=[fact("mean_images", "mean_images", unit="images", country="vn",
                     value_type="decimal", tol=("absolute", 0.01))]),
    case("Tổng số lượt thích của tất cả listing Bibica tại Việt Nam ngày 03/07 là bao nhiêu?",
         answerability=A, action="allow", category="aggregate",
         group_id="g_sumlikes_bibica", country="vn", entity_text="Bibica",
         oracle_id="sum_brand_likes", params={"country": "vn", "brand": "Bibica"},
         facts=[fact("total_likes", "total_likes", unit="likes", country="vn",
                     filters=["brand=Bibica"])]),
]

# ─── XẾP HẠNG / CỰC TRỊ ─────────────────────────────────────────────────────
C += [
    case("Listing nào có giá cao nhất tại Việt Nam ngày 03/07?", answerability=A,
         action="allow", category="ranking", group_id="g_maxprice_vn", country="vn",
         oracle_id="max_price_listing", params={"country": "vn"},
         facts=[fact("max_price", "max_price", unit="VND", country="vn",
                     value_type="decimal", tol=("absolute", 0.5)),
                fact("product_name", "product_name", unit=None, country="vn",
                     value_type="string")]),
    case("Sản phẩm giá đắt nhất ở Việt Nam ngày 03/07 là gì?", answerability=A,
         action="allow", category="ranking", group_id="g_maxprice_vn", country="vn",
         oracle_id="max_price_listing", params={"country": "vn"},
         facts=[fact("max_price", "max_price", unit="VND", country="vn",
                     value_type="decimal", tol=("absolute", 0.5)),
                fact("product_name", "product_name", unit=None, country="vn",
                     value_type="string")]),
    case("Listing nào có nhiều lượt thích nhất tại Việt Nam ngày 03/07?",
         answerability=A, action="allow", category="ranking",
         group_id="g_maxlikes_vn", country="vn",
         oracle_id="top_liked_listing", params={"country": "vn"},
         facts=[fact("max_likes", "max_likes", unit="likes", country="vn",
                     value_type="decimal", tol=("absolute", 0.5))]),
    case("Which listing has the most likes in Indonesia on 03/07?", answerability=A,
         action="allow", category="ranking", language="en",
         group_id="g_maxlikes_id", country="id",
         oracle_id="top_liked_listing", params={"country": "id"},
         facts=[fact("max_likes", "max_likes", unit="likes", country="id",
                     value_type="decimal", tol=("absolute", 0.5))]),
    case("Listing nào có nhiều lượt đánh giá nhất tại Indonesia ngày 03/07?",
         answerability=A, action="allow", category="ranking",
         group_id="g_maxratingcount_id", country="id",
         oracle_id="top_rating_count_listing", params={"country": "id"},
         facts=[fact("max_rating_count", "max_rating_count", unit="ratings",
                     country="id", value_type="decimal", tol=("absolute", 0.5))]),
    case("Shop nào có nhiều listing nhất tại Việt Nam ngày 03/07?", answerability=A,
         action="allow", category="ranking", group_id="g_topshop_vn", country="vn",
         oracle_id="top_shop_by_listings", params={"country": "vn"},
         facts=[fact("shop_name", "shop_name", unit=None, country="vn",
                     value_type="string", grain="shop"),
                fact("listing_count", "listing_count", unit="listings", country="vn",
                     grain="shop")]),
    case("Cửa hàng dẫn đầu về số listing ở Việt Nam ngày 03/07 là cửa hàng nào?",
         answerability=A, action="allow", category="ranking",
         group_id="g_topshop_vn", country="vn",
         oracle_id="top_shop_by_listings", params={"country": "vn"},
         facts=[fact("shop_name", "shop_name", unit=None, country="vn",
                     value_type="string", grain="shop"),
                fact("listing_count", "listing_count", unit="listings", country="vn",
                     grain="shop")]),
    case("Toko mana yang punya listing terbanyak di Indonesia pada 03/07?",
         answerability=A, action="allow", category="ranking", language="id",
         group_id="g_topshop_id", country="id",
         oracle_id="top_shop_by_listings", params={"country": "id"},
         facts=[fact("shop_name", "shop_name", unit=None, country="id",
                     value_type="string", grain="shop"),
                fact("listing_count", "listing_count", unit="listings", country="id",
                     grain="shop")]),
    case("Thương hiệu nào có nhiều listing nhất tại Việt Nam ngày 03/07?",
         answerability=A, action="allow", category="ranking",
         group_id="g_topbrand_vn", country="vn",
         oracle_id="top_brand_by_listings", params={"country": "vn"},
         facts=[fact("brand", "brand", unit=None, country="vn", value_type="string",
                     grain="brand"),
                fact("listing_count", "listing_count", unit="listings", country="vn",
                     grain="brand")]),
    case("Thương hiệu nào có nhiều listing nhất tại Indonesia ngày 03/07?",
         answerability=A, action="allow", category="ranking",
         group_id="g_topbrand_id", country="id",
         oracle_id="top_brand_by_listings", params={"country": "id"},
         facts=[fact("brand", "brand", unit=None, country="id", value_type="string",
                     grain="brand"),
                fact("listing_count", "listing_count", unit="listings", country="id",
                     grain="brand")]),
    case("Giá thấp nhất tại Việt Nam ngày 03/07 là bao nhiêu?", answerability=A,
         action="allow", category="ranking", group_id="g_minprice_vn", country="vn",
         oracle_id="min_price", params={"country": "vn"},
         facts=[fact("min_price", "min_price", unit="VND", country="vn",
                     value_type="decimal", tol=("absolute", 0.5))]),
    # Hoà THẬT ở đỉnh: 76 (VN) / 64 (ID) listing cùng đạt số ảnh tối đa. Trả một
    # cái tên duy nhất là SAI; chấp nhận allow-nêu-hoà hoặc từ chối vì hoà.
    case("Listing nào có nhiều ảnh nhất tại Việt Nam ngày 03/07?", answerability=A,
         action="allow", category="ranking_tie", group_id="g_imagetie_vn",
         country="vn", oracle_id="max_images_tie", params={"country": "vn"},
         accepted_actions=["allow", "clarify", "abstain"],
         facts=[fact("max_images", "max_images", unit="images", country="vn"),
                fact("tie_count", "tie_count", unit="listings", country="vn")],
         tags=["tie"]),
    case("Listing nào có nhiều ảnh nhất tại Indonesia ngày 03/07?", answerability=A,
         action="allow", category="ranking_tie", group_id="g_imagetie_id",
         country="id", oracle_id="max_images_tie", params={"country": "id"},
         accepted_actions=["allow", "clarify", "abstain"],
         facts=[fact("max_images", "max_images", unit="images", country="id"),
                fact("tie_count", "tie_count", unit="listings", country="id")],
         tags=["tie"]),
    # Sentinel/display-cap: đỉnh thô của ID là 999 999 999 trên dòng "FREE GIFT"
    # — một ô giữ chỗ nhìn thấy được từ dữ liệu. Chấp nhận: từ chối vì chất
    # lượng dữ liệu, HOẶC allow với đỉnh đã loại giữ chỗ; cấm allow đỉnh thô.
    case("Giá cao nhất tại Indonesia ngày 03/07 là bao nhiêu?", answerability=A,
         action="abstain", category="sentinel", group_id="g_maxprice_id",
         country="id", oracle_id="max_price_excl_placeholder", params={"country": "id"},
         accepted_actions=["abstain", "clarify", "allow"],
         facts=[fact("max_price_excl_placeholder", "max_price_excl_placeholder",
                     unit="IDR", country="id", value_type="decimal",
                     tol=("absolute", 0.5))],
         forbidden_values=[999999999.0, 9999999.0], tags=["sentinel"]),
]

# ─── TỶ LỆ ──────────────────────────────────────────────────────────────────
C += [
    case("Tỷ lệ listing có giảm giá tại Việt Nam ngày 03/07 là bao nhiêu phần trăm?",
         answerability=A, action="allow", category="ratio",
         group_id="g_ratio_vn", country="vn",
         oracle_id="discount_ratio", params={"country": "vn"},
         facts=[fact("discounted_ratio_percent", "discounted_ratio_percent",
                     unit="percent", country="vn", value_type="decimal",
                     tol=("absolute", 0.05))]),
    case("Bao nhiêu phần trăm listing ở Việt Nam đang có giảm giá vào ngày 03/07?",
         answerability=A, action="allow", category="ratio",
         group_id="g_ratio_vn", country="vn",
         oracle_id="discount_ratio", params={"country": "vn"},
         facts=[fact("discounted_ratio_percent", "discounted_ratio_percent",
                     unit="percent", country="vn", value_type="decimal",
                     tol=("absolute", 0.05))]),
    case("Tỷ lệ listing có giảm giá tại Indonesia ngày 03/07 là bao nhiêu phần trăm?",
         answerability=A, action="allow", category="ratio",
         group_id="g_ratio_id", country="id",
         oracle_id="discount_ratio", params={"country": "id"},
         facts=[fact("discounted_ratio_percent", "discounted_ratio_percent",
                     unit="percent", country="id", value_type="decimal",
                     tol=("absolute", 0.05))]),
]

# ─── HAI MỐC THỜI GIAN ──────────────────────────────────────────────────────
delta_facts = lambda c: [
    fact("count_start", "count_start", unit="listings", country=c,
         date_start="2026-07-01", date_end="2026-07-01"),
    fact("count_end", "count_end", unit="listings", country=c),
    fact("count_delta", "count_delta", unit="listings", country=c,
         date_start="2026-07-01", date_end=D3),
]
C += [
    case("Số listing tại Việt Nam thay đổi thế nào từ 01/07 đến 03/07?",
         answerability=A, action="allow", category="date_window",
         group_id="g_delta_vn", country="vn",
         oracle_id="listing_delta",
         params={"country": "vn", "d0": "2026-07-01", "d1": D3},
         facts=delta_facts("vn")),
    case("Listing count ở Việt Nam từ 01/07 tới 03/07 tăng hay giảm bao nhiêu?",
         answerability=A, action="allow", category="date_window", language="mixed",
         group_id="g_delta_vn", country="vn",
         oracle_id="listing_delta",
         params={"country": "vn", "d0": "2026-07-01", "d1": D3},
         facts=delta_facts("vn")),
    case("Số listing tại Indonesia thay đổi thế nào từ 01/07 đến 03/07?",
         answerability=A, action="allow", category="date_window",
         group_id="g_delta_id", country="id",
         oracle_id="listing_delta",
         params={"country": "id", "d0": "2026-07-01", "d1": D3},
         facts=delta_facts("id")),
]

# ─── SO SÁNH ────────────────────────────────────────────────────────────────
C += [
    case('Shop "Richy - Chi nhánh Miền Nam" hay "Bibica Official Store" có nhiều '
         "listing hơn tại Việt Nam ngày 03/07?",
         answerability=A, action="allow", category="comparison",
         group_id="g_cmp_shops_vn", country="vn",
         entity_text="Richy - Chi nhánh Miền Nam",
         oracle_id="compare_two_shops",
         params={"country": "vn", "shop_a": "Richy - Chi nhánh Miền Nam",
                 "shop_b": "Bibica Official Store"},
         facts=[fact("count_a", "count_a", unit="listings", country="vn",
                     filters=["shop=Richy - Chi nhánh Miền Nam"]),
                fact("count_b", "count_b", unit="listings", country="vn",
                     filters=["shop=Bibica Official Store"]),
                fact("winner", "winner", unit=None, country="vn", value_type="string")]),
    case("GLAD2GLOW và Cyeecare, thương hiệu nào nhiều listing hơn tại Indonesia ngày 03/07, và hơn kém cụ thể ra sao?",
         answerability=A, action="allow", category="comparison",
         group_id="g_cmp_brands_id", country="id", entity_text="GLAD2GLOW",
         oracle_id="brand_listing_count", params={"country": "id", "brand": "GLAD2GLOW"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="id",
                     filters=["brand=GLAD2GLOW"])]),
]

# ─── ENTITY THEO MÃ ─────────────────────────────────────────────────────────
C += [
    case("Giá của sản phẩm mã 2260506115 tại Việt Nam ngày 03/07 là bao nhiêu?",
         answerability=A, action="allow", category="entity",
         group_id="g_item_price", country="vn", entity_text="2260506115",
         oracle_id="item_price", params={"country": "vn", "item_id": 2260506115},
         facts=[fact("price", "price", unit="VND", country="vn",
                     value_type="decimal", tol=("absolute", 0.5))]),
    case("Điểm đánh giá của sản phẩm mã 7005434955 tại Việt Nam ngày 03/07 là bao nhiêu?",
         answerability=A, action="allow", category="entity",
         group_id="g_item_rating", country="vn", entity_text="7005434955",
         oracle_id="item_rating", params={"country": "vn", "item_id": 7005434955},
         facts=[fact("rating", "rating", unit="stars", country="vn",
                     value_type="decimal", tol=("absolute", 0.005))]),
    case('Sản phẩm "Thùng Sữa lúa mạch Nestle MILO ít đường (48 Hộp x 180ml)" có bao '
         "nhiêu lượt đánh giá tại Việt Nam ngày 03/07?",
         answerability=A, action="allow", category="entity",
         group_id="g_item_ratingcount", country="vn",
         entity_text="Thùng Sữa lúa mạch Nestle MILO ít đường (48 Hộp x 180ml)",
         oracle_id="item_rating_count", params={"country": "vn", "item_id": 2260506115},
         facts=[fact("rating_count", "rating_count", unit="ratings", country="vn")]),
]

# ─── KẾT QUẢ RỖNG THẬT ──────────────────────────────────────────────────────
C += [
    case('Có bao nhiêu listing của Bibica tại shop "Richy - Chi nhánh Miền Nam" '
         "ở Việt Nam ngày 03/07?",
         answerability=A, action="allow", category="empty_result",
         group_id="g_empty_brandshop", country="vn", entity_text="Bibica",
         oracle_id="brand_at_shop_count",
         params={"country": "vn", "brand": "Bibica",
                 "shop_name": "Richy - Chi nhánh Miền Nam"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     filters=["brand=Bibica", "shop=Richy - Chi nhánh Miền Nam"])]),
    case("Thương hiệu ORION có bao nhiêu listing tại Indonesia ngày 03/07?",
         answerability=A, action="allow", category="empty_result",
         group_id="g_empty_orion_id", country="id", entity_text="ORION",
         oracle_id="brand_listing_count", params={"country": "id", "brand": "ORION"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="id",
                     filters=["brand=ORION"])]),
    case("Có bao nhiêu listing giá trên 5 triệu đồng tại Việt Nam ngày 03/07?",
         answerability=A, action="allow", category="empty_result",
         group_id="g_empty_price5m", country="vn",
         oracle_id="price_over", params={"country": "vn", "threshold": 5_000_000},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     filters=["price>5000000"])]),
    case("Thương hiệu Cyeecare có bao nhiêu listing tại Việt Nam ngày 03/07?",
         answerability=A, action="allow", category="empty_result",
         group_id="g_empty_cyeecare_vn", country="vn", entity_text="Cyeecare",
         oracle_id="brand_listing_count", params={"country": "vn", "brand": "Cyeecare"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     filters=["brand=Cyeecare"])]),
    case('Shop "ghaniskin" có bao nhiêu listing tại Việt Nam ngày 03/07?',
         answerability=A, action="allow", category="empty_result",
         group_id="g_empty_ghaniskin_vn", country="vn", entity_text="ghaniskin",
         oracle_id="shop_listing_count",
         params={"country": "vn", "shop_name": "ghaniskin"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     filters=["shop=ghaniskin"])]),
]

# ─── VOUCHER TƯỜNG MINH ─────────────────────────────────────────────────────
C += [
    case("Có bao nhiêu listing có voucher có cấu trúc tại Việt Nam ngày 03/07?",
         answerability=A, action="allow", category="filter",
         group_id="g_voucher_structured_vn", country="vn",
         oracle_id="structured_voucher_count", params={"country": "vn"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     filters=["structured_voucher=true"])]),
    case("Có bao nhiêu listing có nhãn voucher hiển thị tại Indonesia ngày 03/07?",
         answerability=A, action="allow", category="filter",
         group_id="g_voucher_label_id", country="id",
         oracle_id="voucher_label_count", params={"country": "id"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="id",
                     filters=["voucher_label>=1"])]),
]

# ─── MULTI-TURN ─────────────────────────────────────────────────────────────
C += [
    case(None, answerability=A, action="allow", category="multi_turn",
         group_id="g_mt_shops", country="vn",
         oracle_id="shop_count", params={"country": "id"},
         facts=[fact("shop_count", "shop_count", unit="shops", country="id",
                     grain="shop")],
         turns=[
             {"question": "Có bao nhiêu shop ở Việt Nam?", "expected_action": "allow"},
             {"question": "Còn ở Indonesia thì sao?", "expected_action": "allow",
              "scored": True},
         ]),
    case(None, answerability=A, action="allow", category="multi_turn",
         group_id="g_mt_bibica", country="vn",
         oracle_id="brand_listing_count", params={"country": "vn", "brand": "Bibica"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     filters=["brand=Bibica"])],
         turns=[
             {"question": "Có bao nhiêu listing tại Việt Nam ngày 03/07?",
              "expected_action": "allow"},
             {"question": "Trong số đó, bao nhiêu listing thuộc thương hiệu Bibica?",
              "expected_action": "allow", "scored": True},
         ]),
]

# ─── NEEDS_CLARIFICATION (15) ───────────────────────────────────────────────
N = "needs_clarification"
C += [
    case("Có bao nhiêu listing ngày 03/07?", answerability=N, action="clarify",
         category="count", group_id="g_cl_country", slots=["country"],
         oracle_id="listing_count", params={"country": "vn"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn")],
         turns=[
             {"question": "Có bao nhiêu listing ngày 03/07?",
              "expected_action": "clarify"},
             {"question": "Tại Việt Nam.", "expected_action": "allow", "scored": True},
         ]),
    case("How many products are listed on 03/07?", answerability=N, action="clarify",
         category="count", language="en", group_id="g_cl_country", slots=["country"]),
    case("Tổng số sản phẩm đang bán là bao nhiêu?", answerability=N,
         action="clarify", category="count", group_id="g_cl_country_nodate",
         slots=["country"]),
    case("Có bao nhiêu listing có voucher tại Việt Nam ngày 03/07?", answerability=N,
         action="clarify", category="ambiguous_term", group_id="g_cl_voucher_vn",
         country="vn", slots=["voucher_definition"],
         oracle_id="structured_voucher_count", params={"country": "vn"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="vn",
                     filters=["structured_voucher=true"])],
         turns=[
             {"question": "Có bao nhiêu listing có voucher tại Việt Nam ngày 03/07?",
              "expected_action": "clarify"},
             {"question": "Ý tôi là voucher có cấu trúc (có mã và mức chiết khấu).",
              "expected_action": "allow", "scored": True},
         ],
         tags=["two_voucher_concepts:577_vs_419"]),
    case("Có bao nhiêu listing có voucher tại Indonesia ngày 03/07?", answerability=N,
         action="clarify", category="ambiguous_term", group_id="g_cl_voucher_id",
         country="id", slots=["voucher_definition"],
         oracle_id="voucher_label_count", params={"country": "id"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="id",
                     filters=["voucher_label>=1"])],
         turns=[
             {"question": "Có bao nhiêu listing có voucher tại Indonesia ngày 03/07?",
              "expected_action": "clarify"},
             {"question": "Tính theo nhãn voucher hiển thị trên listing.",
              "expected_action": "allow", "scored": True},
         ],
         tags=["two_voucher_concepts:0_vs_210"]),
    case("Shop nào lớn nhất tại Việt Nam?", answerability=N, action="clarify",
         category="ambiguous_metric", group_id="g_cl_bestshop", country="vn",
         slots=["ranking_metric"],
         oracle_id="top_shop_by_listings", params={"country": "vn"},
         facts=[fact("shop_name", "shop_name", unit=None, country="vn",
                     value_type="string", grain="shop")],
         turns=[
             {"question": "Shop nào lớn nhất tại Việt Nam?",
              "expected_action": "clarify"},
             {"question": "Theo số listing đang bán ngày 03/07.",
              "expected_action": "allow", "scored": True},
         ]),
    case("Sản phẩm tốt nhất tại Việt Nam là gì?", answerability=N, action="clarify",
         category="ambiguous_metric", group_id="g_cl_bestproduct", country="vn",
         slots=["ranking_metric"]),
    case("Giá của Milo là bao nhiêu?", answerability=N, action="clarify",
         category="entity_ambiguity", group_id="g_cl_milo", country="vn",
         entity_text="Milo", slots=["entity_disambiguation"],
         tags=["18_matching_listings"]),
    case("Bao nhiêu sản phẩm bán chạy tại Việt Nam?", answerability=N,
         action="clarify", category="undefined_threshold", group_id="g_cl_banchay",
         country="vn", slots=["definition_threshold"]),
    case("Giá cao nhất là bao nhiêu?", answerability=N, action="clarify",
         category="count", group_id="g_cl_maxprice_nocountry", slots=["country"]),
    case("Cho tôi điểm đánh giá trung bình theo nhóm tại Việt Nam ngày 03/07.",
         answerability=N, action="clarify", category="ambiguous_groupby",
         group_id="g_cl_groupby", country="vn", slots=["group_dimension"]),
    case("Berapa banyak produk?", answerability=N, action="clarify",
         category="count", language="id", group_id="g_cl_berapa", slots=["country"],
         oracle_id="listing_count", params={"country": "id"},
         facts=[fact("listing_count", "listing_count", unit="listings", country="id")],
         turns=[
             {"question": "Berapa banyak produk?", "expected_action": "clarify"},
             {"question": "Di Indonesia, pada tanggal 03/07.",
              "expected_action": "allow", "scored": True},
         ]),
    case("Cho tôi số liệu về Bibica tại Việt Nam.", answerability=N,
         action="clarify", category="ambiguous_metric", group_id="g_cl_bibica_metric",
         country="vn", entity_text="Bibica", slots=["metric"]),
    case("So sánh hai shop tại Việt Nam giúp tôi.", answerability=N,
         action="clarify", category="entity_ambiguity", group_id="g_cl_whichshops",
         country="vn", slots=["entity_disambiguation"]),
    case("Doanh số thay đổi thế nào?", answerability=N, action="clarify",
         category="count", group_id="g_cl_sales_change", slots=["country"]),
]

# ─── UNANSWERABLE (20) ──────────────────────────────────────────────────────
U = "unanswerable"

def ucase(q, group, refusal, language="vi", category="missing_field", tags=()):
    return case(q, answerability=U, action="abstain", category=category,
                language=language, group_id=group, refusal_class=refusal,
                accepted_actions=["abstain", "clarify"], tags=list(tags))

C += [
    ucase("Lợi nhuận của shop Richy - Chi nhánh Miền Nam trong tháng 7 là bao nhiêu?",
          "g_u_profit", "missing_field"),
    ucase("Berapa laba merek GLAD2GLOW bulan Juli?", "g_u_profit", "missing_field",
          language="id"),
    ucase("Tồn kho hiện tại của Bibica còn bao nhiêu sản phẩm?", "g_u_inventory",
          "missing_field"),
    ucase("Listing MILO có bao nhiêu lượt xem trang trong ngày 03/07?",
          "g_u_pageviews", "missing_field"),
    ucase("Tỷ lệ chuyển đổi đơn hàng tại Việt Nam ngày 03/07 là bao nhiêu?",
          "g_u_conversion", "missing_field"),
    ucase("Ngày 03/07 có bao nhiêu đơn hàng được đặt tại Việt Nam?",
          "g_u_orders", "missing_grain", category="missing_grain"),
    ucase("Dự báo doanh số tuần sau của GLAD2GLOW tại Indonesia?",
          "g_u_forecast", "forecast_unsupported", category="forecast"),
    ucase("Predict next week's total sales for Vietnam.", "g_u_forecast",
          "forecast_unsupported", language="en", category="forecast"),
    ucase("Tổng doanh thu Việt Nam và Indonesia cộng lại là bao nhiêu tiền?",
          "g_u_crosscurrency", "cross_currency", category="cross_currency"),
    ucase("Quy đổi giá trung vị của Indonesia sang VND giúp tôi.",
          "g_u_crosscurrency", "cross_currency", category="cross_currency"),
    ucase("Có bao nhiêu listing tại Việt Nam ngày 04/07?", "g_u_date_oor",
          "date_out_of_range", category="date_out_of_range"),
    ucase("Số listing tại Việt Nam ngày 30/06 là bao nhiêu?", "g_u_date_oor",
          "date_out_of_range", category="date_out_of_range"),
    ucase("Điểm NPS của shop Richy - Chi nhánh Miền Nam là bao nhiêu?",
          "g_u_nps", "missing_field"),
    ucase("Shop Bibica Official Store có bao nhiêu nhân viên?", "g_u_employees",
          "missing_field"),
    ucase("Cho tôi doanh số theo từng SKU của thùng sữa MILO.", "g_u_sku",
          "missing_grain", category="missing_grain"),
    ucase("Doanh thu theo từng giờ trong ngày 03/07 tại Việt Nam?", "g_u_hourly",
          "missing_grain", category="missing_grain"),
    ucase("Vì sao số listing tại Indonesia tăng mạnh từ 01/07 đến 03/07?",
          "g_u_false_premise", "false_premise", category="false_premise",
          tags=["truth:474->474_flat"]),
    ucase("Vì sao Việt Nam mất một nửa số listing trong tuần đầu tháng 7?",
          "g_u_false_premise", "false_premise", category="false_premise",
          tags=["truth:581->668_grew"]),
    ucase("Giá của các đối thủ ngoài sàn Shopee cho sản phẩm MILO là bao nhiêu?",
          "g_u_external", "external_data", category="external_data"),
    ucase("Chi phí quảng cáo của Glad2Glow Official Store tháng 7 là bao nhiêu?",
          "g_u_adspend", "missing_field"),
]


def main() -> None:
    assert len(C) == 100, f"cần đúng 100 case, đang có {len(C)}"
    by_class = {}
    for item in C:
        by_class[item["answerability"]] = by_class.get(item["answerability"], 0) + 1
    assert by_class == {
        "directly_answerable": 65, "needs_clarification": 15, "unanswerable": 20,
    }, by_class

    # Split theo hash paraphrase_group — nhóm không bao giờ bị xẻ đôi.
    dev, holdout = [], []
    for item in C:
        digest = hashlib.sha256(item["paraphrase_group"].encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 5
        item["split"] = "holdout" if bucket < 2 else "dev"
        (holdout if item["split"] == "holdout" else dev).append(item)

    dev_path = HERE / "dev.json"
    holdout_path = HERE / "holdout.json"
    dev_path.write_text(json.dumps(dev, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    holdout_path.write_text(json.dumps(holdout, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")

    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    groups = {}
    for item in C:
        groups.setdefault(item["paraphrase_group"], 0)
        groups[item["paraphrase_group"]] += 1
    manifest = {
        "schema_version": "accuracy-benchmark.v1",
        "status": "provisional_contaminated",
        "contamination_note": (
            "Tác giả benchmark là agent đã đọc và thi công runtime Gladiators "
            "trong cùng phiên làm việc (SolutionSpec2808 W1-W15). Câu hỏi được "
            "soạn thuần từ data/processed và oracle tính bằng pandas độc lập, "
            "nhưng KHÔNG THỂ loại trừ thiên lệch chọn câu theo hiểu biết về "
            "capability của hệ. Vì vậy: đây KHÔNG phải holdout độc lập theo "
            "nghĩa TC_formulation §3; nhãn đúng là data-grounded synthetic "
            "benchmark, provisional_contaminated. Một holdout sạch cần người "
            "soạn chưa từng đọc implementation."
        ),
        "annotation_status": "pending_independent_review",
        "sampling_note": (
            "Không có log câu hỏi production hay nghiên cứu người dùng — đây là "
            "data-grounded synthetic benchmark, không phải mẫu đại diện traffic."
        ),
        "case_count": len(C),
        "distribution": {
            "answerability": by_class,
            "language": _count(C, "language"),
            "category": _count(C, "category"),
            "country": _count(C, "country"),
            "split": {"dev": len(dev), "holdout": len(holdout)},
            "paraphrase_groups_total": len(groups),
            "paraphrase_groups_multi": sum(1 for v in groups.values() if v >= 2),
            "entity_text_cases": sum(1 for c in C if c["entity_text"]),
            "ranking_cases": sum(1 for c in C if "ranking" in c["category"]),
            "empty_result_cases": sum(
                1 for c in C if c["category"] == "empty_result"),
            "multi_turn_cases": sum(1 for c in C if c["turns"]),
        },
        "artifact_sha256": oracle.ARTIFACT_SHA256,
        "dev_sha256": sha(dev_path),
        "holdout_sha256": sha(holdout_path),
        "sealed_at": "2026-08-29",
        "changelog": [
            {"version": "v1", "date": "2026-08-29",
             "change": "khởi tạo 100 case; seal dev+holdout",
             "author": "claude-fable-5 session d3f7bbc8"},
        ],
    }
    (HERE / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
    )
    print(json.dumps(manifest["distribution"], ensure_ascii=False, indent=1))
    print("dev_sha256", manifest["dev_sha256"][:16],
          "holdout_sha256", manifest["holdout_sha256"][:16])


def _count(cases, key):
    out = {}
    for item in cases:
        value = item.get(key) or "none"
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


if __name__ == "__main__":
    main()
