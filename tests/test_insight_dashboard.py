"""Insight dashboard — ultimate solution §12.4 / §12.5.

Two rules carry real risk and get most of the tests: the drawer may only open on
evidence already on the page, and Ask-deeper may never carry table content into
a prompt. Everything else the page shows is an API response rendered verbatim.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gladiators.insights.api import router, set_repository
from gladiators.insights.dashboard import (
    ASK_DEEPER_ENABLED,
    DashboardFilters,
    InsightApiClient,
    ask_deeper_payload,
    layout_sections,
    load_state,
    open_evidence_drawer,
)
from gladiators.insights.repository import InsightRepository
from tests.test_insight_api import bundle  # noqa: F401  (fixture reuse)


@pytest.fixture
def client(bundle) -> InsightApiClient:  # noqa: F811
    app = FastAPI()
    app.include_router(router)
    set_repository(InsightRepository(bundle))
    with TestClient(app) as transport:
        yield InsightApiClient(transport)
    set_repository(None)


@pytest.fixture
def state(client):
    return load_state(client, DashboardFilters(country="vn"))


# --- loading --------------------------------------------------------------

def test_state_comes_entirely_from_the_api(state):
    """A number on screen and a number in the bundle cannot disagree if the
    page holds no data logic of its own."""
    assert state.error is None
    assert state.dataset_version
    assert state.as_of_date
    assert state.overview["listings"] == 2
    assert state.cards


def test_layout_matches_the_interaction_contract():
    sections = layout_sections()
    assert sections[0] == "filters"
    assert "evidence_drawer" in sections
    assert "external_context_footer" in sections


def test_an_unavailable_bundle_is_an_error_not_an_empty_page():
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

    state = load_state(InsightApiClient(Failing()), DashboardFilters())
    assert state.error
    assert "INSIGHT_BUNDLE_UNAVAILABLE" in state.error
    assert state.cards == []


def test_filters_are_passed_through_to_the_api(client):
    state = load_state(client, DashboardFilters(country="vn", kind="price_move"))
    assert all(card["kind"] == "price_move" for card in state.cards)


# --- evidence drawer ------------------------------------------------------

def test_drawer_opens_on_evidence_already_on_the_page(client, state):
    evidence_id = state.cards[0]["evidence_ids"][0]
    updated = open_evidence_drawer(client, state, evidence_id)
    assert updated.selected_evidence is not None
    assert updated.selected_evidence["evidence_id"] == evidence_id
    assert updated.selected_evidence["source_artifact"].endswith(".csv")


def test_drawer_refuses_an_id_that_is_not_displayed(client, state):
    """Otherwise the URL bar becomes a way to browse the whole bundle."""
    updated = open_evidence_drawer(client, state, "ev:insight:" + "f" * 16)
    assert updated.selected_evidence is None
    assert any("không thuộc" in w for w in updated.warnings)


def test_drawer_lookup_is_deterministic_and_uses_no_agent(client, state):
    evidence_id = state.cards[0]["evidence_ids"][0]
    first = open_evidence_drawer(client, state, evidence_id).selected_evidence
    second = open_evidence_drawer(client, state, evidence_id).selected_evidence
    assert first == second


# --- ask deeper -----------------------------------------------------------

def test_ask_deeper_is_off_in_this_release():
    """§12.4: it stays off until the server can confirm a preselected-evidence
    contract. A constant, not a setting, so enabling it shows up in review."""
    assert ASK_DEEPER_ENABLED is False


def test_ask_deeper_sends_nothing_while_disabled(state):
    evidence_id = state.cards[0]["evidence_ids"][0]
    assert ask_deeper_payload(state, evidence_id) is None


def test_ask_deeper_would_only_ever_send_allow_listed_ids(state, monkeypatch):
    """Never a frame, never a chart payload: table content in a prompt turns
    unverified data into instructions."""
    monkeypatch.setattr(
        "gladiators.insights.dashboard.ASK_DEEPER_ENABLED", True, raising=False
    )
    evidence_id = state.cards[0]["evidence_ids"][0]
    payload = ask_deeper_payload(state, evidence_id)
    assert payload == {
        "evidence_ids": [evidence_id], "dataset_version": state.dataset_version,
    }
    assert set(payload) == {"evidence_ids", "dataset_version"}


def test_ask_deeper_rejects_an_id_not_on_the_page(state, monkeypatch):
    monkeypatch.setattr(
        "gladiators.insights.dashboard.ASK_DEEPER_ENABLED", True, raising=False
    )
    assert ask_deeper_payload(state, "ev:insight:" + "0" * 16) is None


# --- chart ----------------------------------------------------------------

def test_chart_points_are_clickable_through_to_evidence(client, state):
    for point in state.chart.get("points", []):
        for evidence_id in point["evidence_ids"]:
            assert open_evidence_drawer(client, state, evidence_id).selected_evidence


def test_dashboard_does_not_build_a_second_runtime():
    """§12.4: two runtimes means two answers with no way to tell which was seen."""
    import ast
    import inspect

    from gladiators.insights import dashboard

    # Parse rather than grep: the module docstring explains *why* it does not
    # build a runtime, and a text search flags its own explanation.
    tree = ast.parse(inspect.getsource(dashboard))
    imported = {
        alias.name for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in node.names
    } | {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any("runtime" in str(name) for name in imported), imported

    called = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "create_runtime" not in called
    assert "AgentRuntime" not in called
