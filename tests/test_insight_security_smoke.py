"""Security and UI smoke — ultimate solution §16 P11, §12.4.

Two questions this answers. Does the render path actually execute end to end
against a real bundle, and does anything the API returns leak something it
should not -- a filesystem path, a key, an internal exception?

Streamlit is not a declared dependency, so ``render()`` runs against a stub. That
verifies the wiring and the call sequence; it does not verify that the page
*looks* right, and nothing here should be read as claiming it does.
"""
from __future__ import annotations

import json
import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gladiators.insights.api import router, set_repository
from gladiators.insights.dashboard import (
    DashboardFilters,
    InsightApiClient,
    load_state,
    render,
)
from gladiators.insights.repository import InsightRepository
from tests.test_insight_api import bundle  # noqa: F401  (fixture reuse)


@pytest.fixture
def client(bundle):  # noqa: F811
    app = FastAPI()
    app.include_router(router)
    set_repository(InsightRepository(bundle))
    with TestClient(app) as transport:
        yield transport
    set_repository(None)


# --- security -------------------------------------------------------------

FORBIDDEN_FRAGMENTS = (
    "artifacts/", "artifacts\\", "C:\\", "/home/", "Traceback",
    "api_key", "API_KEY", "Bearer ", "password", ".env",
)


def _assert_clean(payload: str, where: str) -> None:
    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment not in payload, f"{where} rò rỉ {fragment!r}"


def test_no_endpoint_leaks_a_path_a_key_or_a_traceback(client, bundle):  # noqa: F811
    """§12.4: health reports schema/version/hash and never a path or secret."""
    cards = client.get("/insights/v1/cards", params={"limit": 50}).json()["cards"]
    insight_id = cards[0]["insight_id"]
    evidence_id = cards[0]["evidence_ids"][0]

    for path, params in (
        ("/insights/v1/health", {}),
        ("/insights/v1/overview", {"country": "vn"}),
        ("/insights/v1/cards", {"limit": 20}),
        (f"/insights/v1/cards/{insight_id}", {}),
        (f"/insights/v1/evidence/{evidence_id}", {}),
        ("/insights/v1/charts/price_move", {"country": "vn"}),
    ):
        response = client.get(path, params=params)
        assert response.status_code == 200
        _assert_clean(json.dumps(response.json(), ensure_ascii=False), path)


def test_error_responses_carry_a_code_not_an_exception(client):
    """A stack trace tells an attacker the shape of the system and tells a
    caller nothing it can branch on."""
    for path, params, status in (
        ("/insights/v1/cards/not-an-id", {}, 422),
        (f"/insights/v1/cards/{'ic:top_mover:' + '0' * 16}", {}, 404),
        ("/insights/v1/overview", {"country": "vn", "dataset_version": "ds-x"}, 503),
        ("/insights/v1/cards", {"limit": 9999}, 422),
    ):
        response = client.get(path, params=params)
        assert response.status_code == status
        body = json.dumps(response.json(), ensure_ascii=False)
        _assert_clean(body, path)
        assert response.json()["detail"]["code"]


def test_an_evidence_id_cannot_be_used_to_traverse(client):
    """The id is a dict key, but the pattern keeps a hostile value from ever
    reaching a path join or a log formatter downstream."""
    for hostile in ("../../etc/passwd", "ev:insight:../../x", "ev:insight:%2e%2e"):
        response = client.get(f"/insights/v1/evidence/{hostile}")
        assert response.status_code in {404, 422}
        _assert_clean(json.dumps(response.json(), ensure_ascii=False), hostile)


def test_card_text_carries_no_internal_vocabulary(client):
    """A finding is read by a human; a column name is not something to act on."""
    cards = client.get("/insights/v1/cards", params={"limit": 50}).json()["cards"]
    for card in cards:
        assert "product_listing_key" not in card["finding"]
        assert "NaN" not in card["finding"]


# --- render smoke ---------------------------------------------------------

class _StreamlitStub(types.ModuleType):
    """Records the calls ``render()`` makes so the sequence can be asserted."""

    def __init__(self):
        super().__init__("streamlit")
        self.calls: list[str] = []
        self.sidebar = self

    def __getattr__(self, name):
        def recorder(*args, **kwargs):
            self.calls.append(name)
            if name == "columns":
                return [self for _ in range(args[0] if args else 1)]
            if name == "selectbox":
                options = args[1] if len(args) > 1 else kwargs.get("options", (None,))
                return next(iter(options), None)
            return self
        return recorder

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_render_runs_end_to_end_against_a_real_bundle(client, monkeypatch):
    """Verifies wiring and call sequence -- not that the page looks right."""
    stub = _StreamlitStub()
    monkeypatch.setitem(sys.modules, "streamlit", stub)

    render(InsightApiClient(client), DashboardFilters(country="vn"))

    assert "set_page_config" in stub.calls
    assert "metric" in stub.calls
    assert "bar_chart" in stub.calls
    assert "error" not in stub.calls


def test_render_shows_an_error_rather_than_an_empty_page(monkeypatch):
    """A user reads "no insights" as a finding, not as an outage."""
    class Failing:
        def get(self, path, params=None):
            class Response:
                status_code = 503

                @staticmethod
                def json():
                    return {"detail": {"code": "INSIGHT_BUNDLE_UNAVAILABLE",
                                       "message": "chưa build"}}
            return Response()

    stub = _StreamlitStub()
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    render(InsightApiClient(Failing()), DashboardFilters())
    assert "error" in stub.calls
    assert "bar_chart" not in stub.calls


def test_rendered_state_contains_no_dataframe(client):
    """§12.4: DataFrames are request-scoped internals, never serialized out."""
    import pandas as pd

    state = load_state(InsightApiClient(client), DashboardFilters(country="vn"))
    for value in (state.overview, state.chart, *state.cards):
        assert not isinstance(value, pd.DataFrame)
    assert json.dumps(state.overview)
    assert json.dumps(state.chart)
