#!/usr/bin/env python3
"""Bảng giá theo ngày cấp listing, dựng từ ``product_promotions``.

    PYTHONPATH=src python scripts/build_price_panel.py --snapshot <snapshot_id>

Phát hiện dẫn tới script này: ``products_timeseries`` **không phải chuỗi thời
gian** — 1276/1276 listing xuất hiện đúng **một** ngày, 1154 trong số đó dồn vào
21/07. Cột ``date`` ở đó là *lần cuối nhìn thấy*.

Thứ **thật sự** là bảng theo ngày lại nằm dưới cái tên ``product_promotions``:
22.695 dòng, 0 null ở ``price``/``price_original``/``price_before_promo``,
1055–1168 listing mỗi ngày suốt 20 ngày, và 1046/1276 listing có ≥2 mức giá khác
nhau.

**Nhưng nó lệch chọn mẫu, và đó là điều phải in ra cùng mọi con số nó sinh.**
Bảng chỉ chứa listing *có bản ghi khuyến mãi* trong ngày đó — 83–92% mỗi ngày —
và phần thiếu **không thiếu ngẫu nhiên**. Lấy trung vị giá trên toàn bảng rồi gọi
là "giá trung vị thị trường" là một ước lượng lệch, đúng lớp lỗi sai-mà-im-lặng
mà cả kiến trúc này tồn tại để chặn.

Cách dùng đúng là **panel CÂN BẰNG**: chỉ giữ listing có mặt đủ mọi ngày, và nói
rõ nó là bao nhiêu phần trăm. Panel cân bằng trả lời được câu hỏi *"giá của cùng
những listing này đổi thế nào theo thời gian"* — một câu hỏi khác hẳn *"giá thị
trường là bao nhiêu"*, và là câu duy nhất dữ liệu này trả lời được.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PROMOTIONS_GLOB = "**/product_promotions_*.csv"
KEY = ["country_code", "shop_id", "item_id"]

# Chiến dịch 7.7 nằm trong dải 01–21/07. Đây KHÔNG phải mùa vụ — 20 ngày không đủ
# ước lượng mùa vụ tuần, mỗi thứ trong tuần chỉ có ~3 quan sát. Nó là một
# NGHIÊN CỨU SỰ KIỆN: trước / trong / sau một mốc đã biết.
CAMPAIGN_DATE = "2026-07-07"
CAMPAIGN_WINDOW = 2


def load_promotions(source: Path) -> pd.DataFrame:
    matches = sorted(source.glob(PROMOTIONS_GLOB))
    if not matches:
        raise FileNotFoundError(f"không thấy product_promotions_*.csv trong {source}")
    frame = pd.concat([pd.read_csv(path, low_memory=False) for path in matches])
    frame["date"] = frame["date"].astype(str)
    return frame


def build_panel(promotions: pd.DataFrame) -> dict:
    dates = sorted(promotions["date"].unique())
    per_listing = promotions.groupby(KEY)["date"].nunique()
    total_listings = len(per_listing)
    balanced_keys = per_listing[per_listing == len(dates)].index

    keyed = promotions.set_index(KEY)
    balanced = keyed.loc[keyed.index.isin(balanced_keys)].reset_index()
    # Một listing có thể có nhiều dòng khuyến mãi trong cùng một ngày; giá thấp
    # nhất là giá người mua thật sự trả, nên nó là đại diện đúng cho ngày đó.
    balanced = (
        balanced.sort_values("price")
        .drop_duplicates(subset=[*KEY, "date"], keep="first")
        .sort_values([*KEY, "date"])
        .reset_index(drop=True)
    )

    coverage = promotions.groupby("date").apply(
        lambda day: day.groupby(KEY).ngroups, include_groups=False,
    )
    return {
        "panel": balanced,
        "dates": dates,
        "total_listings": int(total_listings),
        "balanced_listings": int(len(balanced_keys)),
        "coverage_per_day_min": int(coverage.min()),
        "coverage_per_day_max": int(coverage.max()),
    }


def describe(built: dict) -> dict:
    """Metadata phải đi KÈM bảng, không nằm trong một tài liệu khác.

    Một panel không mang theo tỷ lệ phủ của chính nó sẽ được dùng như thể nó phủ
    100%, và cảnh báo nằm ở file khác thì không ai đọc.
    """
    panel, dates = built["panel"], built["dates"]
    total, balanced = built["total_listings"], built["balanced_listings"]
    share = balanced / total if total else 0.0
    return {
        "rows": int(len(panel)),
        "dates": len(dates),
        "date_range": [dates[0], dates[-1]] if dates else [],
        "listings_total": total,
        "listings_balanced": balanced,
        "balanced_share": round(share, 4),
        "source_coverage_per_day": [
            built["coverage_per_day_min"], built["coverage_per_day_max"],
        ],
        "selection_bias_warning": (
            f"Panel này chỉ gồm {balanced}/{total} listing ({share:.1%}) — những "
            "listing CÓ bản ghi khuyến mãi ở cả 20 ngày. Phần thiếu KHÔNG thiếu "
            "ngẫu nhiên. Mọi thống kê trên đây là thống kê của TẬP NÀY, không "
            "phải của thị trường; đừng gọi trung vị ở đây là 'giá trung vị thị "
            "trường'."
        ),
        "not_seasonality": (
            f"{len(dates)} ngày KHÔNG đủ ước lượng mùa vụ tuần — mỗi thứ trong "
            "tuần chỉ có khoảng ba quan sát. Dải này đủ cho một NGHIÊN CỨU SỰ "
            f"KIỆN quanh mốc {CAMPAIGN_DATE}, không đủ cho một mô hình xu hướng."
        ),
    }


def campaign_window(built: dict) -> dict:
    """Giá trước / trong / sau mốc chiến dịch, trên chính panel cân bằng."""
    panel = built["panel"].copy()
    stamp = pd.to_datetime(panel["date"])
    anchor = pd.Timestamp(CAMPAIGN_DATE)
    offset = (stamp - anchor).dt.days
    phase = pd.cut(
        offset,
        bins=[-999, -CAMPAIGN_WINDOW - 1, CAMPAIGN_WINDOW, 999],
        labels=["truoc", "trong", "sau"],
    )
    grouped = panel.assign(phase=phase).groupby("phase", observed=True)
    return {
        str(name): {
            "rows": int(len(group)),
            "median_price": float(group["price"].median()),
            "median_discount_vs_original": float(
                (1 - group["price"] / group["price_original"].replace(0, pd.NA)).median(),
            ),
        }
        for name, group in grouped
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="",
                        help="thư mục chứa product_promotions_*.csv")
    parser.add_argument("--snapshot", default="",
                        help="snapshot_id trong data/raw_snapshots/")
    parser.add_argument("--out", default="artifacts/price_panel.csv")
    parser.add_argument("--meta", default="artifacts/price_panel.json")
    args = parser.parse_args()

    if args.snapshot:
        source = ROOT / "data" / "raw_snapshots" / args.snapshot
    elif args.source:
        source = ROOT / args.source
    else:
        parser.error("cần --snapshot hoặc --source")

    built = build_panel(load_promotions(source))
    meta = describe(built)
    meta["source"] = str(source.relative_to(ROOT))
    meta["campaign_window"] = campaign_window(built)

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    built["panel"].to_csv(out, index=False)
    (ROOT / args.meta).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
