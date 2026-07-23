"""Tests cho đợt chống-hallucination 21/07 (IMPLEMENTATION_HANDOFF mục 13)."""
from __future__ import annotations

import types

import pytest

from gladiators.agent.verifier import verify_numeric_claims
from gladiators.agent.wording import check_wording
from gladiators.contracts import Evidence, ResponseClaim
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


# ---- 13.7+ locale number normalization (thousands grouping bị tách thành nhiều token) ----

def test_verifier_merges_space_separated_thousands_grouping():
    ev = _ev("ev:t:0001", 298219517806.0)
    result = verify_numeric_claims("Tổng 298 219 517 806 VND [ev:t:0001]", [ev])
    assert result["passed"]
    assert result["unsupported"] == []


def test_verifier_merges_comma_separated_thousands_grouping():
    ev = _ev("ev:t:0001", 298219517806.0)
    result = verify_numeric_claims("Tổng 298,219,517,806 VND [ev:t:0001]", [ev])
    assert result["passed"]


def test_verifier_does_not_merge_comma_space_number_list():
    # "512, 431, 380" là DANH SÁCH số rời (comma+space), không phải một số —
    # không được gộp thành 512431380. Cả ba đều có evidence nên phải PASS.
    from gladiators.agent.verifier import _normalize_thousands_grouping
    assert _normalize_thousands_grouping("Top: 512, 431, 380 listing") == "Top: 512, 431, 380 listing"
    evs = [_ev("ev:t:0001", 512.0), _ev("ev:t:0002", 431.0), _ev("ev:t:0003", 380.0)]
    result = verify_numeric_claims(
        "Ba shop dẫn đầu: 512, 431, 380 listing "
        "[ev:t:0001][ev:t:0002][ev:t:0003].", evs,
    )
    assert result["passed"]
    assert result["unsupported"] == []


def test_verifier_still_rejects_single_group_decimal_ambiguity():
    # "745.078" chỉ có 1 nhóm-3-chữ-số — vẫn coi là số thập phân, KHÔNG gộp
    # thành 745078, giữ nguyên hành vi display-rounding cũ.
    ev = _ev("ev:t:0001", 745.077922)
    assert not verify_numeric_claims("Giá trị 750 [ev:t:0001]", [ev])["passed"]


def test_verifier_accepts_date_with_alternate_separator():
    ev = _ev("ev:t:0001", "2026-07-03")
    result = verify_numeric_claims("Ngày cao nhất là 2026/07/03 [ev:t:0001]", [ev])
    assert result["passed"]


def test_verifier_accepts_typographic_dash_and_narrow_space():
    # LLM Groq đôi khi sinh dau gach noi khong ngat dong (U+2011) va khoang
    # trang hep (U+202F) thay vi ASCII thuong.
    date_ev = _ev("ev:t:0001", "2026-07-03")
    amount_ev = _ev("ev:t:0002", 298219517806.0)
    text = (
        "Ngay cao nhat la 2026" + chr(0x2011) + "07" + chr(0x2011) + "03 [ev:t:0001]"
        + " voi tong 298" + chr(0x202F) + "219" + chr(0x202F) + "517" + chr(0x202F)
        + "806 VND [ev:t:0002]"
    )
    result = verify_numeric_claims(text, [date_ev, amount_ev])
    assert result["passed"]
    assert result["unsupported"] == []


# ---- 22/07 W2 per-claim value/unit/path/citation binding ----

def _claim(evidence_id="ev:t:0001", *, unit="VND", path="value", text=None):
    text = text or f"Giá trị 10 {unit} [{evidence_id}]."
    return ResponseClaim(
        claim_id="cl:test:0001", text=text, claim_type="money", value=10,
        unit=unit, evidence_id=evidence_id, evidence_path=path,
    )


def test_per_claim_wrong_unit_fails_even_when_value_and_citation_match():
    ev = Evidence(
        evidence_id="ev:t:0001", source_tier="btc_dataset", metric="price", value=10,
        unit="VND", source_locator=SourceLocator(kind="internal", value="x"), dataset_version="v1",
    )
    answer = "Giá trị 10 IDR [ev:t:0001]."
    result = verify_numeric_claims(answer, [ev], claims=(_claim(unit="IDR", text=answer),), require_claims=True)
    assert result["passed"] is False
    assert any(gap["reason"] == "unit_mismatch" for gap in result["claim_binding_gaps"])


