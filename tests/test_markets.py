"""Thị trường — MỘT nơi khai, và mọi nơi khác đọc từ đó.

Đo ngày 01/09: mã thị trường viết cứng rải khắp mã nguồn, không có danh sách tập
trung nào, trong khi ``CATALOG["dim.country"].value_index`` đã khai đúng hai giá
trị đó mà không chỗ nào đọc. Hệ quả không nằm ở số dòng phải sửa mà ở hình dạng
lỗi: ``"VND" if country == "vn" else "IDR"`` gán nhãn IDR cho MỌI thị trường
chưa biết — im lặng, không cảnh báo.

Bộ kiểm này khoá ba tính chất, và tính chất thứ ba mới là thứ đắt nhất để mất:

* mọi thị trường của catalog phải khai ĐỦ phần đi kèm — thiếu là lỗi khởi động;
* mỗi tra cứu FAIL-CLOSED — thị trường lạ thì NỔ, không trả một giá trị mặc định;
* thêm một thị trường KHÔNG cần sửa code nhận diện — nó chảy ra từ bảng khai.
"""
from __future__ import annotations

import re

import pytest

from gladiators.domain.markets import (
    AMBIGUOUS_SURFACES,
    CURRENCY_BY_MARKET,
    CURRENCY_MARKERS_BY_MARKET,
    DEFAULT_MARKET,
    DISPLAY_NAME_BY_MARKET,
    SURFACES_BY_MARKET,
    MarketDeclarationError,
    check_markets_are_fully_declared,
    currency_of,
    display_name_of,
    markets,
    surface_pattern,
)


def test_danh_sach_thi_truong_doc_tu_catalog_khong_giu_ban_sao():
    from gladiators.domain.catalog import CATALOG

    assert markets() == tuple(CATALOG["dim.country"].value_index)


def test_moi_thi_truong_khai_du_phan_di_kem():
    check_markets_are_fully_declared()          # không nổ ⇒ đủ
    for market in markets():
        assert market in CURRENCY_BY_MARKET
        assert market in SURFACES_BY_MARKET
        assert market in DISPLAY_NAME_BY_MARKET
        assert market in CURRENCY_MARKERS_BY_MARKET


def test_thi_truong_mac_dinh_phai_co_that():
    assert DEFAULT_MARKET in markets()


@pytest.mark.parametrize("lookup", [currency_of, display_name_of])
def test_tra_cuu_fail_closed(lookup):
    """Thị trường lạ thì NỔ. Bản cũ trả một nhãn cho MỌI đầu vào, kể cả None —
    và một con số mang sai đơn vị tiền là đúng thứ hệ này tồn tại để chống."""
    for market in markets():
        assert lookup(market)
    for unknown in ("th", "sg", "", None):
        with pytest.raises(MarketDeclarationError):
            lookup(unknown)


def test_don_vi_tien_khong_suy_tu_ma_nuoc():
    """Khai tường minh, không suy diễn: một quy tắc suy diễn sẽ tự tin gán nhãn
    cho thị trường nó chưa từng thấy."""
    assert currency_of("vn") == "VND"
    assert currency_of("id") == "IDR"


def test_regex_cach_goi_dung_tu_bang_khai():
    for market in markets():
        pattern = surface_pattern(market)
        for surface in SURFACES_BY_MARKET[market]:
            assert re.search(pattern, f"gia trung vi o {surface} ngay 21/7"), (
                market, surface,
            )


def test_regex_uu_tien_cum_dai():
    """"viet nam" phải thắng "vn" khi cả hai cùng khớp được — nếu không thì cụm
    dài bị cắt và phần dư trở thành rác."""
    match = re.search(surface_pattern("vn"), "gia o viet nam")
    assert match is not None and match.group(1) == "viet nam"


def test_cach_goi_nhap_nhang_duoc_KHAI_chu_khong_doan():
    """`"id"` trùng chữ "id" trong "mã id"/"shop id". Bảng này nói CÁCH GỌI NÀO
    cần luật gỡ nhập nhằng, để một thị trường mới có cùng vấn đề được khai ra
    thay vì lặng lẽ nhận nhầm."""
    assert "id" in AMBIGUOUS_SURFACES
    assert not (AMBIGUOUS_SURFACES & set(SURFACES_BY_MARKET["vn"]))


def test_them_thi_truong_khong_can_sua_ma_nhan_dien(monkeypatch):
    """Tính chất đắt nhất. Bản cũ có ĐÚNG HAI nhánh viết tay trong
    `extract_countries`, nên một thị trường thứ ba khai trong catalog sẽ không
    bao giờ được nhận ra từ câu hỏi — im lặng, và mọi câu về nó rơi vào "thiếu
    country"."""
    from gladiators.agent import entity_extract
    from gladiators.agent.parser import normalize_text
    from gladiators.domain import markets as markets_module

    monkeypatch.setattr(markets_module, "markets", lambda: ("vn", "id", "th"))
    monkeypatch.setitem(
        markets_module.SURFACES_BY_MARKET, "th", ("thai lan", "thailand", "th"),
    )
    question = "Có bao nhiêu listing ở Thái Lan ngày 21/7?"
    assert entity_extract.extract_countries(
        question, normalize_text(question),
    ) == ("th",)


def test_khai_thieu_thi_no_luc_kiem():
    from gladiators.domain import markets as markets_module

    original = dict(markets_module.CURRENCY_BY_MARKET)
    markets_module.CURRENCY_BY_MARKET.pop("id", None)
    try:
        with pytest.raises(MarketDeclarationError, match="thiếu đơn vị tiền"):
            check_markets_are_fully_declared()
    finally:
        markets_module.CURRENCY_BY_MARKET.clear()
        markets_module.CURRENCY_BY_MARKET.update(original)
