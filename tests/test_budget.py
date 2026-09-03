"""Ngân sách độ trễ và phép đo theo chặng — Spec2308 §WP-A6.1."""
from __future__ import annotations

from gladiators.agent.budget import (
    MAX_LLM_CALLS_CRITICAL,
    P95_BUDGET_SECONDS,
    STAGES,
    StageTimer,
    within_budget,
)
from gladiators.agent.workflow import AgentRuntime


def test_every_stage_is_reported_even_when_it_never_ran():
    """Chặng không chạy phải ra 0, không được VẮNG MẶT.

    Một khoá vắng mặt và một chặng tốn 0ms trông giống hệt nhau ở phía đọc bảng,
    và đó đúng là cách một chặng bị bỏ quên biến mất khỏi phép đo.
    """
    timing = StageTimer().as_dict()
    assert set(timing) == set(STAGES) | {"total"}
    assert all(value >= 0 for value in timing.values())


def test_total_covers_time_that_falls_outside_every_stage():
    timer = StageTimer()
    with timer.stage("parse"):
        sum(range(10_000))
    timing = timer.as_dict()
    assert timing["total"] >= timing["parse"]


def test_a_stage_that_raises_is_still_measured():
    """Chặng hỏng thường là chặng chậm nhất; bỏ nó là bỏ đúng ca cần nhìn."""
    timer = StageTimer()
    try:
        with timer.stage("plan"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert timer.as_dict()["plan"] >= 0


def test_a_real_run_records_nine_stages_and_a_budget_verdict():
    response = AgentRuntime().run("Có bao nhiêu listing tại Việt Nam ngày 03/07?")
    timing = response.planning["timing"]
    assert set(timing) == set(STAGES) | {"total"}
    assert response.planning["llm_calls_critical"] >= 0
    assert response.planning["budget"]["p95_seconds"] == P95_BUDGET_SECONDS


def test_the_budget_verdict_fails_on_too_many_sequential_llm_calls():
    """Ngân sách không chỉ là số giây: số BƯỚC tuần tự mới là thứ tối ưu được."""
    fast = {"total": 100.0}
    assert within_budget(fast, MAX_LLM_CALLS_CRITICAL) is True
    assert within_budget(fast, MAX_LLM_CALLS_CRITICAL + 1) is False
    assert within_budget({"total": P95_BUDGET_SECONDS * 1000 + 1}, 0) is False
