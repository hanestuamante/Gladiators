"""voucher_profile_rank_v1 (V2 §2.8, T-11) — L4 descriptive ranking, không causal."""
from __future__ import annotations

import pytest

from gladiators.agent.parser import MultilingualIntentParser
from gladiators.agent.wording import check_wording
from gladiators.agent.workflow import AgentRuntime
from gladiators.analytics.tools import AnalyticsTools
from gladiators.domain.intent_registry import default_registry
from gladiators.domain.metrics import METRICS
from gladiators.planner.macros import default_macro_registry

QUESTION = "Shop nào có chiến lược voucher hiệu quả nhất VN?"


# ---- routing ----

def test_parser_routes_l4_voucher_question_to_new_intent():
    request = MultilingualIntentParser().parse(QUESTION, default_registry())
    assert request.intent == "voucher_profile_rank"
    assert request.country == "vn"


def test_parser_keeps_two_group_promo_question_unchanged():
    request = MultilingualIntentParser().parse(
        "Voucher ở VN có hiệu quả không?", default_registry(),
    )
    assert request.intent == "promotion_effectiveness"


# ---- governance T-11: mặc định OFF → A19-METRIC clarify ----

def test_flag_off_returns_a19_metric_clarify(tmp_path, monkeypatch):
    monkeypatch.delenv("GLADIATORS_ENABLE_VOUCHER_PROFILE", raising=False)
    response = AgentRuntime(trace_dir=tmp_path).run(QUESTION)
    assert response.gate.action == "clarify"
    assert response.gate.rule_id == "A19-METRIC"
    assert "voucher_profile_rank_v1" in response.gate.reason
    assert response.evidence == []


# ---- flag ON: chạy đủ contract ----

@pytest.fixture()
def served(tmp_path):
    return AgentRuntime(trace_dir=tmp_path, enable_voucher_profile=True).run(QUESTION)


def test_flag_on_serves_ranking_with_certified_evidence_contract(served):
    assert served.gate.action == "allow"
    macro = default_macro_registry().get("voucher_profile_rank")
    assert macro is not None  # đăng ký = đã qua Plan Validator
    assert macro.accepts_evidence([item.metric for item in served.evidence])
    assert served.verification["passed"] is True


def test_answer_is_descriptive_and_passes_wording_gate(served):
    assert "không đo hiệu quả nhân quả" in served.answer
    assert check_wording(served.answer) == []


def test_component_values_bounded_and_attrs_carry_definition(served):
    by_metric = {item.metric: item for item in served.evidence}
    assert 0.0 <= by_metric["voucher_rate"].value <= 1.0
    assert 0.0 <= by_metric["voucher_profile_score"].value <= 1.0
    assert by_metric["ranked_shop_count"].value >= 1
    top = by_metric["top_voucher_profile_shop_name"]
    assert top.attrs["definition"] == "voucher_profile_rank_v1"
    assert top.attrs["observational_only"] is True
    assert top.attrs["n_listings"] >= AnalyticsTools.VOUCHER_PROFILE_MIN_LISTINGS


def test_ranking_is_deterministic(tmp_path, served):
    rerun = AgentRuntime(trace_dir=tmp_path, enable_voucher_profile=True).run(QUESTION)
    first = {item.metric: item.value for item in served.evidence}
    second = {item.metric: item.value for item in rerun.evidence}
    assert first == second


def test_indonesia_without_structured_vouchers_abstains(tmp_path):
    response = AgentRuntime(trace_dir=tmp_path, enable_voucher_profile=True).run(
        "Toko mana punya strategi voucher terbaik di Indonesia?",
    )
    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A-NO-EVIDENCE"


# ---- metric registry governance ----

def test_metric_registry_contains_definition_with_pending_approval_caveat():
    spec = METRICS["voucher_profile_score"]
    assert spec.grain == "group"
    assert any("T-11" in caveat for caveat in spec.caveats)
    assert any("không đo hiệu quả nhân quả" in caveat for caveat in spec.caveats)
    assert sum(AnalyticsTools.VOUCHER_PROFILE_WEIGHTS.values()) == pytest.approx(1.0)
    assert set(AnalyticsTools.VOUCHER_PROFILE_WEIGHTS) == {
        "voucher_rate", "median_discount_ratio", "descriptive_gap_median_sold",
    }
