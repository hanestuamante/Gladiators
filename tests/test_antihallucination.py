"""Tests cho đợt chống-hallucination 21/07 (IMPLEMENTATION_HANDOFF mục 13)."""
from __future__ import annotations

import types

import pytest

from gladiators.agent.verifier import verify_numeric_claims
from gladiators.agent.wording import check_wording
from gladiators.contracts import Evidence
from gladiators.external.contracts import SourceLocator
from gladiators.planner.analytical import build_analytical_plan
from gladiators.planner.critic import PlanCritic
from gladiators.planner.consensus import ConsensusError, NVersionResolver
from gladiators.planner.semantic_parser import (
    AnalyticalRanking, AnalyticalRequest, AnalyticalTimeScope, SemanticBinding,
)
from gladiators.data.repository import ArtifactRepository


def _ev(eid: str, value, **attrs) -> Evidence:
    return Evidence(
        evidence_id=eid, source_tier="btc_dataset", metric="x", value=value,
        source_locator=SourceLocator(kind="internal", value="x"), dataset_version="v1", attrs=attrs,
    )


# ---- 13.2.1 display-rounding tolerance ----

def test_verifier_rejects_close_but_wrong_number():
    ev = _ev("ev:t:0001", 745.077922)
    # 750 chênh 0,67% — tolerance 1,1% cũ cho pass; display-rounding chặn.
    assert not verify_numeric_claims("Giá trị 750 [ev:t:0001]", [ev])["passed"]


def test_verifier_accepts_correctly_rounded_number():
    ev = _ev("ev:t:0001", 745.077922)
    assert verify_numeric_claims("Giá trị 745.08 [ev:t:0001]", [ev])["passed"]
    assert verify_numeric_claims("Giá trị 745 [ev:t:0001]", [ev])["passed"]


# ---- 13.2.2 fake citation ----

def test_verifier_blocks_fabricated_citation():
    ev = _ev("ev:t:0001", 745.077922)
    result = verify_numeric_claims("Giá trị 745.08 [ev:fake:0007]", [ev])
    assert not result["passed"]
    assert result["unknown_citations"] == ["ev:fake:0007"]


# ---- 13.2.3 string evidence values không bị chấm là số bịa ----

def test_verifier_ignores_digits_inside_string_evidence_values():
    shop = _ev("ev:t:0002", "Glad2Glow Official Store")
    result = verify_numeric_claims("Shop là Glad2Glow Official Store [ev:t:0002]", [shop])
    assert result["passed"]


# ---- 13.2.4 wording gate ----

@pytest.mark.parametrize("answer,expect_violation", [
    ("Voucher làm tăng doanh số", True),
    ("Đây là tương quan nhóm, không chứng minh khuyến mãi gây ra thay đổi.", False),
    ("Doanh thu ngày 03/07 là 5000000 VND", True),
    ("Tổng doanh thu proxy ước tính là 5000000", False),
    ("Sản phẩm này cùng mẫu với listing kia", True),
    ("Không khẳng định cùng mẫu hoặc cùng SKU.", False),
    ("Tháng sau sẽ tăng mạnh", True),
])
def test_wording_gate_cases(answer, expect_violation):
    assert bool(check_wording(answer)) is expect_violation


# ---- 13.2.6 critic lọc issue verifiably-false ----

def _valid_top_shop_plan():
    return build_analytical_plan("top_shop_by_listing_count", "vn")


class _CriticClient:
    provider, model, prompt_version = "test", "critic", "p9-test"

    def __init__(self, issues):
        self._issues = issues

    def critique_plan(self, question, payload):
        return {"issues": self._issues}


def test_critic_drops_deterministic_covered_issue_on_valid_plan():
    plan = _valid_top_shop_plan()
    client = _CriticClient([{"code": "missing_semantic_object", "node_id": "n1",
                             "message": "entity.shop không map (phán đoán sai)"}])
    review = PlanCritic(client).review("Shop nào nhiều listing nhất VN?", plan)
    assert review.issues == ()          # không chặn plan đúng
    assert len(review.dropped) == 1     # ghi lại issue sai kiểm chứng được


def test_critic_drops_issue_pointing_at_nonexistent_node():
    plan = _valid_top_shop_plan()
    client = _CriticClient([{"code": "grain_mismatch", "node_id": "n99",
                             "message": "node không tồn tại"}])
    review = PlanCritic(client).review("Shop nào nhiều listing nhất VN?", plan)
    assert review.issues == ()
    assert len(review.dropped) == 1


def test_critic_keeps_real_semantic_issue():
    plan = _valid_top_shop_plan()
    client = _CriticClient([{"code": "grain_mismatch", "node_id": "n4",
                             "message": "Aggregate grain chưa đủ rõ."}])
    review = PlanCritic(client).review("Shop nào nhiều listing nhất VN?", plan)
    assert len(review.issues) == 1      # nhóm semantic ngoài khả năng kiểm cơ học → giữ
    assert review.issues[0].code == "grain_mismatch"
    assert review.dropped == ()


# ---- 13.2.7 adjudicator fail-closed khi thiếu reason_issue_type ----

def _price_request():
    return AnalyticalRequest(
        normalized_question="gia san pham theo xep hang vn", language="vi",
        requested_measures=(SemanticBinding(surface_text="giá", ref="measure.price"),),
        requested_dimensions=(SemanticBinding(surface_text="sản phẩm", ref="dim.product_name"),),
        filters=(), time_scope=AnalyticalTimeScope(dates=("2026-07-03",), mode="single_snapshot"),
        grouping=(), ranking=AnalyticalRanking(order_by="measure.price", top_k=1),
        requested_grain="group", analytical_operators=("filter", "rank"),
        requested_output_shape="ranking",
    )


def test_adjudicator_without_reason_is_fail_closed():
    primary = build_analytical_plan("highest_price_listing", "vn")
    alternate = primary.model_copy(update={
        "plan_id": "open:alternate_lowest_price",
        "nodes": tuple(
            node.model_copy(update={"descending": False}) if node.op == "Rank" else node
            for node in primary.nodes
        ),
    })

    class AlternateAndJudgeNoReason:
        def plan_analytical_alternate(self, payload):
            return alternate.model_dump(mode="json")

        def adjudicate_plans(self, payload):
            # Chọn phe nhưng KHÔNG nêu reason_issue_type → không kiểm được.
            return {"verdict": "alternate", "reason_issue_type": None, "detail": "không lý do"}

    client = AlternateAndJudgeNoReason()
    resolver = NVersionResolver(ArtifactRepository("data/processed"), client, client)
    with pytest.raises(ConsensusError, match="reason_issue_type"):
        resolver.resolve("Giá sản phẩm theo xếp hạng tại VN", _price_request(), "vn", primary)


# ---- 13.2.8 Groq empty-response bounded retry ----

def test_groq_retries_once_on_empty_response(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("GROQ_PARSE_API_KEY", raising=False)
    monkeypatch.setattr("gladiators.agent.llm.load_dotenv", lambda: None)
    from gladiators.agent.llm import GroqLLMClient

    client = GroqLLMClient(model="openai/gpt-oss-120b")

    def _resp(content):
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))],
            usage=None,
        )

    calls = {"n": 0}

    def fake_complete(*args, **kwargs):
        calls["n"] += 1
        return _resp("" if calls["n"] == 1 else "Câu trả lời thật.")

    monkeypatch.setattr(client, "_complete", fake_complete)
    out = client.generate({"deterministic_answer": "x"})
    assert out == "Câu trả lời thật."
    assert calls["n"] == 2
    assert client.telemetry().get("empty_retries") == 1
