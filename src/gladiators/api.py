from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from gladiators.contracts import AgentResponse
from gladiators.runtime_factory import create_runtime
from gladiators.ui import MVP_UI
from gladiators.ui_flow import FLOW_UI


class AskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


app = FastAPI(title="Gladiators V1", version="1.1.0")
runtime = create_runtime()


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def ui() -> str:
    return MVP_UI


@app.get("/flow", response_class=HTMLResponse, include_in_schema=False)
def ui_flow() -> str:
    return FLOW_UI


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "dataset_version": runtime.repo.dataset_version, "provider": runtime.llm_client.provider if runtime.llm_client else "offline"}


@app.get("/capabilities")
def capabilities() -> dict:
    return {"intents": runtime.registry.names(), "data": runtime.repo.capability_profile(), "unsupported_policy": "abstain"}


@app.post("/ask", response_model=AgentResponse)
def ask(request: AskRequest) -> AgentResponse:
    try:
        return runtime.run(request.text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "AGENT_RUNTIME_ERROR", "type": type(exc).__name__}) from exc
