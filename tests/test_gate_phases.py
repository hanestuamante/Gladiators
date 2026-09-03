"""Gate phases and issue collection — ultimate solution §4.5."""
from __future__ import annotations

import pytest

from gladiators.agent.gate import PHASE_REGISTRY_VERSION
from gladiators.agent.workflow import AgentRuntime


@pytest.fixture(scope="module")
def runtime(tmp_path_factory) -> AgentRuntime:
    return AgentRuntime(trace_dir=tmp_path_factory.mktemp("gate-phases"))


def test_phase_registry_is_versioned():
    # §4.5: "Phase/priority registry có version và ADR."
    assert PHASE_REGISTRY_VERSION


def test_a_clean_request_records_the_phases_it_passed(runtime):
    decision = runtime.run("Có bao nhiêu listing ở VN?").gate
    assert decision.action == "allow"
    assert decision.issues == ()
    assert decision.selected_issue_id is None
    # Evaluation did not stop at the first phase just because nothing was wrong.
    assert len(decision.evaluated_phases) > 1


def test_every_issue_is_collected_not_just_the_first(runtime):
    # This question trips the route-level currency rule and the measure-level one.
    # The early-return chain could only ever report whichever fired first.
    decision = runtime.run("So sánh giá trung bình giữa Việt Nam và Indonesia").gate
    assert decision.action == "clarify"
    assert len(decision.issues) > 1
    assert decision.selected_issue_id == "A16-CROSS-CURRENCY"
    assert {issue.detail.category for issue in decision.issues} == {"currency"}


def test_selected_issue_is_the_highest_priority_one(runtime):
    decision = runtime.run("So sánh giá trung bình giữa Việt Nam và Indonesia").gate
    best = min(decision.issues, key=lambda issue: issue.priority)
    assert decision.selected_issue_id == best.rule_id
    assert decision.reason == best.reason
    assert decision.action == best.action


def test_a_capability_block_is_terminal(runtime):
    # §4.5: later phases may be skipped only for a terminal capability block.
    decision = runtime.run("Lợi nhuận shop nào cao nhất?").gate
    assert decision.action == "abstain"
    assert decision.selected_issue_id == "A-MISSING-PROFIT"
    assert decision.issues[0].detail.category == "capability"
    assert decision.evaluated_phases == (1,)


def test_missing_slot_is_evaluated_last_so_it_cannot_mask_other_issues(runtime):
    # §4.5: "Country slot không được che out-of-scope, rolling-window hoặc
    # fanout issue." Slot checks live in the last phase, so anything found
    # earlier keeps a lower priority number and wins selection.
    decision = runtime.run("So sánh giá trung bình giữa Việt Nam và Indonesia").gate
    slot_issues = [i for i in decision.issues if i.detail.category == "slot"]
    other = [i for i in decision.issues if i.detail.category != "slot"]
    for slot_issue in slot_issues:
        assert all(slot_issue.priority > item.priority for item in other)
        assert slot_issue.phase == 6


def test_issue_detail_carries_a_typed_category_and_code(runtime):
    decision = runtime.run("Dự báo doanh số tuần sau tại VN?").gate
    assert decision.issues
    for issue in decision.issues:
        assert issue.detail.category in {
            "capability", "entity", "grain", "fanout",
            "currency", "alignment", "security", "slot", "route",
        }
        assert issue.detail.code
        assert issue.phase >= 1 and issue.priority >= 1
