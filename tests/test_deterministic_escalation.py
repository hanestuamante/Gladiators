"""W7 — thang leo thang rủi ro không áp cho plan tất định (SolutionSpec2808 §8).

Thang leo thang tồn tại để review một plan do **mô hình ngôn ngữ** viết: các yếu
tố của nó (``schema_linking``, ``entity_margin``, ``new_metric``) đều là bất định
của bước ánh xạ chữ→ký hiệu. Một plan do ``DeterministicPlanSynthesizer`` sinh
không chứa output nào của mô hình — đưa nó cho một critic (bản thân critic là một
mô hình) không thêm thông tin nào về nó.

Cái duy nhất đẩy bốn câu "shop chính hãng" qua ngưỡng là việc plan có một node
``Join`` **đã được chứng nhận** — đúng thứ mà cả tầng relation registry tồn tại
để cho phép.
"""
from __future__ import annotations

import pytest

from gladiators.agent.workflow import AgentRuntime
from gladiators.planner.risk import (
    EscalationConfig,
    deterministic_plan_is_acceptable,
    score_plan,
)
from gladiators.planner.semantic_parser import DeterministicSemanticParser
from gladiators.planner.synthesizer import synthesize

PARSER = DeterministicSemanticParser()
OFFICIAL_SHOP_VN = "Có bao nhiêu listing của shop chính hãng tại Việt Nam ngày 03/07?"


@pytest.fixture(scope="module")
def runtime() -> AgentRuntime:
    return AgentRuntime()


def _joined_plan():
    """Plan tất định thật, một join đã chứng nhận — không phải plan dựng tay."""
    result = synthesize(PARSER.parse(OFFICIAL_SHOP_VN, "vi", "vn"), "vn")
    assert result is not None, "câu này phải sinh được plan tất định"
    assert any(node.op == "Join" for node in result.plan.nodes)
    return result.plan


# --- vị từ chấp nhận -------------------------------------------------------

def test_a_deterministic_plan_with_one_certified_join_is_allowed():
    plan = _joined_plan()
    acceptable, reason = deterministic_plan_is_acceptable(plan)
    assert acceptable, reason
    risk = score_plan(plan, plan_provenance="deterministic_synthesis")
    assert risk.allowed is True
    assert risk.effective_mode == "single"
    # Điểm và factor vẫn được tính nguyên vẹn — chúng là quan sát, và bỏ chúng
    # đi thì không ai đo được vị từ có đang che một plan đáng ngờ hay không.
    assert risk.score >= 3
    assert risk.requested_mode in {"critic", "nversion"}


def test_the_same_plan_from_an_llm_is_still_blocked():
    """Thang cũ nguyên vẹn: xuất xứ là thứ duy nhất khác nhau giữa hai ca này."""
    risk = score_plan(_joined_plan(), plan_provenance="llm_ir")
    assert risk.allowed is False
    assert risk.effective_mode == "blocked"


def test_the_default_provenance_keeps_todays_behaviour():
    """Mặc định ``llm_ir`` ⇒ mọi call site chưa cập nhật không đổi hành vi."""
    assert score_plan(_joined_plan()).allowed is False


def test_an_invalid_plan_never_passes_the_predicate():
    plan = _joined_plan()
    broken = plan.model_copy(update={"output_node": "khong_ton_tai"})
    acceptable, reason = deterministic_plan_is_acceptable(broken)
    assert not acceptable
    assert reason == "plan_invalid"


def test_a_fanout_relation_without_dedupe_before_aggregate_is_blocked():
    """Điều kiện 4 — INV-DEDUPE-BEFORE-AGGREGATE.

    Fanout rồi tổng hợp là đếm trùng, và một con số đếm trùng trông giống hệt
    một con số đúng.
    """
    from gladiators.domain.relations import RELATIONS

    fanout = next(
        (name for name, spec in RELATIONS.items()
         if spec.fanout_effect != "none" and spec.binding is not None),
        None,
    )
    if fanout is None:
        pytest.skip("registry hiện không có relation fanout nào có binding")
    plan = _joined_plan()
    nodes = tuple(
        node.model_copy(update={"relation": fanout}) if node.op == "Join" else node
        for node in plan.nodes
    )
    has_aggregate = any(node.op == "Aggregate" for node in nodes)
    if not has_aggregate:
        pytest.skip("plan mẫu không có Aggregate nên điều kiện 4 không áp")
    acceptable, reason = deterministic_plan_is_acceptable(
        plan.model_copy(update={"nodes": nodes}),
    )
    assert not acceptable
    assert reason.startswith(("fanout_khong_dedupe", "relation_chua_chung_nhan",
                              "duong_quan_he_khong_dai_mot", "plan_invalid"))


