#!/usr/bin/env python3
"""Bộ đề hai lượt cho bộ nhớ hội thoại — Spec2308 §WP-A3, nghiệm thu.

    PYTHONPATH=src python scripts/build_multiturn_suite.py

Mỗi case gồm **hai lượt cùng một ``session_id``**:

* lượt 1 xác lập phạm vi (thị trường, và có khi cả ngày) và tự nó trả lời được;
* lượt 2 hỏi một câu **thiếu phạm vi** — không có bộ nhớ thì nó ra ``clarify``.

``clarify_recovery_rate`` = tỷ lệ case mà lượt 2 chuyển từ ``clarify`` sang
``allow`` **kèm evidence đúng oracle**. "Đúng oracle" là phần quan trọng: một bộ
nhớ điền bừa cũng làm lượt 2 thành ``allow``, và chỉ oracle mới phân biệt được
điền đúng với điền bừa.

GIỚI HẠN PHẢI ĐỌC KÈM MỌI CON SỐ ĐO TRÊN BỘ NÀY
------------------------------------------------
§WP-A3 đòi bộ đề **do người soạn**. Bộ này do một tác nhân đã đọc codebase sinh
ra, nên nó **không** thoả điều kiện đó — cùng lớp giới hạn với bộ B3
(``scripts/build_question_bank.py``). Từng case mang cờ
``author_read_source_code: true`` để con số không bao giờ bị trích dẫn như một
phép đo độc lập.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
LATEST = "2026-07-03"
MARKET = {"vn": "Việt Nam", "id": "Indonesia"}

# Câu lượt 1: tự trả lời được VÀ nêu rõ thị trường. Đây là điều kiện để lượt 2 có
# gì đó để kế thừa — một lượt 1 bị từ chối không xác lập ô nào cả.
OPENERS = (
    "Có bao nhiêu shop ở {label}?",
    "Có bao nhiêu listing tại {label} ngày 03/07?",
)

# Câu lượt 2: THIẾU phạm vi. Mỗi câu ở đây đã được kiểm là ra `clarify` khi hỏi
# một mình — nếu không, case đó không đo được điều gì.
FOLLOW_UPS = (
    ("Có bao nhiêu listing?", "listing_count"),
    ("Có bao nhiêu sản phẩm?", "listing_count"),
    ("Có bao nhiêu listing đã xác minh?", "verified_count"),
    ("Sản phẩm nào có giá cao nhất?", "max_price"),
    ("Shop nào có nhiều listing nhất?", "top_shop_listing_count"),
    ("Ngày nào có doanh thu cao nhất?", "any"),
)


def oracles() -> dict[str, dict[str, object]]:
    products = pd.read_csv(DATA / "products_clean.csv")
    per_country: dict[str, dict[str, object]] = {}
    for country in MARKET:
        latest = products[
            (products.country_code == country)
            & (products.date.astype(str) == LATEST)
        ].drop_duplicates("product_listing_key")
        # W15.4: bản sao thứ SÁU của hằng số sentinel từng nằm ở đây — oracle
        # kế thừa đúng cái cờ thiếu và ghim 9 999 999 (một giá trị giữ chỗ) làm
        # đáp án. Bộ sinh gọi cùng registry của W14; luật CHƯA duyệt không loại
        # dòng, nên max_price có thể rơi vào giá trị giữ chỗ — khi đó suite phải
        # khai abstain·A19-VALUE-CLASS chứ không khai allow với con số đó.
        from gladiators.domain.metrics import approved_exclusion_predicates

        clean = latest
        for _ref, op, value in approved_exclusion_predicates("measure.price"):
            if op == "lt":
                clean = clean[clean.price_num < value]
        per_country[country] = {
            "listing_count": int(len(latest)),
            "verified_count": int(latest.shopee_verified_bool.sum())
            if "shopee_verified_bool" in latest.columns else None,
            "max_price": float(clean.price_num.max()) if len(clean) else None,
            "top_shop_listing_count": int(
                latest.groupby("shop_id").size().max(),
            ) if len(latest) else None,
            "shop_count": int(products[products.country_code == country].shop_id.nunique()),
        }
    return per_country


def build() -> list[dict]:
    per_country = oracles()
    cases: list[dict] = []
    index = 0
    for country, label in MARKET.items():
        for opener in OPENERS:
            for question, metric in FOLLOW_UPS:
                index += 1
                expected = (
                    None if metric == "any" else per_country[country].get(metric)
                )
                cases.append({
                    "id": f"mt{index:03d}",
                    "session_id": f"mt{index:03d}",
                    "turns": [
                        {
                            "question": opener.format(label=label),
                            "expected_action": "allow",
                        },
                        {
                            "question": question,
                            # Không có bộ nhớ, lượt này ra clarify vì thiếu thị
                            # trường. Đây chính là thứ WP-A3 phải lật.
                            "expected_action": "allow",
                            "expected_action_without_memory": "clarify",
                            "expected_value": (
                                None if expected is None else {metric: expected}
                            ),
                        },
                    ],
                    "country": country,
                    "oracle_snippet": (
                        f"P[(P.country_code=='{country}')&(P.date=='{LATEST}')]"
                        ".drop_duplicates('product_listing_key')"
                    ),
                    "author": "scripts/build_multiturn_suite.py",
                    # §WP-A3 đòi người soạn. Không thoả — nói thẳng trong từng case.
                    "author_read_source_code": True,
                })
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="eval/questions_multiturn.json")
    args = parser.parse_args()

    cases = build()
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "cases": len(cases),
        "turns_per_case": 2,
        "human_authored": False,
        "output": str(out.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
