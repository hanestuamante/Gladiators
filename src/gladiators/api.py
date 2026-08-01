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


@app.post("/ask", response_model=AgentResponse)
def ask(request: AskRequest) -> AgentResponse:
    try:
        return runtime.run(request.text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "AGENT_RUNTIME_ERROR", "type": type(exc).__name__}) from exc
