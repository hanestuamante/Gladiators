"""Deterministic capability router for Phase 6 external-data requests.

Routing is intentionally outside the LLM.  The model may formulate bounded
queries only after this module has selected the capability and market scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
import re
import unicodedata


RouteMode = Literal["internal_only", "external_only", "hybrid", "clarify", "abstain"]


@dataclass(frozen=True)
class ExternalRoute:
    mode: RouteMode
    rule_id: str
    reason: str
    purpose: Literal["campaign_context", "market_event", "product_external_info"] | None = None
    market: Literal["vn", "id", "global"] = "global"
    requested_variables: tuple[str, ...] = ()


_COMPARE = (
    "so sanh", "cao hon", "thap hon", "lon hon", "re hon", "dat hon",
    "compare", "higher", "lower", "cheaper", "lebih tinggi", "lebih murah",
    "cong", "tong", "sum", "total",
)
_CONVERT = ("quy doi", "convert", "conversion", "sang usd", "to usd")
_VN = (" vietnam ", " viet nam ", " vn ", " vnd ")
_ID = (" indonesia ", " id ", " idr ")
# W8.4: nhận theo CẤU TRÚC, không theo cụm liền nhau. "Giá CỦA đối thủ NGOÀI
# SÀN" chen từ vào giữa và rơi qua danh sách phrase cũ, rồi nhận nhãn currency —
# một lời từ chối mô tả sai vấn đề.
_PRICE_CONCEPT = ("gia", "price", "harga")
_COMPETITOR_CONCEPT = ("doi thu", "pesaing", "competitor")
# Chỉ dấu hiệu VỊ TRÍ ngoài sàn mới đủ nói "external" một mình cạnh giá —
# "đối thủ" trần còn nghĩa trong-sàn ("đối thủ có cùng mức giá ±20%" của tc19
# là một câu SIMILARITY, và gán nó nhãn external là một lời từ chối sai vấn đề).
_EXTERNAL_LOCATION = (
    "ngoai san", "ben ngoai", "outside platform", "external marketplace",
    "market price", "external price", "ngoai nen tang", "off platform",
    "luar platform",
)
_CLAUSE_SPLIT = (";", ",", " va ", " and ", " nhung ", " but ", " roi ")


def _is_external_competitor_price(normalized: str) -> bool:
    """External khi cùng MỘT mệnh đề có khái niệm giá và (a) một dấu hiệu vị
    trí ngoài sàn, hoặc (b) dạng sở hữu "giá (của) đối thủ" — giá đứng LIỀN
    trước đối thủ trong vòng ba token. Tách mệnh đề theo dấu câu/liên từ mạnh.
    """
    clauses = [f" {normalized} "]
    for separator in _CLAUSE_SPLIT:
        clauses = [part for clause in clauses for part in clause.split(separator)]
    for clause in clauses:
        padded = f" {clause.strip()} "
        if not any(term in padded for term in _PRICE_CONCEPT):
            continue
        if any(term in padded for term in _EXTERNAL_LOCATION):
            return True
        tokens = padded.split()
        for index, token in enumerate(tokens):
            if token not in _PRICE_CONCEPT:
                continue
            # "giá (của) đối thủ" — sở hữu, giá đứng TRƯỚC; và dạng tiếng Anh
            # "competitor price" — đối thủ đứng NGAY trước giá.
            forward = " ".join(tokens[index + 1: index + 4])
            backward = " ".join(tokens[max(0, index - 2): index])
            if any(f" {term}" in f" {forward}" for term in _COMPETITOR_CONCEPT):
                return True
            if any(backward.endswith(term) for term in _COMPETITOR_CONCEPT):
                return True
    return False
_CAMPAIGN = (
    "lich 7.7", "7.7", "lich chien dich", "lich khuyen mai", "campaign calendar",
    "campaign date", "campaign window", "ngay chien dich", "chien dich mua sam",
    "shopping campaign", "jadwal kampanye",
)
_MARKET_EVENT = (
    "su kien thi truong", "market event", "ngay le", "theme day",
    "shopping festival", "le hoi mua sam", "hari belanja",
)


def _contains(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _normalize_text(value: str) -> str:
    value = value.lower().replace("đ", "d")
    value = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s:/._-]", " ", value)).strip()


def _requested_internal_variables(text: str) -> tuple[str, ...]:
    variables = []
    for name, terms in (
        ("revenue_proxy", ("doanh thu", "revenue", "pendapatan")),
        ("price", ("gia noi bo", "gia thay doi", "bien dong gia", "price change", "harga")),
        ("listing_count", ("bao nhieu listing", "listing", "san pham", "produk")),
        ("monthly_sold", ("luot ban", "doanh so", "monthly sold", "penjualan")),
        ("voucher_observation", ("voucher", "hieu qua khuyen mai", "promotion effectiveness")),
        ("shop_metric", ("shop nao", "cua hang", "toko")),
    ):
        if _contains(text, terms):
            variables.append(name)
    return tuple(variables)


def classify_external_need(text: str) -> ExternalRoute:
    """Map a question to a capability using machine-checkable lexical rules."""
    normalized = f" {_normalize_text(text)} "
    has_vn = _contains(normalized, _VN)
    has_id = _contains(normalized, _ID)
    monetary = _contains(normalized, ("gia", "price", "revenue", "doanh thu", "vnd", "idr", "usd"))
    cross_market = has_vn and has_id and monetary and _contains(normalized, _COMPARE)
    currency_conversion = monetary and _contains(normalized, _CONVERT) and _contains(
        normalized, (" usd ", " dollar ", " vnd ", " idr "),
    )
    if cross_market or currency_conversion:
        return ExternalRoute(
            mode="clarify", rule_id="A16-CROSS-CURRENCY",
            reason=(
                "Không thể cộng, quy đổi hoặc kết luận hơn-kém giữa VND và IDR: "
                "contract cross-tier derived value T-8c chưa được phê duyệt."
            ),
        )
    if _is_external_competitor_price(normalized):
        return ExternalRoute(
            mode="abstain", rule_id="A14-EXT",
            reason=(
                "Câu hỏi cần nguồn giá đối thủ/external đã được governance phê duyệt; "
                "capability `sources.external.enabled` hiện chưa bật."
            ), purpose="product_external_info",
            market="id" if has_id else "vn" if has_vn else "global",
            requested_variables=("competitor_price",),
        )
    internal_variables = _requested_internal_variables(normalized)
    if _contains(normalized, _CAMPAIGN):
        return ExternalRoute(
            mode="hybrid" if internal_variables else "external_only",
            rule_id="A14-HYBRID" if internal_variables else "A14-LIVE",
            reason="Câu hỏi cần lịch chiến dịch cập nhật.",
            purpose="campaign_context", market="id" if has_id else "vn" if has_vn else "global",
            requested_variables=(*internal_variables, "campaign_context"),
        )
    if _contains(normalized, _MARKET_EVENT):
        return ExternalRoute(
            mode="hybrid" if internal_variables else "external_only",
            rule_id="A14-HYBRID" if internal_variables else "A14-LIVE",
            reason="Câu hỏi cần bối cảnh sự kiện thị trường cập nhật.",
            purpose="market_event", market="id" if has_id else "vn" if has_vn else "global",
            requested_variables=(*internal_variables, "market_event"),
        )
    return ExternalRoute(
        mode="internal_only", rule_id="A14-INTERNAL", reason="Dataset nội bộ đủ để định tuyến.",
        requested_variables=internal_variables,
    )
