"""Adapter dump Postgres → layout raw canonical.

Kiểm HÀNH VI, không kiểm cấu trúc: một adapter nối sai vẫn sinh ra đúng số file,
đúng tên cột, đúng kiểu. Thứ phân biệt được nối đúng với nối sai là bộ đóng băng
— ba ngày chồng lấn phải tái lập ĐÚNG số listing và ĐÚNG giá tới từng đồng.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from gladiators.data.extract_adapter import (
    IDENTITY_COLUMNS,
    UNAVAILABLE_COLUMNS,
    ExtractAdapterError,
    _to_epoch,
    _to_iso,
    adapt_extract,
)
from gladiators.data.pipeline import run_pipeline

REPO = Path(__file__).resolve().parents[1]
DUMP = REPO / "raw_extra_data" / "datashopee"
FROZEN = REPO / "data" / "processed"

pytestmark = pytest.mark.skipif(not DUMP.exists(), reason="dump không có trong cây làm việc")


@pytest.fixture(scope="module")
def adapted(tmp_path_factory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("adapt")
    raw, processed = root / "raw", root / "processed"
    adapt_extract(DUMP, raw)
    run_pipeline(raw, processed)
    return raw, processed


# --- bước nối --------------------------------------------------------------


def test_the_three_overlapping_days_reproduce_the_frozen_dataset(adapted):
    """Bằng chứng mạnh nhất có thể có rằng promotions là panel nguồn.

    Nếu adapter nối nhầm bảng, nhầm khoá, hay nhầm ngày, ba ngày này sẽ lệch.
    Chúng khớp tới từng đồng là thứ không thể xảy ra do may mắn.
    """
    _, processed = adapted
    new = pd.read_csv(processed / "products_clean.csv", low_memory=False)
    old = pd.read_csv(FROZEN / "products_clean.csv", low_memory=False)
    for date in ("2026-07-01", "2026-07-02", "2026-07-03"):
        n = new[new.date.astype(str) == date].drop_duplicates("product_listing_key")
        o = old[old.date.astype(str) == date].drop_duplicates("product_listing_key")
        assert len(n) == len(o) > 0, date
        joined = o[["product_listing_key", "price_num"]].merge(
            n[["product_listing_key", "price_num"]],
            on="product_listing_key", suffixes=("_o", "_n"),
        )
        assert len(joined) == len(o), f"{date}: listing key không khớp"
        assert (joined.price_num_o - joined.price_num_n).abs().lt(0.01).all(), date


def test_the_new_schema_is_a_strict_superset_of_the_frozen_one(adapted):
    """Cột CŨ không được biến mất: một cột rơi mất trông giống hệt một cột chưa
    từng có, và mọi câu hỏi dựa vào nó chuyển sang 'không hỗ trợ' trong im lặng."""
    _, processed = adapted
    new = pd.read_csv(processed / "products_clean.csv", nrows=1)
    old = pd.read_csv(FROZEN / "products_clean.csv", nrows=1)
    assert not set(old.columns) - set(new.columns)


def test_category_columns_are_carried_not_blanked(adapted):
    """``catid``/``global_catids`` từng ra RỖNG 100% vì hai cột nguồn không nằm
    trong IDENTITY_COLUMNS nên nhánh ánh xạ im lặng rơi vào ``else``. Cột trống
    là hợp lệ về kiểu, nên pipeline vẫn xanh — chỉ hành vi mới bắt được."""
    _, processed = adapted
    new = pd.read_csv(processed / "products_clean.csv", low_memory=False)
    assert new.catid_num.notna().all()
    assert new.global_catids_count.notna().all()
    assert {"shopee_category_id", "global_category_id"} <= set(IDENTITY_COLUMNS)


def test_timestamps_are_written_as_epoch_seconds_like_the_frozen_set(adapted):
    """Dump ghi thời gian dạng chữ, bộ cũ dùng epoch, pipeline khai chúng là cột
    SỐ. Không đổi đơn vị thì mỗi dòng sinh một INVALID_NUMBER và cột số ra null."""
    _, processed = adapted
    new = pd.read_csv(processed / "products_clean.csv", low_memory=False)
    assert new.ctime_num.notna().all()
    # Neo vào chính dải của bộ đóng băng thay vì một hằng số tự chọn: hai bộ mô
    # tả cùng một sàn, nên độ lớn phải cùng bậc. Lệch đơn vị 1000 lần (ns/us/ms)
    # đẩy giá trị ra ngoài dải này ngay lập tức.
    old = pd.read_csv(FROZEN / "products_clean.csv", low_memory=False)
    low, high = old.ctime_num.min(), old.ctime_num.max()
    span = high - low
    assert new.ctime_num.between(low - span, high + span).all()


def test_empty_timestamps_stay_empty_rather_than_becoming_nan_text():
    assert list(_to_epoch(pd.Series(["2026-07-03 00:00:00.000 +0700", ""]))) == \
        ["1783011600", ""]
    assert list(_to_iso(pd.Series(["2023-11-08 14:33:05.000 +0700", ""]))) == \
        ["2023-11-08T07:33:05+00:00", ""]


# --- chỗ KHÔNG được bịa ----------------------------------------------------


def test_point_in_time_attributes_are_written_only_at_their_observed_date(adapted):
    """Dump có ĐÚNG một quan sát rating/liked/monthly_sold mỗi item. Gắn nó cho
    cả 20 ngày sẽ dựng ra một chuỗi thời gian PHẲNG không có thật — "không đo
    được" đội lốt "đo được và không đổi" (CLAUDE.md §3.1)."""
    _, processed = adapted
    new = pd.read_csv(processed / "products_clean.csv", low_memory=False)
    observed = new[new.attributes_observed.astype(str).str.lower() == "true"]
    unobserved = new[new.attributes_observed.astype(str).str.lower() != "true"]

    assert len(observed) == new.product_listing_key.nunique(), "phải đúng 1 ngày/item"
    assert observed.rating_num.notna().any()
    # Ngoài ngày quan sát: TRỐNG, không phải 0.
    for column in ("rating_num", "liked_count_num", "rating_count_num"):
        assert unobserved[column].isna().all(), column


