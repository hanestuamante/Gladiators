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


# Tên hiển thị cho người đọc. Khai ở đây vì nó hỏng theo ĐÚNG hình dạng của lỗi
# tiền tệ: `"Việt Nam" if country == "vn" else "Indonesia"` gán "Indonesia" cho
# mọi thị trường không phải vn, im lặng.
DISPLAY_NAME_BY_MARKET: dict[str, str] = {
    "vn": "Việt Nam",
    "id": "Indonesia",
}


# Từ chỉ ĐƠN VỊ TIỀN trong câu hỏi. Trước đây nằm ở
# ``planner.semantic_parser._CURRENCY_MARKERS`` — tức từ vựng tiền tệ của một
# thị trường sống tách khỏi mã tiền tệ của chính nó, ở hai file. Chuyển về đây
# để thêm một thị trường là sửa MỘT khối.
CURRENCY_MARKERS_BY_MARKET: dict[str, tuple[str, ...]] = {
    "vn": ("dong", "đồng", "vnd", "vnđ"),
    "id": ("rupiah", "idr", "rp"),
}


# Cách gọi TRÙNG một từ thường, nên gặp nó chưa đủ để kết luận câu đang nói về
# thị trường. `"id"` là ví dụ duy nhất hiện có: nó cũng là chữ "id" trong "mã
# id", "shop id", "promotion id". `entity_extract` giữ luật gỡ nhập nhằng; bảng
# này chỉ nói CÁCH GỌI NÀO cần luật đó, để một thị trường mới có cùng vấn đề
# được khai ra thay vì lặng lẽ nhận nhầm.
AMBIGUOUS_SURFACES: frozenset[str] = frozenset({"id"})

# Thị trường MẶC ĐỊNH khi câu hỏi không nêu. Khai tường minh vì `or "vn"` rải
# rác là một lựa chọn ngầm: đổi thị trường chính thì phải tìm lại từng chỗ.
DEFAULT_MARKET: str = "vn"


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


def display_name_of(market: str | None) -> str:
    """Tên hiển thị của thị trường, hoặc NỔ. Cùng lý do với ``currency_of``."""
    name = DISPLAY_NAME_BY_MARKET.get(str(market or ""))
    if name is None:
        raise MarketDeclarationError(
            f"Thị trường {market!r} chưa khai tên hiển thị trong "
            "domain/markets.DISPLAY_NAME_BY_MARKET.",
        )
    return name


def surface_pattern(market: str) -> str:
    """Regex khớp mọi cách gọi của một thị trường, dựng TỪ bảng khai.

    Dùng cho ``entity_extract``: bản cũ viết cứng ``r"\b(viet nam|vietnam|vn)\b"``
    — một bản sao thứ hai của cùng danh sách, và hai bản của một sự thật là
    cách chúng lệch nhau.
    """
    import re as _re

    surfaces = SURFACES_BY_MARKET.get(market)
    if not surfaces:
        raise MarketDeclarationError(
            f"Thị trường {market!r} chưa khai cách gọi trong câu hỏi.",
        )
    # Dài trước: "viet nam" phải thắng "vn" khi cả hai cùng khớp được.
    ordered = sorted(surfaces, key=len, reverse=True)
    return r"\b(" + "|".join(_re.escape(s) for s in ordered) + r")\b"


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
        if market not in DISPLAY_NAME_BY_MARKET:
            missing.append(f"{market}: thiếu tên hiển thị")
        if market not in CURRENCY_MARKERS_BY_MARKET:
            missing.append(f"{market}: thiếu từ chỉ đơn vị tiền")
    if DEFAULT_MARKET not in markets():
        missing.append(f"thị trường mặc định {DEFAULT_MARKET!r} không có trong catalog")
    if missing:
        raise MarketDeclarationError(
            "Thị trường khai thiếu phần đi kèm: " + "; ".join(missing),
        )
