"""P5 bounded live-search planner; no tool access and one schema repair."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from typing import Callable

from pydantic import ValidationError

from .search_contracts import LiveSearchPlan


class SearchPlanningError(RuntimeError):
    pass


# Tên marketplace là tín hiệu truy hồi MẠNH NHẤT cho câu hỏi lịch chiến dịch.
# Đo trực tiếp trên Tavily (26/07), cùng câu hỏi 7.7 Indonesia:
#   "7.7 marketplace promotion Indonesia schedule"       → score 0.03–0.09, toàn rác
#     (tên lửa KHAN, hợp đồng UFC, visa Quý Châu, Walmart Mexico)
#   "Shopee Tokopedia Indonesia 7.7 ecommerce shopping…" → score 0.54–0.87, đúng chủ đề
# Query hợp lệ theo validator vẫn có thể lấy về rác; thiếu tên sàn mới là nguyên nhân.
# Map này là nguồn sự thật duy nhất: vừa đưa vào constraints cho P5, vừa dùng cho
# deterministic fallback, để hai đường không lệch nhau.
MARKETPLACES: dict[str, tuple[str, ...]] = {
    "vn": ("Shopee", "Lazada", "TikTok Shop"),
    "id": ("Shopee", "Tokopedia", "Lazada"),
    "global": ("Shopee", "Lazada"),
}

_MARKET_NAMES = {"id": "Indonesia", "vn": "Vietnam", "global": "Southeast Asia"}

# Qualifier mà campaign query BẮT BUỘC phải có. Trước đây tuple này chỉ nằm inline
# trong nhánh validate nên prompt P5 không hề biết — model không có cách nào đoán
# đúng và luôn fail hai vòng repair rồi rơi xuống fallback.
_CAMPAIGN_QUALIFIERS: tuple[str, ...] = (
    "campaign", "shopping", "sale", "ecommerce", "e-commerce", "promotion",
    "marketplace", "shopee", "tokopedia", "traveloka", "lazada",
)


class LiveSearchPlanner:
    def __init__(
        self, llm_client, *, max_queries: int = 3,
        clock: Callable[[], datetime] | None = None,
    ):
        self.llm_client = llm_client
        if not 1 <= max_queries <= 3:
            raise ValueError("P5 max_queries phải nằm trong [1, 3].")
        self.max_queries = max_queries
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _deterministic_fallback(
        question: str, *, purpose: str, market: str, mode: str, as_of_date: str,
    ) -> LiveSearchPlan | None:
        """Safe fallback for the two approved context purposes; never embeds raw text."""
        market_name = _MARKET_NAMES.get(market)
        if market_name is None or purpose not in {"campaign_context", "market_event"}:
            return None
        year = as_of_date[:4]
        # Hai sàn lớn nhất của market — đủ để neo chủ đề, không dài tới mức
        # loãng query (max_query_chars = 200).
        sellers = " ".join(MARKETPLACES.get(market, ())[:2])
        prefix = f"{sellers} " if sellers else ""
        if purpose == "campaign_context":
            match = re.search(r"(?<!\d)(\d{1,2}\.\d{1,2})(?!\d)", question)
            token = match.group(1) if match else None
            campaign = f" {token}" if token else ""
            query_text = f"{prefix}{market_name}{campaign} ecommerce shopping campaign {year} dates"
        else:
            query_text = f"{prefix}{market_name} ecommerce market event {year}"
        digest = hashlib.sha256(
            f"{purpose}|{market}|{query_text}".encode(),
        ).hexdigest()[:12]
        return LiveSearchPlan(
            plan_id=f"p5:deterministic:{digest}", mode=mode,
            queries=({
                "query": query_text, "market": market,
                "recency_days": 365, "purpose": purpose,
            },),
        )

    def plan(self, question: str, *, purpose: str, market: str, mode: str = "cache_only") -> LiveSearchPlan:
        if self.llm_client is None or not hasattr(self.llm_client, "plan_live_search"):
            raise SearchPlanningError("P5 live-search planner provider chưa khả dụng.")
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        as_of_date = now.astimezone(timezone.utc).date().isoformat()
        payload = {
            "question": question, "purpose": purpose, "market": market, "mode": mode,
            "as_of_date": as_of_date,
            "constraints": {
                "max_queries": self.max_queries, "max_query_chars": 200,
                "search_language": "en", "default_recency_days": 365,
                "allowed_markets": ["vn", "id", "global"],
                "no_secrets": True, "no_pii": True,
                # P5 phải neo query vào sàn thật của market, nếu không truy hồi ra rác.
                "marketplaces": list(MARKETPLACES.get(market, ())),
                "required_query_qualifiers": list(_CAMPAIGN_QUALIFIERS),
            },
        }
        errors: list[str] = []
        for _ in range(2):
            try:
                plan = LiveSearchPlan.model_validate(self.llm_client.plan_live_search(payload))
                if plan.mode != mode:
                    raise ValueError("P5 không được thay đổi execution mode.")
                if len(plan.queries) > self.max_queries:
                    raise ValueError("P5 vượt max_queries_per_request đã cấu hình.")
                if any(query.purpose != purpose or query.market != market for query in plan.queries):
                    raise ValueError("P5 query không khớp purpose/market đã route.")
                if any(query.recency_days is None for query in plan.queries):
                    raise ValueError("P5 query cập nhật phải có bounded recency_days.")
                normalized_question = question.strip().rstrip("?").casefold()
                if any(
                    query.query.strip().endswith("?")
                    or query.query.strip().rstrip("?").casefold() == normalized_question
                    for query in plan.queries
                ):
                    raise ValueError("P5 phải sinh search-engine query, không copy câu hỏi hội thoại.")
                if purpose == "campaign_context" and any(
                    not any(token in query.query.casefold() for token in _CAMPAIGN_QUALIFIERS)
                    for query in plan.queries
                ):
                    raise ValueError("P5 campaign query phải có qualifier shopping/campaign rõ ràng.")
                return plan
            except (ValidationError, ValueError, TypeError, RuntimeError) as exc:
                errors.append(str(exc)[:300])
                payload["validator_feedback"] = errors[-1]
        fallback = self._deterministic_fallback(
            question, purpose=purpose, market=market, mode=mode, as_of_date=as_of_date,
        )
        if fallback is not None:
            return fallback
        raise SearchPlanningError("P5 plan không hợp lệ sau bounded repair: " + "; ".join(errors))
