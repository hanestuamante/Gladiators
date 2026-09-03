"""Theme B: coverage, not containment — and premises that get checked.

bgk13 asked "vì sao số listing tại VN giảm mạnh từ 01/07 đến 03/07?".  The count
rose 581 → 668, so the premise was false; the answer was "Có 668 listing", which
answers a different question; and it was drawn from the 03/07 snapshot alone, so
it did not cover the window asked about.  All three passed every existing check,
and the reply carried "Độ tin cậy: High".
"""
from __future__ import annotations

import pytest

from gladiators.agent.alignment import (
    check_evidence_alignment,
    check_question_alignment,
)
from gladiators.agent.context import RequestDigest
from gladiators.agent.workflow import AgentRuntime
from gladiators.contracts import Evidence, SourceLocator


@pytest.fixture(scope="module")
def runtime(tmp_path_factory) -> AgentRuntime:
    return AgentRuntime(trace_dir=tmp_path_factory.mktemp("premise"))


def _digest(question: str, date_range: tuple[str, ...] = ()) -> RequestDigest:
    return RequestDigest(
        normalized_question=question, language="vi", intent="open_analytical",
        countries=("vn",), requested_output_shape="scalar", date_range=date_range,
    )


def _snapshot_evidence(value: int, observed: str) -> Evidence:
    return Evidence(
        evidence_id="ev:test:0001", source_tier="btc_dataset", metric="listing_count",
        value=value, unit="listings",
        source_locator=SourceLocator(kind="internal", value="product_snapshot_metrics"),
        dataset_version="test",
        attrs={"country": "vn", "observed_date": observed},
    )


def test_one_snapshot_does_not_cover_a_two_day_window():
    # B1: the old check asked whether the observed date sat INSIDE the window.
    # An end-of-period snapshot always does, so narrowing was undetectable here
    # while the transition branch right below caught the same class of defect.
    verdict = check_evidence_alignment(
        _digest("so listing tai vn giam manh tu 01/07 den 03/07",
                ("2026-07-01", "2026-07-03")),
        [_snapshot_evidence(668, "2026-07-03")],
    )
    assert not verdict.aligned
    assert "date_range_narrowed" in {issue.code for issue in verdict.issues}
    assert verdict.rule_id == "A22-ALIGN-DATE"


def test_evidence_covering_both_ends_is_aligned():
    verdict = check_evidence_alignment(
        _digest("so listing tai vn tu 01/07 den 03/07", ("2026-07-01", "2026-07-03")),
        [_snapshot_evidence(581, "2026-07-01"), _snapshot_evidence(668, "2026-07-03")],
    )
    assert verdict.aligned


def test_a_single_date_question_is_untouched():
    verdict = check_evidence_alignment(
        _digest("so listing tai vn ngay 03/07", ("2026-07-03", "2026-07-03")),
        [_snapshot_evidence(668, "2026-07-03")],
    )
    assert verdict.aligned


@pytest.mark.parametrize("question", [
    "vi sao so listing tai viet nam giam manh tu 01/07 den 03/07",
    "tai sao doanh so giam",
    "mengapa penjualan turun",
    "why did listings drop",
])
def test_a_why_question_is_not_answered_by_a_bare_count(question):
    # B2: asked *why*, answered *how many*. The guard against asserting causation
    # already existed for insight cards; nothing checked the opposite failure --
    # quietly answering a different question than the causal one asked.
    verdict = check_question_alignment(_digest(question), "Có 668 listing trong phạm vi đã chọn.")
    assert not verdict.aligned
    assert "causal_question_unanswered" in {issue.code for issue in verdict.issues}


def test_a_non_causal_question_answered_by_a_count_is_fine():
    verdict = check_question_alignment(
        _digest("co bao nhieu listing tai viet nam"), "Có 668 listing trong phạm vi đã chọn.",
    )
    assert verdict.aligned


def test_a_stated_direction_is_checked_against_the_data():
    # B3: "giảm mạnh" is a claim about the data, not a framing device. 581 -> 668
    # is a rise, so the premise is false and no part of the question is
    # answerable as asked.
    verdict = check_question_alignment(
        _digest("so listing tai viet nam giam manh tu 01/07 den 03/07",
                ("2026-07-01", "2026-07-03")),
        "Có 668 listing.",
        [_snapshot_evidence(581, "2026-07-01"), _snapshot_evidence(668, "2026-07-03")],
    )
    assert not verdict.aligned
    assert "premise_contradicted" in {issue.code for issue in verdict.issues}
    assert verdict.rule_id == "A22-ALIGN-PREMISE"


def test_a_stated_direction_the_data_agrees_with_passes():
    verdict = check_question_alignment(
        _digest("so listing tai viet nam tang manh tu 01/07 den 03/07",
                ("2026-07-01", "2026-07-03")),
        "Có 668 listing.",
        [_snapshot_evidence(581, "2026-07-01"), _snapshot_evidence(668, "2026-07-03")],
    )
    assert "premise_contradicted" not in {issue.code for issue in verdict.issues}


def test_bgk13_is_no_longer_a_confident_allow(runtime):
    response = runtime.run("Vì sao số listing tại Việt Nam giảm mạnh từ 01/07 đến 03/07?")
    assert response.gate.action != "allow"
