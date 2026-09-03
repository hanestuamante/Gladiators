"""Insight API — ultimate solution §12.4.

The response codes are the contract. A caller that has to read prose to tell a
bad filter from a missing id from a stale bundle will get it wrong the first
time the prose changes, so each case gets a stable code and these tests pin them.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gladiators.insights.api import router, set_repository
from gladiators.insights.builder import write_bundle
from gladiators.insights.contracts import (
    PAM_SCORECARD_COLUMNS,
    InsightCard,
    InsightEvidence,
    InsightScope,
    stable_id,
)
from gladiators.insights.pam import FORMULA_VERSION
from gladiators.insights.repository import InsightRepository

DATASET = "ds-test"
AS_OF = "2026-07-03"


def _card(kind="price_move", priority="medium", country="vn"):
    insight_id = stable_id(f"ic:{kind}", DATASET, country, priority)
    price = InsightEvidence(
        evidence_id=stable_id("ev:insight", insight_id, "price_change_percent", "k"),
        insight_id=insight_id, metric="price_change_percent", value=-15.0,
        unit="percent", formula="f", source_artifact="product_transition_metrics.csv",
        stable_row_key="vn:1@2026-07-03", dataset_version=DATASET,
    )
    sold = InsightEvidence(
        evidence_id=stable_id("ev:insight", insight_id, "snapshot_sales_delta_clean", "k"),
        insight_id=insight_id, metric="snapshot_sales_delta_clean", value=34.0,
        unit="sold_proxy_delta", formula="f",
        source_artifact="product_transition_metrics.csv",
        stable_row_key="vn:1@2026-07-03", dataset_version=DATASET,
    )
    card = InsightCard(
        insight_id=insight_id, kind=kind, title="t", finding="f",
        scope=InsightScope(country_code=country, as_of_date=AS_OF),
        evidence_ids=(price.evidence_id, sold.evidence_id),
        recommended_action="a", action_owner_role="r", impact_metric="m",
        baseline_value=1.0, target_definition="td", measurement_window="w",
        confidence="observed", priority=priority, dataset_version=DATASET,
    )
    return card, [price, sold]


@pytest.fixture(scope="module")
def bundle(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("insights")
    rows = 4
    data = {c: [None] * rows for c in PAM_SCORECARD_COLUMNS}
    data["product_listing_key"] = [f"vn:{i}" for i in range(rows)]
    data["country_code"] = ["vn", "vn", "id", "id"]
    data["shop_id"] = ["s1", "s2", "s3", "s3"]
    data["as_of_date"] = [AS_OF] * rows
    data["dataset_version"] = [DATASET] * rows
    data["formula_version"] = [FORMULA_VERSION] * rows
    data["pam_segment"] = ["Steady", "Star", "Cooling", "InsufficientData"]
    data["price_sentinel_excluded"] = [False, False, True, False]
    data["transition_missing"] = [False, True, False, False]
    scorecard = pd.DataFrame(data)[list(PAM_SCORECARD_COLUMNS)]

    cards, evidence = [], []
    for kind, priority in (("price_move", "medium"), ("top_mover", "high"),
                           ("data_quality", "high"), ("voucher_gap", "low")):
        card, items = _card(kind=kind, priority=priority)
        cards.append(card)
        evidence.extend(items)

    return write_bundle(
        root, DATASET, scorecard=scorecard, cards=cards, evidence=evidence,
        as_of_date=AS_OF, source_files={"products_clean.csv": "h"}, parameters={"top_k": 5},
    )


@pytest.fixture(scope="module")
def client(bundle) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    set_repository(InsightRepository(bundle))
    with TestClient(app) as test_client:
        yield test_client
    set_repository(None)


# --- envelope -------------------------------------------------------------

def test_every_response_carries_the_identifying_envelope(client):
    payload = client.get("/insights/v1/overview", params={"country": "vn"}).json()
    for field in ("schema_version", "dataset_version", "as_of_date",
                  "applied_filters", "warnings"):
        assert field in payload
    assert payload["dataset_version"] == DATASET
    assert payload["applied_filters"] == {"country": "vn"}


def test_health_reports_version_and_hash_but_no_path(client):
    """§12.4: no paths, no secrets."""
    payload = client.get("/insights/v1/health").json()
    assert payload["dataset_version"] == DATASET
    assert payload["content_hash"]
    blob = json.dumps(payload)
    assert "artifacts" not in blob
    assert "/" not in payload.get("content_hash", "")


# --- overview -------------------------------------------------------------

def test_overview_counts_listings_and_shops(client):
    payload = client.get("/insights/v1/overview", params={"country": "vn"}).json()
    assert payload["overview"]["listings"] == 2
    assert payload["overview"]["shops"] == 2
    assert payload["overview"]["segments"] == {"Star": 1, "Steady": 1}


def test_overview_requires_a_country(client):
    """§12.4 forbids country=all for monetary charts; requiring it makes that
    structural rather than a rule someone remembers."""
    assert client.get("/insights/v1/overview").status_code == 422
    assert client.get("/insights/v1/overview", params={"country": "all"}).status_code == 422


def test_quality_warnings_are_surfaced(client):
    payload = client.get("/insights/v1/overview", params={"country": "id"}).json()
    assert payload["overview"]["active_quality_warnings"] >= 1


# --- cards ----------------------------------------------------------------

def test_cards_filter_and_paginate(client):
    response = client.get("/insights/v1/cards", params={"limit": 2})
    payload = response.json()
    assert len(payload["cards"]) == 2
    assert payload["total"] == 4
    assert payload["next_cursor"]

    second = client.get(
        "/insights/v1/cards", params={"limit": 2, "cursor": payload["next_cursor"]}
    ).json()
    assert len(second["cards"]) == 2
    assert second["next_cursor"] is None
    assert {c["insight_id"] for c in payload["cards"]}.isdisjoint(
        {c["insight_id"] for c in second["cards"]}
    )


def test_cards_are_returned_in_deterministic_priority_order(client):
    cards = client.get("/insights/v1/cards", params={"limit": 50}).json()["cards"]
    priorities = [c["priority"] for c in cards]
    assert priorities == sorted(priorities, key=lambda p: {"high": 0, "medium": 1, "low": 2}[p])


def test_limit_above_the_cap_is_a_stable_422(client):
    response = client.get("/insights/v1/cards", params={"limit": 500})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INSIGHT_LIMIT_INVALID"


def test_a_corrupt_cursor_is_a_stable_422(client):
    response = client.get("/insights/v1/cards", params={"cursor": "!!!not-base64!!!"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INSIGHT_CURSOR_INVALID"


def test_kind_filter_narrows_the_result(client):
    payload = client.get("/insights/v1/cards", params={"kind": "price_move"}).json()
    assert all(c["kind"] == "price_move" for c in payload["cards"])


# --- single card and evidence --------------------------------------------

def test_a_card_is_returned_with_its_evidence(client):
    listed = client.get("/insights/v1/cards", params={"kind": "price_move"}).json()
    insight_id = listed["cards"][0]["insight_id"]
    payload = client.get(f"/insights/v1/cards/{insight_id}").json()
    assert payload["card"]["insight_id"] == insight_id
    assert len(payload["evidence"]) == 2


def test_malformed_id_is_422_and_unknown_id_is_404(client):
    """Different failures, different codes: one is the caller's mistake, the
    other is a question about what the bundle contains."""
    bad = client.get("/insights/v1/cards/not-an-id")
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "INSIGHT_ID_INVALID"

    missing = client.get(f"/insights/v1/cards/{'ic:price_move:' + '0' * 16}")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "INSIGHT_NOT_FOUND"


def test_evidence_outside_the_bundle_is_404(client):
    missing = client.get(f"/insights/v1/evidence/{'ev:insight:' + 'a' * 16}")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "EVIDENCE_NOT_FOUND"


def test_evidence_lookup_returns_the_traceable_record(client):
    listed = client.get("/insights/v1/cards", params={"kind": "price_move"}).json()
    evidence_id = listed["cards"][0]["evidence_ids"][0]
    payload = client.get(f"/insights/v1/evidence/{evidence_id}").json()
    assert payload["evidence"]["source_artifact"].endswith(".csv")
    assert payload["evidence"]["stable_row_key"]


# --- version pinning ------------------------------------------------------

def test_a_version_the_bundle_does_not_serve_is_503(client):
    """Substituting whatever is loaded would answer a different question."""
    response = client.get(
        "/insights/v1/overview", params={"country": "vn", "dataset_version": "ds-other"}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "INSIGHT_VERSION_MISMATCH"


def test_the_matching_version_is_accepted(client):
    response = client.get(
        "/insights/v1/overview", params={"country": "vn", "dataset_version": DATASET}
    )
    assert response.status_code == 200


# --- charts ---------------------------------------------------------------

def test_chart_payload_is_typed_data_not_prose(client):
    """A model-written label in a chart payload is an unverifiable claim
    wearing the costume of an axis."""
    payload = client.get(
        "/insights/v1/charts/price_move", params={"country": "vn"}
    ).json()["chart"]
    assert payload["chart_id"] == "price_move_scatter"
    assert payload["x"] == {"field": "price_change_percent", "unit": "percent"}
    assert payload["y"]["unit"] == "sold_proxy_delta"
    for point in payload["points"]:
        assert set(point) == {"listing_key", "x", "y", "insight_id", "evidence_ids"}
        assert isinstance(point["x"], (int, float))


def test_chart_points_link_back_to_evidence(client):
    chart = client.get(
        "/insights/v1/charts/price_move", params={"country": "vn"}
    ).json()["chart"]
    assert chart["points"]
    for point in chart["points"]:
        for evidence_id in point["evidence_ids"]:
            assert client.get(f"/insights/v1/evidence/{evidence_id}").status_code == 200
