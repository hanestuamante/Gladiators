from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from gladiators.contracts import AgentResponse
from gladiators.insights.api import router as insights_router
from gladiators.runtime_factory import create_runtime
from gladiators.ui import MVP_UI
from gladiators.ui_flow import FLOW_UI


class AskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    # WP-A3. Không truyền session_id ⇒ hành vi cũ TỪNG BIT (A3-R3): bộ nhớ hội
    # thoại là thứ caller phải chọn dùng, không phải thứ bật sẵn cho mọi lời gọi.
    session_id: str | None = Field(default=None, max_length=128)
    reset: bool = False


app = FastAPI(title="Gladiators V2", version="2.0.0-alpha")
runtime = create_runtime()

# §12.4: the insight mart is served read-only from a pinned sidecar bundle. It
# shares this app rather than standing up a second AgentRuntime.
app.include_router(insights_router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def ui() -> str:
    return MVP_UI


@app.get("/flow", response_class=HTMLResponse, include_in_schema=False)
def ui_flow() -> str:
    return FLOW_UI


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok", "dataset_version": runtime.repo.dataset_version,
        "provider": runtime.llm_client.provider if runtime.llm_client else "offline",
        "live_search_enabled": runtime.enable_live_search,
    }


@app.get("/capability-map", response_class=HTMLResponse, include_in_schema=False)
def capability_map_page() -> str:
    """WP-B8 — biết hệ làm được gì TRƯỚC khi bị từ chối."""
    from gladiators.ui_capability import render

    return render()


@app.get("/capability-map.json")
def capability_map_json() -> dict:
    """Cùng một nguồn cho trang, slide và test."""
    from gladiators.ui_capability import capability_map

    return capability_map()


@app.get("/capabilities")
def capabilities() -> dict:
    return {
        "intents": runtime.registry.names(),
        "certified_macros": runtime.macros.names(),
        "analytical_templates": (
            "highest_revenue_day", "listing_count",
            "highest_price_listing", "highest_monthly_sold_listing", "top_shop_by_listing_count",
            "price_change_by_date",
        ),
        "planner": {"ir_version": "1.0", "critic_enabled": runtime.enable_critic, "nversion_enabled": runtime.enable_nversion},
        "external": {
            "live_search_enabled": runtime.enable_live_search,
            "max_admission": "context_only",
            "cross_tier_conversion": False,
        },
        "data": runtime.repo.capability_profile(),
        "unsupported_policy": "clarify_or_abstain",
    }


@app.post("/session/{session_id}/reset")
def reset_session(session_id: str) -> dict[str, bool]:
    """Huỷ ngữ cảnh đang mang theo — A3 luật 2: bộ nhớ phải huỷ được.

    Trả ``cleared`` kể cả khi không có phiên nào để xoá: người dùng bấm "bỏ ngữ
    cảnh" cần biết kết quả là "không còn ngữ cảnh", không cần biết trước đó có
    hay không.
    """
    runtime.conversations.reset(session_id)
    return {"cleared": True}


@app.post("/ask", response_model=AgentResponse)
def ask(request: AskRequest) -> AgentResponse:
    if request.reset and request.session_id:
        runtime.conversations.reset(request.session_id)
    try:
        return runtime.run(request.text, session_id=request.session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "AGENT_RUNTIME_ERROR", "type": type(exc).__name__}) from exc
