"""Insight dashboard — ultimate solution §12.4 / §12.5.

A Streamlit view over the insight API.  §12.4 requires it to call the API rather
than construct a second ``AgentRuntime``: two runtimes would mean two answers to
the same question with no way to tell which one a user saw.

The interaction rule that matters is Ask-deeper.  Click-to-evidence is
deterministic and always available -- it just looks up an Evidence record the
server already published.  Ask-deeper sends a question to the agent, and §12.4
allows it *only* when the server has confirmed the evidence id belongs to the
active bundle. Until the preselected-evidence contract exists, the drawer
displays and the button stays off; a chart payload or DataFrame must never be
pasted into a prompt, because that turns unverified table content into
instructions.

This module holds no data logic. Everything it shows comes from an API response,
so a number on screen and a number in the bundle cannot disagree.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DASHBOARD_VERSION = "insight-dashboard.v1"

def _countries() -> tuple[str, ...]:
    """Đọc từ nơi khai, không giữ bản sao. Đây CHÍNH là bản sao duy nhất từng
    tồn tại của danh sách thị trường, và nó nằm trong một file dashboard."""
    from gladiators.domain.markets import markets

    return markets()


COUNTRIES = _countries()
CARD_KINDS = ("top_mover", "price_move", "voucher_gap", "data_quality")

# §12.4: Ask-deeper stays off until the server can confirm a preselected
# evidence contract. This is a constant, not a setting, so enabling it is a code
# change that shows up in review.
ASK_DEEPER_ENABLED = False


@dataclass(frozen=True)
class DashboardFilters:
    country: str = "vn"
    category_id: str | None = None
    kind: str | None = None
    priority: str | None = None

    def as_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {"country": self.country}
        for name in ("category_id", "kind", "priority"):
            value = getattr(self, name)
            if value:
                params[name] = value
        return params


@dataclass
class DashboardState:
    """What the page renders. Populated entirely from API responses."""
    dataset_version: str = ""
    as_of_date: str = ""
    overview: dict[str, Any] = field(default_factory=dict)
    cards: list[dict[str, Any]] = field(default_factory=list)
    chart: dict[str, Any] = field(default_factory=dict)
    selected_evidence: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class InsightApiClient:
    """Thin HTTP client. Any transport with a ``get(path, params)`` works."""

    def __init__(self, transport, base_path: str = "/insights/v1"):
        self.transport = transport
        self.base_path = base_path

    def _get(self, path: str, params: dict | None = None) -> tuple[int, dict]:
        response = self.transport.get(f"{self.base_path}{path}", params=params or {})
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, {}

    def overview(self, filters: DashboardFilters):
        return self._get("/overview", {"country": filters.country})

    def cards(self, filters: DashboardFilters, limit: int = 20):
        return self._get("/cards", {**filters.as_params(), "limit": limit})

    def price_move_chart(self, filters: DashboardFilters):
        return self._get("/charts/price_move", {"country": filters.country})

    def evidence(self, evidence_id: str):
        return self._get(f"/evidence/{evidence_id}")


def load_state(client: InsightApiClient, filters: DashboardFilters) -> DashboardState:
    """Fetch everything the page shows, or report why it could not."""
    state = DashboardState()

    status, payload = client.overview(filters)
    if status == 503:
        # A stale or missing bundle is not something to paper over with an
        # empty page: the user would read "no insights" as a finding.
        state.error = _error_message(payload, "Bundle insight chưa sẵn sàng.")
        return state
    if status != 200:
        state.error = _error_message(payload, "Không tải được tổng quan.")
        return state

    state.dataset_version = payload.get("dataset_version", "")
    state.as_of_date = payload.get("as_of_date", "")
    state.overview = payload.get("overview", {})
    state.warnings = list(payload.get("warnings", []))

    status, payload = client.cards(filters)
    if status == 200:
        state.cards = list(payload.get("cards", []))
    else:
        state.warnings.append(_error_message(payload, "Không tải được danh sách insight."))

    status, payload = client.price_move_chart(filters)
    if status == 200:
        state.chart = payload.get("chart", {})
    else:
        state.warnings.append(_error_message(payload, "Không tải được biểu đồ."))
    return state


def open_evidence_drawer(
    client: InsightApiClient, state: DashboardState, evidence_id: str,
) -> DashboardState:
    """Click-to-evidence: deterministic lookup, no agent involved."""
    allowed = {
        eid for card in state.cards for eid in card.get("evidence_ids", ())
    } | {
        eid for point in state.chart.get("points", ()) for eid in point.get("evidence_ids", ())
    }
    if evidence_id not in allowed:
        # The drawer may only open on evidence already on the page. Fetching an
        # arbitrary id would let the URL bar browse the bundle.
        state.selected_evidence = None
        state.warnings.append("Evidence không thuộc nội dung đang hiển thị.")
        return state

    status, payload = client.evidence(evidence_id)
    if status != 200:
        state.selected_evidence = None
        state.warnings.append(_error_message(payload, "Không mở được evidence."))
        return state
    state.selected_evidence = payload.get("evidence")
    return state


def ask_deeper_payload(state: DashboardState, evidence_id: str) -> dict | None:
    """Allow-listed evidence ids only -- never a frame or a chart payload.

    Returns ``None`` while the feature is off, which is the current release
    state (§12.4). Sending table content into a prompt would turn unverified
    data into instructions.
    """
    if not ASK_DEEPER_ENABLED:
        return None
    allowed = {eid for card in state.cards for eid in card.get("evidence_ids", ())}
    if evidence_id not in allowed:
        return None
    return {
        "evidence_ids": [evidence_id],
        "dataset_version": state.dataset_version,
    }


def layout_sections() -> tuple[str, ...]:
    """§12.5 interaction contract, as data so the test can check it."""
    return (
        "filters", "kpi", "pam_segment_distribution", "top_movers",
        "price_change_vs_sold_delta", "voucher_gap_and_data_quality",
        "insight_feed", "evidence_drawer", "external_context_footer",
    )


def _error_message(payload: dict, fallback: str) -> str:
    detail = payload.get("detail")
    if isinstance(detail, dict) and detail.get("code"):
        return f"{detail['code']}: {detail.get('message', fallback)}"
    return fallback


def render(client: InsightApiClient, filters: DashboardFilters | None = None) -> None:
    """Streamlit entry point. Imported lazily so tests need no Streamlit."""
    import streamlit as st

    st.set_page_config(page_title="Gladiators — Insight", layout="wide")
    filters = filters or DashboardFilters(
        country=st.sidebar.selectbox("Quốc gia", COUNTRIES),
        kind=st.sidebar.selectbox("Loại insight", (None,) + CARD_KINDS),
        priority=st.sidebar.selectbox("Mức ưu tiên", (None, "high", "medium", "low")),
    )
    state = load_state(client, filters)
    if state.error:
        st.error(state.error)
        return

    st.caption(
        f"dataset `{state.dataset_version}` · as_of `{state.as_of_date}` · {DASHBOARD_VERSION}"
    )
    columns = st.columns(4)
    for column, (label, key) in zip(columns, (
        ("Listing", "listings"), ("Shop", "shops"),
        ("Snapshot", "snapshot_coverage"), ("Cảnh báo dữ liệu", "active_quality_warnings"),
    )):
        column.metric(label, state.overview.get(key, "—"))

    st.subheader("Phân bố PAM segment")
    st.bar_chart(state.overview.get("segments", {}))

    st.subheader("Insight")
    for card in state.cards:
        with st.expander(f"[{card['priority']}] {card['title']}"):
            st.write(card["finding"])
            st.caption(f"Hành động: {card['recommended_action']} · {card['action_owner_role']}")
            for evidence_id in card["evidence_ids"]:
                st.code(evidence_id, language="text")

    for warning in state.warnings:
        st.warning(warning)
    st.caption("Nguồn ngoài chỉ dùng làm ngữ cảnh, không tham gia tính toán.")