def test_per_claim_wrong_path_fails_even_when_value_is_identical():
    ev = Evidence(
        evidence_id="ev:t:0001", source_tier="btc_dataset", metric="price", value=10,
        unit="VND", attrs={"duplicate": 10},
        source_locator=SourceLocator(kind="internal", value="x"), dataset_version="v1",
    )
    answer = "Giá trị 10 VND [ev:t:0001]."
    result = verify_numeric_claims(
        answer, [ev], claims=(_claim(path="attrs.duplicate", text=answer),), require_claims=True,
    )
    assert result["passed"] is False
    assert any(gap["reason"] == "path_not_claimable" for gap in result["claim_binding_gaps"])


def test_per_claim_correct_binding_passes():
    ev = Evidence(
        evidence_id="ev:t:0001", source_tier="btc_dataset", metric="price", value=10,
        unit="VND", source_locator=SourceLocator(kind="internal", value="x"), dataset_version="v1",
    )
    answer = "Giá trị 10 VND [ev:t:0001]."
    result = verify_numeric_claims(answer, [ev], claims=(_claim(text=answer),), require_claims=True)
    assert result["passed"] is True


def test_strict_claim_mode_does_not_ignore_digits_in_string_evidence():
    ev = _ev("ev:t:0001", "Campaign 7.7 starts 2026-07-01")
    result = verify_numeric_claims(
        "Campaign 7.7 starts 2026-07-01 [ev:t:0001].", [ev], require_claims=True,
    )
    assert result["passed"] is False
    assert result["claim_binding_gaps"] == [
        {"claim_id": "", "reason": "missing_claim:ev:t:0001"}
    ]


def test_per_claim_missing_bound_citation_fails():
    ev = Evidence(
        evidence_id="ev:t:0001", source_tier="btc_dataset", metric="price", value=10,
        unit="VND", source_locator=SourceLocator(kind="internal", value="x"), dataset_version="v1",
    )
    answer = "Giá trị 10 VND."
    result = verify_numeric_claims(
        answer, [ev], claims=(_claim(text=answer),), require_claims=True,
    )
    assert result["passed"] is False
    assert any(gap["reason"] == "missing_bound_citation" for gap in result["claim_binding_gaps"])


def test_final_deterministic_verification_failure_abstains(monkeypatch, tmp_path):
    from gladiators.agent.workflow import AgentRuntime

    monkeypatch.setattr("gladiators.agent.workflow.verify_numeric_claims", lambda *a, **k: {
        "passed": False, "coverage": 0.0, "unsupported": [], "unknown_citations": [],
        "tier_mixing": [], "provenance_gaps": [], "source_label_gaps": [],
        "claim_binding_gaps": [{"claim_id": "", "reason": "forced_test_failure"}],
    })
    response = AgentRuntime(trace_dir=tmp_path).run("Có bao nhiêu listing tại VN?")
    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A-VERIFICATION-FINAL"
    assert response.evidence == []


# ---- 13.2.4 wording gate ----

@pytest.mark.parametrize("answer,expect_violation", [
    ("Voucher làm tăng doanh số", True),
    ("Đây là tương quan nhóm, không chứng minh khuyến mãi gây ra thay đổi.", False),
    ("Doanh thu ngày 03/07 là 5000000 VND", True),
    ("Tổng doanh thu proxy ước tính là 5000000", False),
    ("Sản phẩm này cùng mẫu với listing kia", True),
    ("Không khẳng định cùng mẫu hoặc cùng SKU.", False),
    ("Tháng sau sẽ tăng mạnh", True),
    # Bug 22/07: đại từ "nó" fold thành "no" từng scrub oan mệnh đề nhân quả phía sau.
    ("Voucher — nó làm tăng doanh số 20%.", True),
    # "nốt" fold thành "not" — cũng không được nuốt mệnh đề nhân quả.
    ("Xử lý nốt phần còn lại, chương trình làm tăng doanh số.", True),
    # Negator tiếng Anh "no" vẫn phải scrub được mệnh đề nhân quả (folded) theo sau.
    ("Chỉ là tương quan, no bằng chứng voucher làm tăng doanh số.", False),
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


def test_groq_structured_empty_response_retries_without_response_format(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("GROQ_PARSE_API_KEY", raising=False)
    monkeypatch.setattr("gladiators.agent.llm.load_dotenv", lambda: None)
    from pydantic import BaseModel
    from gladiators.agent.llm import GroqLLMClient

    class TinySchema(BaseModel):
        value: int

    client = GroqLLMClient(model="openai/gpt-oss-120b")

    def _resp(content):
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))],
            usage=None,
        )

    formats = []

    def fake_complete(_client, _model, _prompt, response_format, _reasoning):
        formats.append(response_format)
        return _resp("" if len(formats) == 1 else '{"value": 1}')

    monkeypatch.setattr(client, "_complete", fake_complete)
    out = client._chat("structured", "fixture", TinySchema)
    assert out == '{"value": 1}'
    assert formats[0] is not None and formats[1] is None
    assert client.telemetry().get("empty_retries") == 1
