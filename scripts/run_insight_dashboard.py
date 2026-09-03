"""Launch the insight dashboard — ultimate solution §12.4.

    python -m streamlit run scripts/run_insight_dashboard.py

Talks to the insight API over HTTP. §12.4 forbids a second AgentRuntime here, so
this file resolves a transport and hands it to the renderer; it holds no data
logic and makes no decision the API has not already made.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from gladiators.insights.dashboard import InsightApiClient, render  # noqa: E402

API_BASE = os.environ.get("GLADIATORS_API_BASE", "http://127.0.0.1:8000")


class HttpTransport:
    """Minimal ``get(path, params)`` over the running API."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def get(self, path: str, params: dict | None = None):
        import httpx
        return httpx.get(f"{self.base_url}{path}", params=params or {}, timeout=15.0)


def in_process_transport():
    """Fallback for local use: mount the router without a separate server."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from gladiators.insights.api import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def main() -> None:
    transport = (
        in_process_transport() if os.environ.get("GLADIATORS_INSIGHT_INPROCESS")
        else HttpTransport(API_BASE)
    )
    render(InsightApiClient(transport))


main()
