#!/usr/bin/env python3
"""Sinh bộ đề từ DỮ LIỆU THÔ — Spec2308 §WP-B12, phục vụ §WP-B3.

Pandas thuần. **Không import gladiators**: một bộ đề dùng chung code với hệ bị
kiểm thì không thể mâu thuẫn với nó.

    python scripts/build_question_bank.py

GIỚI HẠN PHẢI ĐỌC KÈM MỌI CON SỐ ĐO TRÊN BỘ ĐỀ NÀY
---------------------------------------------------
§B3-R1 đòi người soạn KHÔNG đọc ``src/gladiators/``. Bộ đề này do một tác nhân
ĐÃ đọc toàn bộ codebase sinh ra, nên nó **không** thoả B3-R1. Hệ quả cụ thể:

* ``over_refusal_rate`` đo trên đây là **chặn dưới của thiên lệch**, không phải
  một phép đo sạch — câu hỏi sinh từ những gì dữ liệu có, nhưng cách diễn đạt
  khó tránh khỏi ảnh hưởng của việc biết hệ nhận dạng thế nào;
* nó **không thay thế** bộ đề do người ngoài soạn; nó chỉ làm việc soạn bộ đó rẻ
  hơn, vì đáp án đã có sẵn và tái lập được.

Mọi câu hỏi sinh từ CỘT và GIÁ TRỊ có thật trong ``data/processed/*.csv``, kèm
đáp án tính bằng pandas và đoạn code tái lập.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
LATEST = "2026-07-03"
FIRST = "2026-07-01"
MARKET = {"vn": "Việt Nam", "id": "Indonesia"}


def _case(cid, question, group, answerable, expected, snippet):
    return {
        "id": cid,
        "question": question,
        "paraphrase_group": group,
        "answerable": answerable,
        "expected_action": "allow" if answerable else "abstain",
        "expected_value": expected,
        "oracle_snippet": snippet,
        "author": "scripts/build_question_bank.py",
        # B3-R1 KHÔNG thoả. Nói thẳng trong từng case để con số đo trên bộ này
        # không bao giờ bị trích dẫn như một phép đo độc lập.
        "author_read_source_code": True,
    }


def build() -> list[dict]:
    products = pd.read_csv(DATA / "products_clean.csv")
    snapshots = pd.read_csv(DATA / "product_snapshot_metrics.csv")
    cases: list[dict] = []
    counter = {"n": 0}

    def nid() -> str:
        counter["n"] += 1
        return f"ans{counter['n']:03d}"

    def latest_products(country: str) -> pd.DataFrame:
        return products[
            (products.country_code == country)
            & (products.date.astype(str) == LATEST)
        ].drop_duplicates("product_listing_key")

    # --- đếm listing, hai cách diễn đạt cùng một ý (B3.1 bước 4) -----------
    for country, label in MARKET.items():
        value = {"listing_count": int(len(latest_products(country)))}
        group = f"g_count_listing_{country}"
        snippet = (
            f"P[(P.country_code=='{country}')&(P.date=='{LATEST}')]"
            ".drop_duplicates('product_listing_key').shape[0]"
        )
        cases.append(_case(nid(), f"Có bao nhiêu listing tại {label} ngày 03/07?",
                           group, True, value, snippet))
        cases.append(_case(nid(), f"Ngày 03/07 ở {label} có bao nhiêu sản phẩm?",
                           group, True, value, snippet))

    # --- đếm shop ---------------------------------------------------------
    for country, label in MARKET.items():
        value = {"shop_count": int(
            products[products.country_code == country].shop_id.nunique(),
        )}
        group = f"g_count_shop_{country}"
        snippet = f"P[P.country_code=='{country}'].shop_id.nunique()"
        cases.append(_case(nid(), f"Có bao nhiêu shop ở {label}?",
                           group, True, value, snippet))
        cases.append(_case(nid(), f"{label} có bao nhiêu cửa hàng?",
                           group, True, value, snippet))

    # --- đếm theo cờ boolean có thật ---------------------------------------
    for column, phrase in (
        ("shopee_verified_bool", "đã xác minh"),
        ("is_ad_bool", "là quảng cáo"),
        ("is_sold_out_bool", "đã hết hàng"),
    ):
        if column not in products.columns:
            continue
        for country, label in MARKET.items():
            frame = latest_products(country)
            value = {"listing_count": int(frame[column].sum())}
            snippet = (
                f"P[(P.country_code=='{country}')&(P.date=='{LATEST}')]"
                f".drop_duplicates('product_listing_key').{column}.sum()"
            )
            cases.append(_case(
                nid(), f"Có bao nhiêu listing {phrase} tại {label} ngày 03/07?",
                f"g_flag_{column}_{country}", True, value, snippet,
            ))

    # --- voucher, đọc từ snapshot metrics ----------------------------------
    for country, label in MARKET.items():
        frame = snapshots[
            (snapshots.country_code == country)
            & (snapshots.date.astype(str) == LATEST)
        ].drop_duplicates("product_listing_key")
        structured_value = {"listing_count": int(frame.has_structured_voucher.sum())}
        group = f"g_voucher_{country}"
        snippet = (
            f"S[(S.country_code=='{country}')&(S.date=='{LATEST}')]"
            ".drop_duplicates('product_listing_key').has_structured_voucher.sum()"
        )
        # W8.4: "có voucher" là HAI khái niệm (structured so với nhãn hiển thị
        # — trên ID: 0/474 so với 210/474). Câu mơ hồ giữ clarify; hai câu
        # tường minh đo hai oracle KHÁC NHAU.
        ambiguous = _case(
            nid(), f"Có bao nhiêu listing có voucher tại {label} ngày 03/07?",
            group, True, None, snippet,
        )
        ambiguous["expected_action"] = "clarify"
        ambiguous["expected_note"] = (
            "W8.3: cụm 'có voucher' chỉ hai khái niệm khác nhau; oracle cũ đo "
            "has_structured_voucher trong khi câu hỏi không nói rõ"
        )
        cases.append(ambiguous)
        cases.append(_case(
            nid(),
            f"Có bao nhiêu listing có voucher có cấu trúc tại {label} ngày 03/07?",
            group, True, structured_value, snippet,
        ))
        label_scope = products[
            (products.country_code == country)
            & (products.date.astype(str) == LATEST)
        ].drop_duplicates("product_listing_key")
        label_value = {
            "listing_count": int((label_scope.vouchers_count > 0).sum()),
        }
        cases.append(_case(
            nid(), f"Có bao nhiêu listing có nhãn voucher tại {label} ngày 03/07?",
            group, True, label_value,
            f"P[(P.country_code=='{country}')&(P.date=='{LATEST}')]"
            ".drop_duplicates('product_listing_key').vouchers_count.gt(0).sum()",
        ))

    # --- biến động số listing giữa hai snapshot ---------------------------
    for country, label in MARKET.items():
        first = products[
            (products.country_code == country) & (products.date.astype(str) == FIRST)
        ].product_listing_key.nunique()
        last = products[
            (products.country_code == country) & (products.date.astype(str) == LATEST)
        ].product_listing_key.nunique()
        cases.append(_case(
            nid(), f"Số listing tại {label} thay đổi thế nào từ 01/07 đến 03/07?",
            f"g_delta_{country}", True, {"delta": int(last - first)},
            f"P[P.country_code=='{country}'] nunique theo ngày, lấy hiệu hai mốc",
        ))

    # --- đếm listing cho TỪNG ngày có thật trong dữ liệu -------------------
    for date in sorted(products.date.astype(str).unique()):
        day = date[8:10] + "/" + date[5:7]
        for country, label in MARKET.items():
            frame = products[
                (products.country_code == country) & (products.date.astype(str) == date)
            ].drop_duplicates("product_listing_key")
            snippet = (
                f"P[(P.country_code=='{country}')&(P.date=='{date}')]"
                ".drop_duplicates('product_listing_key').shape[0]"
            )
            cases.append(_case(
                nid(), f"Ngày {day} tại {label} có bao nhiêu listing?",
                f"g_day_{date}_{country}", True,
                {"listing_count": int(len(frame))}, snippet,
            ))

    # --- đếm brand phân biệt ----------------------------------------------
    if "brand" in products.columns:
        for country, label in MARKET.items():
            frame = latest_products(country)
            value = {"brand_count": int(frame.brand.nunique(dropna=True))}
            snippet = (
                f"P[(P.country_code=='{country}')&(P.date=='{LATEST}')]"
                ".drop_duplicates('product_listing_key').brand.nunique()"
            )
            group = f"g_brand_{country}"
            cases.append(_case(nid(), f"Có bao nhiêu thương hiệu tại {label} ngày 03/07?",
                               group, True, value, snippet))
            cases.append(_case(nid(), f"{label} ngày 03/07 có bao nhiêu brand khác nhau?",
                               group, True, value, snippet))

    # --- shop chính hãng, đọc từ shop_info ---------------------------------
    shops = pd.read_csv(DATA / "shop_info_clean.csv")
    for country, label in MARKET.items():
        official = shops[
            (shops.country_code == country) & (shops.is_official_shop_bool == True)  # noqa: E712
        ]
        keys = set(official.shop_id)
        frame = latest_products(country)
        group = f"g_official_{country}"
        cases.append(_case(
            nid(), f"Có bao nhiêu shop chính hãng ở {label}?", group, True,
            {"shop_count": int(len(keys))},
            f"SH[(SH.country_code=='{country}')&(SH.is_official_shop_bool)].shop_id.nunique()",
        ))
        cases.append(_case(
            nid(), f"Có bao nhiêu listing của shop chính hãng tại {label} ngày 03/07?",
            f"{group}_listing", True,
            {"listing_count": int(frame.shop_id.isin(keys).sum())},
            "P latest ∩ shop_id thuộc tập official",
        ))

    # --- giá và điểm đánh giá ----------------------------------------------
    for country, label in MARKET.items():
        frame = latest_products(country)
        clean = frame[frame.price_num < 999_999_999]
        cases.append(_case(
            nid(), f"Giá trung vị tại {label} ngày 03/07 là bao nhiêu?",
            f"g_median_price_{country}", True,
            {"median_price": float(clean.price_num.median())},
            "P latest, loại sentinel 999999999, .price_num.median()",
        ))
        if "rating_num" in frame.columns:
            cases.append(_case(
                nid(), f"Điểm đánh giá trung vị tại {label} ngày 03/07 là bao nhiêu?",
                f"g_median_rating_{country}", True,
                {"median_rating": float(frame.rating_num.median())},
                "P latest .rating_num.median()",
            ))

    # --- 15-20% câu dữ liệu KHÔNG trả lời được, để đo over_answer_rate ----
    for question in (
        "Lợi nhuận ròng của từng shop tại Việt Nam là bao nhiêu?",
        "Chi phí quảng cáo trên mỗi đơn tại Indonesia là bao nhiêu?",
        "Tỷ lệ chuyển đổi của listing tại Việt Nam ngày 03/07?",
        "Tồn kho còn lại của từng sản phẩm tại Việt Nam?",
        "Dự báo doanh số tuần sau tại Indonesia?",
        "Giá của đối thủ ngoài sàn cho sản phẩm này là bao nhiêu?",
    ):
        cases.append(_case(nid(), question, f"g_no_{counter['n']:03d}", False, None,
                           "không tính được từ data/processed/*.csv"))
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="eval/independent/answerable_manual.json")
    args = parser.parse_args()

    cases = build()
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    answerable = sum(1 for case in cases if case["answerable"])
    print(json.dumps({
        "cases": len(cases),
        "answerable": answerable,
        "unanswerable": len(cases) - answerable,
        "unanswerable_share": round((len(cases) - answerable) / len(cases), 3),
        "paraphrase_groups": len({case["paraphrase_group"] for case in cases}),
        "b3_r1_satisfied": False,
        "output": str(out.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
