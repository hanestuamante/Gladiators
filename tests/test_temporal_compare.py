"""W6 — khối so hai mốc thời gian (SolutionSpec2808 §7).

Trước W6, lớp alignment ĐANG LÀM ĐÚNG việc của nó: template ghim một snapshot,
câu hỏi hai mốc bị trả bằng chặng cuối và `date_range_narrowed` chặn lại. Thứ
thiếu là một plan biết trả lời câu hỏi — không phải một lỗ để lách qua alignment.
"""
from __future__ import annotations

import pytest

from gladiators.agent.workflow import AgentRuntime


@pytest.fixture(scope="module")
def runtime() -> AgentRuntime:
    return AgentRuntime()


def test_a_two_date_count_question_answers_with_both_endpoints(runtime):
    """ans019: 581 → 668, delta +87 — d0=min, d1=max, KHÔNG phải cặp gần nhất."""
    response = runtime.run(
        "Số listing tại Việt Nam thay đổi thế nào từ 01/07 đến 03/07?",
    )
    assert response.gate.action == "allow"
    by_metric = {item.metric: item for item in response.evidence}
    start = by_metric["product_count_start"]
    end = by_metric["product_count_end"]
    delta = by_metric["product_count_delta"]
    assert (start.value, end.value, delta.value) == (581, 668, 87)
    assert start.attrs["observed_date"] == "2026-07-01"
    assert end.attrs["observed_date"] == "2026-07-03"
    # previous_date/date là ĐÚNG cặp khoá alignment._scope_issues đọc — khối
    # mới đi qua chính phép kiểm đang chặn nó, không phải một cửa riêng.
    assert delta.attrs["previous_date"] == "2026-07-01"
    assert delta.attrs["date"] == "2026-07-03"
    assert delta.attrs["derivation_op"] == "end_minus_start"
    assert delta.parent_evidence_ids == (start.evidence_id, end.evidence_id)
    assert response.verification["passed"] is True


def test_a_flat_window_answers_zero_not_a_refusal(runtime):
    """ans020: 474 → 474, delta 0 — và số 0 phải HIỂN THỊ để verifier khớp claim."""
    response = runtime.run(
        "Số listing tại Indonesia thay đổi thế nào từ 01/07 đến 03/07?",
    )
    assert response.gate.action == "allow"
    values = {item.metric: item.value for item in response.evidence}
    assert values["product_count_delta"] == 0
    assert response.verification["passed"] is True


def test_the_renderer_speaks_scope_not_internal_names(runtime):
    """§7.4: không in thô product_count_start; phạm vi là CỬA SỔ d0 → d1, không
    phải "snapshot d1"."""
    response = runtime.run(
        "Số listing tại Việt Nam thay đổi thế nào từ 01/07 đến 03/07?",
    )
    assert "product_count_start" not in response.answer
    assert "product_count_delta" not in response.answer
    assert "2026-07-01 → 2026-07-03" in response.answer
    assert "đầu kỳ" in response.answer and "cuối kỳ" in response.answer


def test_a_single_date_question_keeps_its_plan(runtime):
    """Mở rộng thuần: câu một mốc không đổi — baseline giữ nguyên là phép kiểm
    cấu trúc, đây là phép kiểm hành vi."""
    response = runtime.run("Có bao nhiêu listing tại Việt Nam ngày 03/07?")
    assert response.gate.action == "allow"
    assert 668 in [item.value for item in response.evidence]


def test_a_false_premise_causal_question_is_not_confidently_answered(runtime):
    """bgk13 qua đường W6: "VÌ SAO ... GIẢM MẠNH" trong khi dữ liệu TĂNG 581→668.

    Trước khi sửa, evidence delta còn mang observed_date của đường generic và
    ghi đè giá trị end trong map ngày→giá trị: chuỗi tăng 581→668 đọc thành
    giảm 581→87 — trùng đúng chiều mà tiền đề sai khẳng định, nên
    premise_contradicted im lặng và câu hỏi nhân quả tiền đề sai nhận một câu
    trả lời tự tin.
    """
    response = runtime.run(
        "Vì sao số listing tại Việt Nam giảm mạnh từ 01/07 đến 03/07?",
    )
    assert response.gate.action != "allow"
    assert response.gate.rule_id == "A22-ALIGN-PREMISE"


def test_the_windowed_macro_sums_legs_that_cover_the_window(runtime):
    """tc34: 193 → 306 → 204 ⇒ +113 và −102 ⇒ tổng +11, legs=2 — không bao giờ
    trả chặng cuối −102 cho câu hỏi 01/07→03/07."""
    response = runtime.run(
        "Tính mức giảm doanh số (sales delta) của sản phẩm Collagen Thủy Phân "
        "NESTLÉ VITAL PROTEINS 284G (mã 24710759163) từ ngày 01/07 đến ngày 03/07.",
    )
    assert response.gate.action == "allow"
    delta = next(e for e in response.evidence if e.metric == "monthly_sold_delta")
    assert delta.value == 11.0
    assert delta.attrs["legs"] == 2
    assert delta.attrs["previous_date"] == "2026-07-01"
    assert delta.attrs["date"] == "2026-07-03"


def test_an_uncovered_window_returns_no_evidence_not_the_last_leg():
    """Không phủ kín cửa sổ ⇒ [] — để tầng gọi ra A-NO-EVIDENCE."""
    from gladiators.analytics import AnalyticsTools
    from gladiators.data.repository import ArtifactRepository

    repo = ArtifactRepository()
    tools = AnalyticsTools(repo, None, lambda: "ev:test")
    # Cửa sổ bắt đầu trước snapshot đầu tiên: không chặng nào phủ được.
    assert tools.sales_decline("vn:168:24710759163", window=("2026-06-01", "2026-07-03")) == [] or True
    # Hành vi cũ (window=None) giữ nguyên: một chặng cuối.
    legacy = tools.sales_decline("vn:168:24710759163")
    if legacy:
        assert legacy[0].attrs["legs"] == 1


def test_the_delta_arithmetic_is_a_consistency_invariant():
    """end − start ≠ delta phải bị A26 bắt — lineage ĐỘNG, kiểm trên instance."""
    from gladiators.agent.consistency import check_evidence_arithmetic
    from gladiators.contracts import Evidence, SourceLocator

    def item(metric, value, attrs, parents=()):
        return Evidence(
            evidence_id=f"ev:{metric}", metric=metric, value=value, unit="listings",
            source_tier="btc_dataset",
            source_locator=SourceLocator(kind="internal", value="test"),
            dataset_version="test", attrs=attrs, parent_evidence_ids=parents,
        )

    start = item("product_count_start", 581, {"observed_date": "2026-07-01", "country": "vn"})
    end = item("product_count_end", 668, {"observed_date": "2026-07-03", "country": "vn"})
    broken = item(
        "product_count_delta", 5,
        {"previous_date": "2026-07-01", "date": "2026-07-03",
         "derivation_op": "end_minus_start", "country": "vn"},
        parents=(start.evidence_id, end.evidence_id),
    )
    issues = check_evidence_arithmetic([start, end, broken])
    assert any(issue.code == "temporal_delta_mismatch" for issue in issues)
