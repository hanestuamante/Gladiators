"""Thị trường và đơn vị tiền — MỘT nơi khai báo, đọc được bằng code.

Vì sao file này tồn tại
=======================

Đo ngày 01/09/2026 trên ``src/gladiators``: mã thị trường ``'vn'``/``'id'`` viết
cứng **97 lần trong 25 file**, đơn vị tiền VND/IDR **79 lần trong 30 file**. Không
có danh sách thị trường tập trung nào — ``COUNTRIES = ("vn", "id")`` chỉ tồn tại
trong một file dashboard, còn ``CATALOG["dim.country"].value_index`` đã khai đúng
hai giá trị đó mà **không chỗ nào đọc**.

Hệ quả không nằm ở số dòng phải sửa. Nó nằm ở chỗ này:

    currency = "VND" if country == "vn" else "IDR"     # analytics/tools.py cũ

Thêm một thị trường thứ ba thì mọi con số của nó được gắn nhãn **IDR** — im lặng,
không lỗi, không cảnh báo. Đó là một mặc định FAIL-OPEN nằm trong một hệ
fail-closed, cùng lớp với ba lỗi đã tìm ra trong hai ngày (cột doanh thu vắng
bảng mật độ, ``.sum()`` trên toàn NaN, macro đi vòng qua cửa mật độ).

Điều file này KHÔNG làm
=======================

Nó **không** xoá 97 chỗ viết cứng — việc đó là một pass riêng. Nó làm một việc
nhỏ hơn và quan trọng hơn: biến "thêm một thị trường" từ một **cuộc săn literal**
thành một **checklist khai báo mà máy đọc được**. Thêm ``'th'`` vào
``dim.country.value_index`` mà quên khai đơn vị tiền hay cách gọi thì
``check_markets_are_fully_declared`` nêu đích danh cái còn thiếu, thay vì để một
câu trả lời mang nhãn sai đi ra ngoài.
"""
from __future__ import annotations


def markets() -> tuple[str, ...]:
    """Các thị trường bản dữ liệu phục vụ, đọc từ CHÍNH catalog.

    Không giữ một bản sao thứ hai: ``dim.country.value_index`` đã là lời khai,
    và hai bản của một sự thật là cách chúng lệch nhau.
    """
    from gladiators.domain.catalog import CATALOG

    return tuple(CATALOG["dim.country"].value_index)


# Đơn vị tiền của từng thị trường. Khai TƯỜNG MINH: không suy từ mã nước, vì một
# quy tắc suy diễn sẽ tự tin gán nhãn cho thị trường nó chưa từng thấy.
CURRENCY_BY_MARKET: dict[str, str] = {
    "vn": "VND",
    "id": "IDR",
}

# Cách gọi một thị trường trong câu hỏi. Trước đây nằm riêng ở
# ``planner.semantic_parser._COUNTRY_SURFACES``; giữ nguyên nội dung, chuyển chỗ
# khai để một thị trường mới thiếu cách gọi thì lộ ra ở đây chứ không lộ ra dưới
# dạng một câu hỏi không nhận ra được thị trường.
SURFACES_BY_MARKET: dict[str, tuple[str, ...]] = {
    "vn": ("việt nam", "viet nam", "vietnam", "vn"),
    "id": ("indonesia", "indo", "id"),
}


class MarketDeclarationError(ValueError):
    """Một thị trường được khai mà thiếu phần đi kèm bắt buộc."""


def currency_of(market: str | None) -> str:
    """Đơn vị tiền của thị trường, hoặc NỔ.

    Fail-closed có chủ đích. Bản cũ (`"VND" if country == "vn" else "IDR"`) trả
    một nhãn cho MỌI đầu vào, kể cả ``None`` và kể cả một thị trường chưa khai —
    và một con số mang sai đơn vị tiền là đúng thứ hệ này tồn tại để chống.
    """
    currency = CURRENCY_BY_MARKET.get(str(market or ""))
    if currency is None:
        raise MarketDeclarationError(
            f"Thị trường {market!r} chưa khai đơn vị tiền trong "
            "domain/markets.CURRENCY_BY_MARKET.",
        )
    return currency


def check_markets_are_fully_declared() -> None:
    """Mọi thị trường của catalog phải có đơn vị tiền VÀ cách gọi.

    Gọi lúc import (xem cuối file) để thiếu khai báo là lỗi KHỞI ĐỘNG, giống hai
    chốt chặn đã có ở catalog (``CatalogError`` khi đơn vị đếm thiếu
    ``counting_key``, ``TopicRegistryError`` khi ref không thuộc topic nào).
    """
    missing: list[str] = []
    for market in markets():
        if market not in CURRENCY_BY_MARKET:
            missing.append(f"{market}: thiếu đơn vị tiền")
        if market not in SURFACES_BY_MARKET:
            missing.append(f"{market}: thiếu cách gọi trong câu hỏi")
    if missing:
        raise MarketDeclarationError(
            "Thị trường khai thiếu phần đi kèm: " + "; ".join(missing),
        )