def test_columns_the_dump_cannot_supply_are_blank_with_a_recorded_reason(adapted):
    """Một cột trống không kèm lời giải thích là một cột không ai biết nên chờ
    dữ liệu hay chờ code."""
    raw, processed = adapted
    report = json.loads((raw / "ADAPT_REPORT.json").read_text(encoding="utf-8"))
    assert set(report["unavailable_columns"]) == set(UNAVAILABLE_COLUMNS)
    assert all(reason.strip() for reason in report["unavailable_columns"].values())
    new = pd.read_csv(processed / "products_clean.csv", low_memory=False)
    # ``shopee_verified`` đổi GRAIN (listing → shop): hai đại lượng khác nhau
    # mang một cái tên, ánh xạ cái này thành cái kia là bịa.
    assert new.shopee_verified_bool.isna().all()


def test_the_borrowed_values_are_declared_as_borrowed(adapted):
    raw, _ = adapted
    report = json.loads((raw / "ADAPT_REPORT.json").read_text(encoding="utf-8"))
    assert set(report["borrowed_from_reference"]) == {"brand", "category_platform"}
    # Brand chỉ gán khi tra được; brand_id lạ để TRỐNG, không đoán.
    assert report["brand"]["unmapped"] > 0
    assert report["brand"]["mapped"] > report["brand"]["unmapped"]


# --- grain: tách, không đổi ------------------------------------------------


def test_shop_info_keeps_the_old_grain_and_the_panel_goes_to_shop_stats(adapted):
    """Chín measure ``measure.shop_*`` đọc ``shop_info`` với ngữ nghĩa
    static_latest. Để panel 20 ngày chảy vào đó thì mọi join theo shop nở gấp 20
    lần và chín measure âm thầm đổi nghĩa."""
    _, processed = adapted
    shops = pd.read_csv(processed / "shop_info_clean.csv", low_memory=False)
    assert not shops.duplicated(["country_code", "shop_id"]).any()
    assert shops.date.nunique() == 1

    stats = pd.read_csv(processed / "shop_stats_clean.csv", low_memory=False)
    assert stats.date.nunique() > 1
    assert not stats.duplicated(["country_code", "shop_id", "date"]).any()
    assert stats.rating_star_num.notna().all()


def test_the_shelf_snapshot_is_not_replicated_across_days(adapted):
    """``categories`` của dump KHÔNG mang ngày, còn kệ hàng bộ cũ đo được là ĐỔI
    theo ngày. Gán một ảnh chụp cho mọi ngày là dựng ra lịch sử không có thật."""
    _, processed = adapted
    shelf = pd.read_csv(processed / "category_list_clean.csv", low_memory=False)
    assert shelf.date.nunique() == 1


def test_the_load_step_refuses_two_files_with_the_same_table_prefix(tmp_path):
    """``glob("products_*")`` bắt luôn ``products_timeseries_*`` — hai bảng hình
    dạng khác hẳn nhau, nhận nhầm là nối sai toàn bộ panel."""
    (tmp_path / "products_202601011200.csv").write_text("a\n1\n", encoding="utf-8")
    (tmp_path / "products_202601011300.csv").write_text("a\n1\n", encoding="utf-8")
    with pytest.raises(ExtractAdapterError, match="cùng tiền tố"):
        adapt_extract(tmp_path, tmp_path / "out")


def test_the_pipeline_reports_no_errors_on_the_adapted_layout(adapted):
    """Cảnh báo thì có (và mỗi cái có nguyên nhân đã ghi); LỖI thì không."""
    _, processed = adapted
    issues = pd.read_csv(processed / "data_quality_issues.csv", low_memory=False)
    errors = issues[issues.severity == "error"]
    assert errors.empty, sorted(errors.code.unique())
