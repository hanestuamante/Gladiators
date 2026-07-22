"""Deterministic capability router for Phase 6 external-data requests.

Routing is intentionally outside the LLM.  The model may formulate bounded
queries only after this module has selected the capability and market scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gladiators.agent.parser import normalize_text


RouteMode = Literal["internal_only", "live_search", "clarify", "abstain"]


@dataclass(frozen=True)
class ExternalRoute:
    mode: RouteMode
    rule_id: str
    reason: str
    purpose: Literal["campaign_context", "market_event", "product_external_info"] | None = None
    market: Literal["vn", "id", "global"] = "global"


_COMPARE = (
    "so sanh", "cao hon", "thap hon", "lon hon", "re hon", "dat hon",
    "compare", "higher", "lower", "cheaper", "lebih tinggi", "lebih murah",
    "quy doi", "convert", "conversion", "usd", "dollar",
)
_VN = (" vietnam ", " viet nam ", " vn ", " vnd ")
_ID = (" indonesia ", " id ", " idr ")
_COMPETITOR = (
    "gia doi thu", "competitor price", "market price", "harga pesaing",
    "gia ben ngoai", "external price",
)
_CAMPAIGN = (
    "lich 7.7", "7.7", "lich chien dich", "lich khuyen mai", "campaign calendar",
    "campaign date", "campaign window", "ngay chien dich", "jadwal kampanye",
)
_MARKET_EVENT = (
    "su kien thi truong", "market event", "ngay le", "theme day",
    "shopping festival", "le hoi mua sam", "hari belanja",
)


def _contains(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def classify_external_need(text: str) -> ExternalRoute:
    """Map a question to a capability using machine-checkable lexical rules."""
    normalized = f" {normalize_text(text)} "
    has_vn = _contains(normalized, _VN)
    has_id = _contains(normalized, _ID)
    monetary = _contains(normalized, ("gia", "price", "revenue", "doanh thu", "vnd", "idr", "usd"))
    if has_vn and has_id and monetary and _contains(normalized, _COMPARE):
        return ExternalRoute(
            mode="clarify", rule_id="A16-CROSS-CURRENCY",
            reason=(
                "Không thể cộng, quy đổi hoặc kết luận hơn-kém giữa VND và IDR: "
                "contract cross-tier derived value T-8c chưa được phê duyệt."
            ),
        )
    if _contains(normalized, _COMPETITOR):
        return ExternalRoute(
            mode="abstain", rule_id="A14-EXT",
            reason=(
                "Câu hỏi cần nguồn giá đối thủ/external đã được governance phê duyệt; "
                "capability `sources.external.enabled` hiện chưa bật."
            ), purpose="product_external_info",
            market="id" if has_id else "vn" if has_vn else "global",
        )
    if _contains(normalized, _CAMPAIGN):
        return ExternalRoute(
            mode="live_search", rule_id="A14-LIVE", reason="Câu hỏi cần lịch chiến dịch cập nhật.",
            purpose="campaign_context", market="id" if has_id else "vn" if has_vn else "global",
        )
    if _contains(normalized, _MARKET_EVENT):
        return ExternalRoute(
            mode="live_search", rule_id="A14-LIVE", reason="Câu hỏi cần bối cảnh sự kiện thị trường cập nhật.",
            purpose="market_event", market="id" if has_id else "vn" if has_vn else "global",
        )
    return ExternalRoute(mode="internal_only", rule_id="A14-INTERNAL", reason="Dataset nội bộ đủ để định tuyến.")