def test_a_static_relation_over_two_days_is_blocked():
    """Điều kiện 5 — enrichment tĩnh dùng như panel theo ngày.

    Mỗi ngày nhận đúng cùng một giá trị, và bảng kết quả trông như một chuỗi
    thời gian thật.
    """
    from gladiators.domain.relations import RELATIONS

    plan = _joined_plan()
    joins = [node for node in plan.nodes if node.op == "Join"]
    if not any(
        RELATIONS[node.relation].temporal_validity == "static_latest_only"
        for node in joins if node.relation in RELATIONS
    ):
        pytest.skip("plan mẫu không dùng relation static_latest_only")
    widened = plan.model_copy(update={"time_scope": ("2026-07-01", "2026-07-03")})
    acceptable, reason = deterministic_plan_is_acceptable(widened)
    assert not acceptable
    assert reason.startswith(("static_latest_only", "plan_invalid"))


# --- qua runtime -----------------------------------------------------------

@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Có bao nhiêu shop chính hãng tại Việt Nam ngày 03/07?", 7),
        ("Có bao nhiêu listing của shop chính hãng tại Việt Nam ngày 03/07?", 465),
        ("Có bao nhiêu shop chính hãng tại Indonesia ngày 03/07?", 9),
        ("Có bao nhiêu listing của shop chính hãng tại Indonesia ngày 03/07?", 471),
    ],
)
def test_the_official_shop_questions_are_answered(question, expected, runtime):
    """§8.7 — bốn câu này SINH plan đúng và cho đúng đáp án từ trước W7; thứ
    duy nhất chặn chúng là thang leo thang."""
    response = runtime.run(question)
    assert response.gate.action == "allow", response.gate.rule_id
    assert expected in [item.value for item in response.evidence]


def test_the_bypass_counter_fires_only_when_the_predicate_unlocks(runtime):
    """Khoá đếm (§8.5): "vị từ đã mở khoá 4 câu" và "vị từ chưa bao giờ chạy"
    là hai bảng số giống hệt nhau nếu không đếm số lần nhánh thật sự bắn."""
    unlocked = runtime.run(OFFICIAL_SHOP_VN)
    assert unlocked.planning["risk"]["deterministic_bypass"]["applied"] is True
    assert unlocked.planning["risk"]["provenance"] == "deterministic_synthesis"

    # Câu tất định KHÔNG cần bypass (điểm dưới ngưỡng) vẫn phải báo applied
    # đúng theo nghĩa "vị từ đã mở khoá", chứ không phải "câu này chạy được".
    plain = runtime.run("Có bao nhiêu listing tại Việt Nam ngày 03/07?")
    assert plain.gate.action == "allow"
    assert plain.planning["risk"]["provenance"] != "llm_ir"


def test_the_flat_keys_and_the_risk_object_never_disagree(runtime):
    """W7.3: hai biểu diễn phải đến từ cùng một ``QueryRiskResult``."""
    planning = runtime.run(OFFICIAL_SHOP_VN).planning
    risk = planning["risk"]
    assert risk["score"] == planning["risk_score"]
    assert risk["requested_mode"] == planning["requested_escalation"]
    assert risk["effective_mode"] == planning["escalation_mode"]


def test_the_critic_flag_stays_off_in_source():
    """§8.7: W7 KHÔNG bật critic — nó thay một thang bằng một vị từ tất định."""
    assert EscalationConfig().enable_critic is False
    assert EscalationConfig().enable_nversion is False
