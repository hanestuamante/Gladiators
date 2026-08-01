"""Shadow routing on the live path — ultimate solution §6.5 / §8.11.

The whole value of shadow is that it observes without deciding, so the tests
that matter are the ones proving it cannot affect an answer: identical responses
with it on and off, and a broken observer that still lets a request through.
"""
from __future__ import annotations

import pytest

from gladiators.agent.workflow import AgentRuntime
from gladiators.planner.shadow import SHADOW_VERSION, ShadowObserver

QUESTIONS = (
    "Sản phẩm nào có giá thấp nhất tại VN?",
    "Có bao nhiêu listing tại VN theo từng shop?",
)


@pytest.fixture(scope="module")
def runtime() -> AgentRuntime:
    return AgentRuntime()


def shadow_of(response) -> dict | None:
    return (response.planning or {}).get("shadow")


# --- shadow runs ----------------------------------------------------------

def test_shadow_records_routing_on_the_live_path(runtime):
    """A component nothing calls is a component nobody is measuring."""
    observed = shadow_of(runtime.run(QUESTIONS[0]))
    assert observed is not None
    assert observed["shadow_version"] == SHADOW_VERSION
    assert observed["routing_mode"] in {
        "core_only", "topic_scoped", "multi_topic", "unknown", "overflow",
    }
    assert "shadow_error" not in observed


def test_shadow_reports_the_gate_is_closed(runtime):
    """§6.5: an ungated topic falls back to the legacy slice and says so.

    ``context_applied`` stays false so "shadow ran" is never mistaken for
    "shadow changed something".
    """
    observed = shadow_of(runtime.run(QUESTIONS[0]))
    assert observed["topic_gate_disabled"] is True
    assert observed["context_applied"] is False


def test_shadow_produces_the_metric_the_gate_is_waiting_for(runtime):
    """catalog_miss is the evidence for required-ref recall (§7.3)."""
    observed = shadow_of(runtime.run(QUESTIONS[0]))
    assert observed["catalog_miss_count"] == 0


# --- shadow does not decide ----------------------------------------------

def test_answers_are_identical_with_shadow_on_and_off():
    """The load-bearing property: observation must not move the answer."""
    on, off = AgentRuntime(), AgentRuntime()
    off.shadow = ShadowObserver(enabled=False)
    for question in QUESTIONS:
        a, b = on.run(question), off.run(question)
        assert a.gate.action == b.gate.action
        assert a.gate.rule_id == b.gate.rule_id
        assert [(e.metric, e.value) for e in a.evidence] == \
               [(e.metric, e.value) for e in b.evidence]


def test_a_broken_observer_does_not_break_the_request():
    """Shadow reports its own failures as data rather than raising them."""
    class Exploding(ShadowObserver):
        def _observe(self, *a, **k):
            raise RuntimeError("shadow hỏng")

    runtime = AgentRuntime()
    runtime.shadow = Exploding()
    response = runtime.run(QUESTIONS[0])
    assert response.gate.action == "allow"
    assert "shadow hỏng" in shadow_of(response)["shadow_error"]


def test_disabled_shadow_leaves_a_marker_not_a_gap(runtime):
    """Absent and switched-off are different states."""
    off = AgentRuntime()
    off.shadow = ShadowObserver(enabled=False)
    observed = shadow_of(off.run(QUESTIONS[0]))
    assert observed["shadow_enabled"] is False
    assert "routing_mode" not in observed


def test_shadow_latency_is_negligible(runtime):
    observed = shadow_of(runtime.run(QUESTIONS[0]))
    assert observed["shadow_latency_ms"] < 500
