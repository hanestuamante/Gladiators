"""Thị trường và đơn vị tiền — MỘT nơi khai, và thiếu khai là lỗi khởi động.

Đo ngày 01/09/2026: mã thị trường viết cứng 97 lần/25 file, tiền tệ 79 lần/30
file, và không danh sách tập trung nào — trong khi
``CATALOG["dim.country"].value_index`` đã khai đúng hai giá trị mà không ai đọc.

Bộ test này KHÔNG khoá 97 chỗ đó (việc riêng). Nó khoá thứ quan trọng hơn: thêm
một thị trường mà quên phần đi kèm phải NỔ, chứ không được ra một câu trả lời
mang nhãn tiền tệ sai.
"""
from __future__ import annotations

import pytest

from gladiators.domain.markets import (
    CURRENCY_BY_MARKET,
    SURFACES_BY_MARKET,
    MarketDeclarationError,
    check_markets_are_fully_declared,
    currency_of,
    markets,
)


def test_danh_sach_thi_truong_doc_tu_catalog_khong_giu_ban_sao():
    """Hai bản của một sự thật là cách chúng lệch nhau."""
    from gladiators.domain.catalog import CATALOG

    assert markets() == tuple(CATALOG["dim.country"].value_index)


def test_moi_thi_truong_deu_khai_du_tien_te_va_cach_goi():
    check_markets_are_fully_declared()          # không nổ là điều kiện đạt


@pytest.mark.parametrize("market,currency", [("vn", "VND"), ("id", "IDR")])
def test_tien_te_tra_bang_khai(market, currency):
    assert currency_of(market) == currency


@pytest.mark.parametrize("unknown", ["th", "sg", "", None])
def test_thi_truong_chua_khai_thi_NO_chu_khong_doan(unknown):
    """Bản cũ là `"VND" if country == "vn" else "IDR"` — nó gán IDR cho MỌI
    thứ không phải vn, kể cả `None` và kể cả một thị trường chưa ai khai. Một
    con số mang sai đơn vị tiền là đúng thứ hệ này tồn tại để chống."""
    with pytest.raises(MarketDeclarationError):
        currency_of(unknown)


def test_cach_goi_va_tien_te_phu_cung_mot_tap_thi_truong():
    assert set(CURRENCY_BY_MARKET) >= set(markets())
    assert set(SURFACES_BY_MARKET) >= set(markets())
