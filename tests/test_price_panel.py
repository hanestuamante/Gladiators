"""Bảng giá theo ngày dựng từ ``product_promotions`` — 28/08.

Nguồn của bảng này là một cái bẫy đặt tên. ``products_timeseries`` nghe như chuỗi
thời gian nhưng mỗi listing chỉ xuất hiện **một** ngày; còn ``product_promotions``
nghe như chỉ nói về khuyến mãi lại là bảng giá theo ngày duy nhất có thật.

Điều bộ test này khoá lại: **bảng phải cân bằng, và nó phải tự khai mình lệch.**
Một panel không mang theo tỷ lệ phủ của chính nó sẽ được dùng như thể nó phủ
100%, và cảnh báo nằm ở file khác thì không ai đọc.

Dữ liệu tổng hợp, không đọc ``data/raw_snapshots/`` — thư mục đó bị gitignore nên
một test phụ thuộc nó sẽ đỏ trên mọi máy khác.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_price_panel import (  # noqa: E402
    build_panel,
    campaign_window,
    describe,
    load_promotions,
)

DATES = [f"2026-07-{day:02d}" for day in range(1, 6)]


def _promotions() -> pd.DataFrame:
    """Ba listing: một đủ 5 ngày, một thiếu 1 ngày, một chỉ có 1 ngày."""
    rows = []
    plans = {"full": DATES, "partial": DATES[:4], "sparse": DATES[:1]}
    for item_id, days in plans.items():
        for index, date in enumerate(days):
            rows.append({
                "country_code": "vn", "shop_id": 1, "item_id": item_id,
                "date": date, "price": 100 + index,
                "price_original": 200, "price_before_promo": 150,
                "promotion_id": 1, "promotion_type": 301,
            })
    # Cùng listing, cùng ngày, hai dòng khuyến mãi — giá thấp hơn là giá người
    # mua thật sự trả, nên nó phải thắng.
    rows.append({
        "country_code": "vn", "shop_id": 1, "item_id": "full",
        "date": DATES[0], "price": 50, "price_original": 200,
        "price_before_promo": 150, "promotion_id": 2, "promotion_type": 201,
    })
    return pd.DataFrame(rows)


def test_the_panel_keeps_only_listings_present_on_every_day():
    built = build_panel(_promotions())
    assert built["total_listings"] == 3
    assert built["balanced_listings"] == 1
    assert set(built["panel"]["item_id"]) == {"full"}


def test_one_row_per_listing_per_day_and_the_lowest_price_wins():
    """Nhiều dòng khuyến mãi cùng ngày ⇒ giữ giá THẤP NHẤT. Giữ cả hai sẽ đếm
    trùng một listing trong mọi phép thống kê theo ngày."""
    panel = build_panel(_promotions())["panel"]
    assert len(panel) == len(DATES)
    assert not panel.duplicated(subset=["country_code", "shop_id", "item_id", "date"]).any()
    assert float(panel.loc[panel.date == DATES[0], "price"].iloc[0]) == 50.0


def test_the_metadata_states_its_own_selection_bias():
    meta = describe(build_panel(_promotions()))
    assert meta["listings_balanced"] == 1
    assert meta["listings_total"] == 3
    assert meta["balanced_share"] == pytest.approx(1 / 3, abs=1e-4)
    # Cảnh báo phải NẰM TRONG metadata, không nằm trong một tài liệu khác.
    assert "KHÔNG thiếu ngẫu nhiên" in meta["selection_bias_warning"]
    assert "giá trung vị thị trường" in meta["selection_bias_warning"]


def test_the_metadata_refuses_to_be_read_as_seasonality():
    """20 ngày là ba tuần; mỗi thứ trong tuần chỉ có khoảng ba quan sát."""
    meta = describe(build_panel(_promotions()))
    assert "mùa vụ" in meta["not_seasonality"]
    assert "NGHIÊN CỨU SỰ KIỆN" in meta["not_seasonality"]


def test_the_campaign_window_splits_before_during_and_after():
    window = campaign_window(build_panel(_promotions()))
    assert set(window) <= {"truoc", "trong", "sau"}
    assert all(bucket["rows"] > 0 for bucket in window.values())
    assert all("median_price" in bucket for bucket in window.values())


def test_a_missing_source_fails_loudly(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_promotions(tmp_path)


def test_products_timeseries_is_not_a_time_series():
    """Khoá lại chính phát hiện dẫn tới script này.

    Chạy khi có dữ liệu thật; bỏ qua khi không, vì thư mục đó bị gitignore. Một
    test im lặng bỏ qua vẫn tốt hơn một test đỏ vì thiếu file — nhưng nó phải
    NÓI RÕ là đã bỏ qua, chứ không tính là đạt.
    """
    candidates = sorted(
        Path("data/raw_snapshots").glob("**/products_timeseries_*.csv"),
    ) if Path("data/raw_snapshots").is_dir() else []
    if not candidates:
        pytest.skip("chưa nhận đợt raw nào có products_timeseries")

    frame = pd.read_csv(candidates[0], low_memory=False)
    per_listing = frame.groupby(["country_code", "shop_id", "item_id"]).date.nunique()
    assert (per_listing == 1).all(), (
        "products_timeseries giờ CÓ nhiều ngày mỗi listing — bẫy đặt tên đã hết, "
        "và build_price_panel nên đọc thẳng từ đó"
    )
