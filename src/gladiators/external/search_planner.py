"""P5 bounded live-search planner; no tool access and one schema repair."""
from __future__ import annotations

from pydantic import ValidationError

from .search_contracts import LiveSearchPlan


class SearchPlanningError(RuntimeError):
    pass


class LiveSearchPlanner:
    def __init__(self, llm_client):
        self.llm_client = llm_client

    def plan(self, question: str, *, purpose: str, market: str, mode: str = "cache_only") -> LiveSearchPlan:
        if self.llm_client is None or not hasattr(self.llm_client, "plan_live_search"):
            raise SearchPlanningError("P5 live-search planner provider chưa khả dụng.")
        payload = {
            "question": question, "purpose": purpose, "market": market, "mode": mode,
            "constraints": {
                "max_queries": 3, "max_query_chars": 200,
                "allowed_markets": ["vn", "id", "global"],
                "no_secrets": True, "no_pii": True,
            },
        }
        errors: list[str] = []
        for _ in range(2):
            try:
                plan = LiveSearchPlan.model_validate(self.llm_client.plan_live_search(payload))
                if plan.mode != mode:
                    raise ValueError("P5 không được thay đổi execution mode.")
                if any(query.purpose != purpose or query.market != market for query in plan.queries):
                    raise ValueError("P5 query không khớp purpose/market đã route.")
                return plan
            except (ValidationError, ValueError, TypeError, RuntimeError) as exc:
                errors.append(str(exc)[:300])
                payload["validator_feedback"] = errors[-1]
        raise SearchPlanningError("P5 plan không hợp lệ sau bounded repair: " + "; ".join(errors))
