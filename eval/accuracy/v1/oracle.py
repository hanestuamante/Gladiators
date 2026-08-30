#!/usr/bin/env python3
"""Oracle độc lập cho benchmark accuracy v1 — thuần pandas, KHÔNG import gladiators.

Hợp đồng (TC_formulation §7):
- đọc thẳng artifact đã đóng băng trong ``data/processed``;
- kiểm dataset hash TRƯỚC khi tính, hash lệch ⇒ fail loud;
- mỗi ``oracle_id`` là một hàm pandas dễ review, KHÔNG dùng chung query/compiler
  với hệ bị đo;
- ``--verify`` tái tính mọi expected_fact trong dev.json/holdout.json và so với
  fixture; KHÔNG ghi đè;
- không có chế độ regenerate cho holdout đã seal (kiểm hash manifest và từ chối).

Chạy:
    python eval/accuracy/v1/oracle.py --verify
    python eval/accuracy/v1/oracle.py --hash
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DATA = REPO / "data" / "processed"
LATEST = "2026-07-03"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Hash chuẩn hoá CRLF→LF của từng artifact oracle đọc. Đây là bản TÁI HIỆN ĐỘC
# LẬP của phép băm (không import từ repo) — trùng giá trị là một phép kiểm chéo,
# không phải một phụ thuộc.
ARTIFACT_SHA256 = {
    "products_clean.csv":
        "c4e1db3a04807e4cece5aea1327767d9ede1ea006fd12d4f65a7993fc914d390",
    "product_snapshot_metrics.csv":
        "e71ca60488fa5bdb03544d3483937e633b974e70b71c69556157cce9660e35be",
    "shop_info_clean.csv":
        "9c72a533e1554f38db97cd4fd1b3edfb35bbd50d1a6b01512a9699a28ca83b16",
}


def _normalized_sha(path: Path) -> str:
    payload = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(payload).hexdigest()


def assert_data_hashes() -> None:
    for name, expected in ARTIFACT_SHA256.items():
        actual = _normalized_sha(DATA / name)
        if actual != expected:
            raise SystemExit(
                f"FAIL DATA_HASH: {name} = {actual[:16]}… lệch fixture "
                f"{expected[:16]}… — oracle chỉ có nghĩa trên đúng bộ dữ liệu đã seal."
            )


class Tables:
    """Nạp một lần; mọi oracle nhận cùng frame đã khử trùng lặp theo listing."""

    def __init__(self) -> None:
        self.products = pd.read_csv(DATA / "products_clean.csv")
        self.snapshots = pd.read_csv(DATA / "product_snapshot_metrics.csv")
        self.shops = pd.read_csv(DATA / "shop_info_clean.csv")

    def listings(self, country: str, date: str = LATEST) -> pd.DataFrame:
        frame = self.products
        frame = frame[(frame.country_code == country) & (frame.date == date)]
        return frame.drop_duplicates("product_listing_key")

    def snapshot_listings(self, country: str, date: str = LATEST) -> pd.DataFrame:
        frame = self.snapshots
        frame = frame[(frame.country_code == country) & (frame.date == date)]
        return frame.drop_duplicates("product_listing_key")


# --- registry oracle --------------------------------------------------------
# Mỗi hàm trả dict {fact_key: value}. Giá trị float giữ NGUYÊN độ chính xác —
# tolerance là việc của scorer, không phải của oracle.

def o_listing_count(t: Tables, country: str, date: str = LATEST) -> dict:
    return {"listing_count": int(len(t.listings(country, date)))}


def o_shop_count(t: Tables, country: str) -> dict:
    return {"shop_count": int(t.shops[t.shops.country_code == country].shop_id.nunique())}


def o_brand_count(t: Tables, country: str) -> dict:
    return {"brand_count": int(t.listings(country).brand.nunique())}


def o_brand_listing_count(t: Tables, country: str, brand: str) -> dict:
    return {"listing_count": int((t.listings(country).brand == brand).sum())}


def o_shop_listing_count(t: Tables, country: str, shop_name: str) -> dict:
    frame = t.listings(country)
    shop_ids = set(
        t.shops[(t.shops.country_code == country) & (t.shops.shop_name == shop_name)].shop_id,
    )
    return {"listing_count": int(frame.shop_id.isin(shop_ids).sum())}


def o_brand_at_shop_count(t: Tables, country: str, brand: str, shop_name: str) -> dict:
    frame = t.listings(country)
    shop_ids = set(
        t.shops[(t.shops.country_code == country) & (t.shops.shop_name == shop_name)].shop_id,
    )
    return {"listing_count": int(((frame.brand == brand) & frame.shop_id.isin(shop_ids)).sum())}


def o_median_price(t: Tables, country: str) -> dict:
    return {"median_price": float(t.listings(country).price_num.median())}


def o_median_rating(t: Tables, country: str) -> dict:
    return {"median_rating": float(t.listings(country).rating_num.median())}


def o_mean_images(t: Tables, country: str) -> dict:
    return {"mean_images": float(t.listings(country).images_count.mean())}


def o_sum_brand_likes(t: Tables, country: str, brand: str) -> dict:
    frame = t.listings(country)
    return {"total_likes": int(frame.loc[frame.brand == brand, "liked_count_num"].sum())}


def o_max_price_listing(t: Tables, country: str) -> dict:
    frame = t.listings(country)
    top = frame.price_num.max()
    winners = frame[frame.price_num == top]
    return {
        "max_price": float(top),
        "tie_count": int(len(winners)),
        "product_name": str(winners.iloc[0].product_name) if len(winners) == 1 else None,
    }


def o_min_price(t: Tables, country: str) -> dict:
    return {"min_price": float(t.listings(country).price_num.min())}


def o_max_price_excl_placeholder(t: Tables, country: str) -> dict:
    """Đỉnh giá SAU khi loại giá trị giữ chỗ nhìn thấy được từ dữ liệu.

    Quan sát thuần dữ liệu: các dòng giá 9 999 999 / 999 999 999 (mọi chữ số 9)
    mang tiêu đề "[GIVEAWAY]" / "FREE GIFT" — chúng là ô-không-bán được điền
    số, không phải mức giá. Oracle ghi CẢ HAI: đỉnh thô và đỉnh đã loại.
    """
    frame = t.listings(country)
    def is_repdigit9(v: float) -> bool:
        if pd.isna(v) or v <= 0 or v != int(v):
            return False
        digits = str(int(v))
        return len(digits) >= 7 and set(digits) == {"9"}
    raw = float(frame.price_num.max())
    clean = frame[~frame.price_num.map(is_repdigit9)]
    return {"max_price_raw": raw, "max_price_excl_placeholder": float(clean.price_num.max())}


def o_top_liked_listing(t: Tables, country: str) -> dict:
    frame = t.listings(country)
    top = frame.liked_count_num.max()
    winners = frame[frame.liked_count_num == top]
    return {
        "max_likes": float(top), "tie_count": int(len(winners)),
        "product_name": str(winners.iloc[0].product_name) if len(winners) == 1 else None,
    }


def o_top_rating_count_listing(t: Tables, country: str) -> dict:
    frame = t.listings(country)
    top = frame.rating_count_num.max()
    winners = frame[frame.rating_count_num == top]
    return {
        "max_rating_count": float(top), "tie_count": int(len(winners)),
        "product_name": str(winners.iloc[0].product_name) if len(winners) == 1 else None,
    }


def o_max_images_tie(t: Tables, country: str) -> dict:
    frame = t.listings(country)
    top = frame.images_count.max()
    return {"max_images": int(top), "tie_count": int((frame.images_count == top).sum())}


def o_top_shop_by_listings(t: Tables, country: str) -> dict:
    frame = t.listings(country)
    per_shop = frame.groupby("shop_id").size().sort_values(ascending=False)
    names = t.shops.drop_duplicates("shop_id").set_index("shop_id").shop_name
    top_id = per_shop.index[0]
    ties = int((per_shop == per_shop.iloc[0]).sum())
    return {
        "shop_name": str(names.get(top_id, top_id)),
        "listing_count": int(per_shop.iloc[0]), "tie_count": ties,
    }


def o_top_brand_by_listings(t: Tables, country: str) -> dict:
    counts = t.listings(country).brand.value_counts()
    return {
        "brand": str(counts.index[0]), "listing_count": int(counts.iloc[0]),
        "tie_count": int((counts == counts.iloc[0]).sum()),
    }


def o_verified_count(t: Tables, country: str) -> dict:
    return {"listing_count": int(t.listings(country).shopee_verified_bool.sum())}


def o_discount_over(t: Tables, country: str, threshold: float) -> dict:
    frame = t.listings(country)
    return {"listing_count": int((frame.discount_percent_num > threshold).sum())}


def o_price_over(t: Tables, country: str, threshold: float) -> dict:
    frame = t.listings(country)
    return {"listing_count": int((frame.price_num > threshold).sum())}


def o_discount_ratio(t: Tables, country: str) -> dict:
    frame = t.listings(country)
    numerator = int(frame.discount_percent_num.notna().sum())
    denominator = int(len(frame))
    if denominator == 0:
        raise SystemExit("FAIL ORACLE: mẫu số rỗng cho discount_ratio")
    return {
        "discounted_count": numerator, "listing_count": denominator,
        "discounted_ratio_percent": 100.0 * numerator / denominator,
    }


def o_listing_delta(t: Tables, country: str, d0: str, d1: str) -> dict:
    start = int(len(t.listings(country, d0)))
    end = int(len(t.listings(country, d1)))
    return {"count_start": start, "count_end": end, "count_delta": end - start}


def o_item_price(t: Tables, country: str, item_id: int) -> dict:
    frame = t.listings(country)
    rows = frame[frame.item_id == item_id]
    if len(rows) != 1:
        raise SystemExit(f"FAIL ORACLE: item {item_id} có {len(rows)} dòng")
    return {"price": float(rows.iloc[0].price_num)}


def o_item_rating(t: Tables, country: str, item_id: int) -> dict:
    frame = t.listings(country)
    rows = frame[frame.item_id == item_id]
    if len(rows) != 1:
        raise SystemExit(f"FAIL ORACLE: item {item_id} có {len(rows)} dòng")
    return {"rating": float(rows.iloc[0].rating_num)}


def o_item_rating_count(t: Tables, country: str, item_id: int) -> dict:
    frame = t.listings(country)
    rows = frame[frame.item_id == item_id]
    if len(rows) != 1:
        raise SystemExit(f"FAIL ORACLE: item {item_id} có {len(rows)} dòng")
    return {"rating_count": int(rows.iloc[0].rating_count_num)}


def o_structured_voucher_count(t: Tables, country: str) -> dict:
    frame = t.snapshot_listings(country)
    return {"listing_count": int(frame.has_structured_voucher.sum())}


def o_voucher_label_count(t: Tables, country: str) -> dict:
    frame = t.listings(country)
    return {"listing_count": int((frame.vouchers_count > 0).sum())}


def o_compare_two_shops(t: Tables, country: str, shop_a: str, shop_b: str) -> dict:
    a = o_shop_listing_count(t, country, shop_a)["listing_count"]
    b = o_shop_listing_count(t, country, shop_b)["listing_count"]
    winner = shop_a if a > b else shop_b if b > a else None
    return {"count_a": a, "count_b": b, "winner": winner}


ORACLES = {
    "listing_count": o_listing_count,
    "shop_count": o_shop_count,
    "brand_count": o_brand_count,
    "brand_listing_count": o_brand_listing_count,
    "shop_listing_count": o_shop_listing_count,
    "brand_at_shop_count": o_brand_at_shop_count,
    "median_price": o_median_price,
    "median_rating": o_median_rating,
    "mean_images": o_mean_images,
    "sum_brand_likes": o_sum_brand_likes,
    "max_price_listing": o_max_price_listing,
    "min_price": o_min_price,
    "max_price_excl_placeholder": o_max_price_excl_placeholder,
    "top_liked_listing": o_top_liked_listing,
    "top_rating_count_listing": o_top_rating_count_listing,
    "max_images_tie": o_max_images_tie,
    "top_shop_by_listings": o_top_shop_by_listings,
    "top_brand_by_listings": o_top_brand_by_listings,
    "verified_count": o_verified_count,
    "discount_over": o_discount_over,
    "price_over": o_price_over,
    "discount_ratio": o_discount_ratio,
    "listing_delta": o_listing_delta,
    "item_price": o_item_price,
    "item_rating": o_item_rating,
    "item_rating_count": o_item_rating_count,
    "structured_voucher_count": o_structured_voucher_count,
    "voucher_label_count": o_voucher_label_count,
    "compare_two_shops": o_compare_two_shops,
}


def compute(oracle_id: str, params: dict, tables: Tables | None = None) -> dict:
    if oracle_id not in ORACLES:
        raise SystemExit(f"FAIL ORACLE: oracle_id không tồn tại: {oracle_id}")
    return ORACLES[oracle_id](tables or Tables(), **params)


def verify(case_files: list[Path]) -> int:
    assert_data_hashes()
    tables = Tables()
    mismatches: list[str] = []
    checked = 0
    for path in case_files:
        cases = json.loads(path.read_text(encoding="utf-8"))
        for case in cases:
            oracle = case.get("oracle")
            if not oracle or not oracle.get("oracle_id"):
                continue
            actual = compute(oracle["oracle_id"], oracle.get("params", {}), tables)
            for fact in case.get("expected_facts", []):
                key = fact.get("oracle_fact_key") or fact["metric"]
                if key not in actual:
                    mismatches.append(f"{case['id']}: oracle không phát {key}")
                    continue
                checked += 1
                expected, recomputed = fact["value"], actual[key]
                same = (
                    expected == recomputed
                    if not isinstance(recomputed, float)
                    else abs(float(expected) - recomputed) < 1e-12
                )
                if not same:
                    mismatches.append(
                        f"{case['id']}.{key}: fixture {expected!r} != tái tính {recomputed!r}",
                    )
    if mismatches:
        print("FAIL ORACLE_VERIFY:")
        for line in mismatches[:20]:
            print("  " + line)
        return 1
    print(f"OK — {checked} expected fact tái tính khớp fixture; hash dữ liệu khớp.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--hash", action="store_true")
    args = parser.parse_args()
    if args.hash:
        for name in sorted(ARTIFACT_SHA256):
            print(name, _normalized_sha(DATA / name))
        return 0
    if args.verify:
        return verify([HERE / "dev.json", HERE / "holdout.json"])
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
