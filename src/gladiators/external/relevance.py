"""Deterministic relevance pre-filter cho Phase 6 (không LLM).

P6 extraction tốn một LLM call bounded cho MỖI result item. Kết quả rõ ràng lạc đề
(một vé máy bay giảm giá, một bài Prime Day không liên quan) nên bị loại TRƯỚC call
đó, rẻ và deterministic, để budget LLM chỉ dành cho snippet có khả năng liên quan.

Gate cố ý BẢO THỦ: drop nhầm một hit thật làm mất external evidence, trong khi giữ
nhầm một item mơ hồ chỉ tốn đúng một LLM call mà admission sẽ loại sau. Vì bất đối
xứng chi phí đó, gate chỉ loại item gần như không chia sẻ gì với nội dung đặc trưng
của query — đo bằng số token đặc trưng trùng nhau, bỏ qua từ thương mại chung chung.
"""
from __future__ import annotations

import re
import unicodedata

from .search_contracts import SearchQuery, SearchResultItem

# Campaign/theme day anchor: 7.7, 9.9, 11.11, 12.12 — tín hiệu đặc trưng nhất.
_ANCHOR = re.compile(r"\b\d{1,2}\.\d{1,2}\b")
_WORD = re.compile(r"[a-z0-9]+")

# Từ thương mại/boilerplate KHÔNG đặc trưng khi đứng một mình: có mặt ở cả query
# lẫn phần lớn kết quả rác nên không dùng để phân biệt liên quan hay không.
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "date", "dates", "shopping", "ecommerce",
    "commerce", "online", "sale", "sales", "deal", "deals", "campaign", "event",
    "market", "2023", "2024", "2025", "2026", "2027", "news", "best", "top", "guide",
})

# Market code -> tên đầy đủ để so khớp với văn bản kết quả (thường viết đủ chữ).
_MARKET_SYNONYMS = {
    "vn": ("vietnam", "vietnamese"),
    "id": ("indonesia", "indonesian"),
    "global": (),
}

# Chỉ cần chia sẻ 1 token đặc trưng là giữ. Ngưỡng cao hơn từng drop nhầm hit thật
# chỉ trùng đúng anchor "7.7" (không nhắc lại tên market trong snippet). Ngưỡng 1 =
# "chia sẻ hầu như không gì mới loại" — cắt rác rõ ràng, không đụng hit hợp lệ.
_MIN_OVERLAP = 1


def _fold(value: str) -> str:
    value = value.lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")


def _tokens(text: str) -> set[str]:
    folded = _fold(text)
    anchors = set(_ANCHOR.findall(folded))
    words = {w for w in _WORD.findall(folded) if len(w) >= 4 and w not in _STOPWORDS}
    return anchors | words


def query_signal_tokens(query: SearchQuery) -> set[str]:
    """Token đặc trưng của query = anchor + từ riêng (len>=4, bỏ stopword) + tên market."""
    tokens = _tokens(query.query)
    tokens.update(_MARKET_SYNONYMS.get(query.market, ()))
    return tokens


def is_relevant(query: SearchQuery, item: SearchResultItem) -> bool:
    """True nếu item chia sẻ đủ token đặc trưng với query để đáng chạy P6.

    Fail-open khi query quá ít token đặc trưng (không đủ cơ sở để loại) — để P6 và
    admission quyết định thay vì im lặng bỏ qua.
    """
    signal = query_signal_tokens(query)
    if not signal:
        return True
    item_tokens = _tokens(f"{item.title} {item.snippet}")
    return len(signal & item_tokens) >= _MIN_OVERLAP
