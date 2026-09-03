"""Mutation tests — scorer/oracle của benchmark accuracy v1 PHẢI đỏ được.

TC_formulation §7: "một scorer không đỏ được khi kỳ vọng sai là một scorer
không tồn tại". Mỗi test lật đúng MỘT chiều ngữ nghĩa của một case đã pass và
khẳng định strict_pass chuyển False vì đúng lý do đó.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

from run_accuracy_benchmark import score_case  # noqa: E402


class _Gate:
    def __init__(self, action="allow", rule_id="A-ALLOW", reason="",
                 answerable_alternative=""):
        self.action, self.rule_id = action, rule_id
        self.reason, self.answerable_alternative = reason, answerable_alternative


class _Evidence:
    def __init__(self, metric, value, unit=None, attrs=None, evidence_id="ev:x:1"):
        self.metric, self.value, self.unit = metric, value, unit
        self.attrs = attrs or {}
        self.evidence_id = evidence_id


class _Response:
    def __init__(self, gate, evidence, answer, verified=True):
        self.gate, self.evidence, self.answer = gate, evidence, answer
        self.verification = {"passed": verified}


def _base_case(**overrides):
    case = {
        "id": "acc-v1-9999", "split": "dev",
        "answerability": "directly_answerable",
        "expected_action": "allow", "accepted_actions": ["allow"],
        "expected_clarification_slots": [],
        "expected_refusal_reason_class": None,
        "forbidden_values": [],
        "expected_facts": [{
            "metric": "listing_count", "oracle_fact_key": "listing_count",
            "value": 668, "value_type": "integer", "unit": "listings",
            "country": "vn", "date_start": "2026-07-03",
            "date_end": "2026-07-03", "grain": "listing", "group": None,
            "filters": [], "tolerance": {"kind": "exact", "value": 0},
        }],
    }
    case.update(overrides)
    return case


def _good_response():
    return _Response(
        _Gate("allow"),
        [_Evidence("listing_count", 668, "listings",
                   {"country": "vn", "observed_date": "2026-07-03"})],
        "Có 668 listing [ev:x:1] tại VN ngày 2026-07-03.",
    )


def test_the_happy_path_passes():
    row = score_case(_base_case(), [_good_response()])
    assert row["strict_pass"], row["reasons"]


def test_wrong_action_fails():
    response = _good_response()
    response.gate = _Gate("abstain", "A19-PLAN")
    assert not score_case(_base_case(), [response])["strict_pass"]


def test_wrong_numeric_value_fails():
    response = _Response(
        _Gate("allow"),
        [_Evidence("listing_count", 670, "listings",
                   {"country": "vn", "observed_date": "2026-07-03"})],
        "Có 670 listing [ev:x:1].",
    )
    row = score_case(_base_case(), [response])
    assert not row["strict_pass"]
    assert any("kỳ vọng" in r for r in row["reasons"])


def test_same_number_under_a_different_metric_fails():
    """"Metric khác nhưng tình cờ cùng số là fail" — nguyên văn §8."""
    response = _Response(
        _Gate("allow"),
        [_Evidence("rating_count", 668, "ratings",
                   {"country": "vn", "observed_date": "2026-07-03"})],
        "Có 668 [ev:x:1].",
    )
    row = score_case(_base_case(), [response])
    assert not row["strict_pass"]
    assert any("không có evidence metric" in r for r in row["reasons"])


def test_wrong_country_scope_fails():
    response = _Response(
        _Gate("allow"),
        [_Evidence("listing_count", 668, "listings",
                   {"country": "id", "observed_date": "2026-07-03"})],
        "Có 668 listing [ev:x:1].",
    )
    assert not score_case(_base_case(), [response])["strict_pass"]


def test_wrong_date_scope_fails():
    response = _Response(
        _Gate("allow"),
        [_Evidence("listing_count", 668, "listings",
                   {"country": "vn", "observed_date": "2026-07-01"})],
        "Có 668 listing [ev:x:1].",
    )
    assert not score_case(_base_case(), [response])["strict_pass"]


def test_a_value_only_in_evidence_but_not_displayed_fails():
    response = _Response(
        _Gate("allow"),
        [_Evidence("listing_count", 668, "listings",
                   {"country": "vn", "observed_date": "2026-07-03"})],
        "Kết quả nằm trong bảng đính kèm [ev:x:1].",
    )
    row = score_case(_base_case(), [response])
    assert not row["strict_pass"]
    assert any("không hiển thị" in r for r in row["reasons"])


def test_a_displayed_value_without_citation_fails():
    response = _Response(
        _Gate("allow"),
        [_Evidence("listing_count", 668, "listings",
                   {"country": "vn", "observed_date": "2026-07-03"})],
        "Có 668 listing.",
    )
    row = score_case(_base_case(), [response])
    assert not row["strict_pass"]
    assert any("trích dẫn" in r for r in row["reasons"])


def test_verifier_failure_fails_the_case():
    response = _good_response()
    response.verification = {"passed": False}
    assert not score_case(_base_case(), [response])["strict_pass"]


def test_a_forbidden_sentinel_value_fails():
    case = _base_case(forbidden_values=[999999999.0])
    response = _Response(
        _Gate("allow"),
        [_Evidence("listing_count", 668, "listings",
                   {"country": "vn", "observed_date": "2026-07-03"}),
         _Evidence("price", 999999999.0, "IDR",
                   {"country": "vn", "observed_date": "2026-07-03"},
                   evidence_id="ev:x:2")],
        "Có 668 listing [ev:x:1], giá đỉnh 999999999 [ev:x:2].",
    )
    row = score_case(case, [response])
    assert not row["strict_pass"]
    assert any("bị cấm" in r for r in row["reasons"])


def test_a_unique_name_claim_on_a_real_tie_fails():
    case = _base_case(expected_facts=[
        {"metric": "max_images", "oracle_fact_key": "max_images", "value": 9,
         "value_type": "integer", "unit": "images", "country": "vn",
         "date_start": "2026-07-03", "date_end": "2026-07-03",
         "grain": "listing", "group": None, "filters": [],
         "tolerance": {"kind": "exact", "value": 0}},
        {"metric": "tie_count", "oracle_fact_key": "tie_count", "value": 76,
         "value_type": "integer", "unit": "listings", "country": "vn",
         "date_start": "2026-07-03", "date_end": "2026-07-03",
         "grain": "listing", "group": None, "filters": [],
         "tolerance": {"kind": "exact", "value": 0}},
    ], accepted_actions=["allow", "clarify", "abstain"])
    response = _Response(
        _Gate("allow"),
        [_Evidence("images_count", 9, "images",
                   {"country": "vn", "observed_date": "2026-07-03"})],
        "Listing X có nhiều ảnh nhất với 9 ảnh [ev:x:1].",
    )
    row = score_case(case, [response])
    assert not row["strict_pass"]
    assert any("không duy nhất" in r or "hoà" in r for r in row["reasons"])


def test_tolerance_is_per_metric_not_a_blanket_half():
    case = _base_case(expected_facts=[{
        "metric": "median_rating", "oracle_fact_key": "median_rating",
        "value": 4.9236, "value_type": "decimal", "unit": "stars",
        "country": "vn", "date_start": "2026-07-03", "date_end": "2026-07-03",
        "grain": "listing", "group": None, "filters": [],
        "tolerance": {"kind": "absolute", "value": 0.005},
    }])
    response = _Response(
        _Gate("allow"),
        [_Evidence("rating", 4.7, "stars",
                   {"country": "vn", "observed_date": "2026-07-03",
                    "aggregation": "median"})],
        "Điểm trung vị là 4.7 [ev:x:1].",
    )
    # 4.7 lệch 0.22 — dưới ngưỡng ±0.5 cũ nhưng vượt tolerance khai theo metric.
    assert not score_case(case, [response])["strict_pass"]


def test_a_median_answer_to_a_mean_question_fails_by_aggregation():
    case = _base_case(expected_facts=[{
        "metric": "mean_images", "oracle_fact_key": "mean_images",
        "value": 5.66, "value_type": "decimal", "unit": "images",
        "country": "vn", "date_start": "2026-07-03", "date_end": "2026-07-03",
        "grain": "listing", "group": None, "filters": [],
        "tolerance": {"kind": "absolute", "value": 0.01},
    }])
    response = _Response(
        _Gate("allow"),
        [_Evidence("images_count", 5.66, "images",
                   {"country": "vn", "observed_date": "2026-07-03",
                    "aggregation": "median"})],
        "Trung bình 5.66 ảnh [ev:x:1].",
    )
    row = score_case(case, [response])
    assert not row["strict_pass"]
    assert any("aggregation" in r for r in row["reasons"])


def test_answering_a_truly_ambiguous_question_fails():
    case = _base_case(
        answerability="needs_clarification", expected_action="clarify",
        accepted_actions=["clarify"], expected_facts=[],
        expected_clarification_slots=["country"],
    )
    row = score_case(case, [_good_response()])
    assert not row["strict_pass"]
    assert any("đoán" in r or "∉" in r for r in row["reasons"])


def test_a_generic_clarify_that_misses_the_slot_fails():
    case = _base_case(
        answerability="needs_clarification", expected_action="clarify",
        accepted_actions=["clarify"], expected_facts=[],
        expected_clarification_slots=["voucher_definition"],
    )
    response = _Response(
        _Gate("clarify", "A-MISSING-SLOT", reason="Câu hỏi chưa đủ thông tin."),
        [], "Bạn có thể nói rõ hơn không?",
    )
    row = score_case(case, [response])
    assert not row["strict_pass"]
    assert any("slot" in r for r in row["reasons"])


def test_allowing_an_unanswerable_question_fails():
    case = _base_case(
        answerability="unanswerable", expected_action="abstain",
        accepted_actions=["abstain", "clarify"], expected_facts=[],
        expected_refusal_reason_class="missing_field",
    )
    row = score_case(case, [_good_response()])
    assert not row["strict_pass"]


def test_a_refusal_with_the_wrong_reason_class_fails():
    case = _base_case(
        answerability="unanswerable", expected_action="abstain",
        accepted_actions=["abstain", "clarify"], expected_facts=[],
        expected_refusal_reason_class="missing_field",
    )
    response = _Response(
        _Gate("abstain", "A16-CROSS-CURRENCY", reason="Không trộn tiền tệ."),
        [], "Không thể trả lời.",
    )
    row = score_case(case, [response])
    assert not row["strict_pass"]
    assert any("sai nhóm lý do" in r for r in row["reasons"])


# --- oracle mutation --------------------------------------------------------

def test_the_oracle_verify_goes_red_on_a_doctored_fixture(tmp_path, monkeypatch):
    import importlib

    sys.path.insert(0, str(REPO / "eval" / "accuracy" / "v1"))
    try:
        oracle = importlib.import_module("oracle")
    finally:
        sys.path.pop(0)
    cases = json.loads(
        (REPO / "eval/accuracy/v1/dev.json").read_text(encoding="utf-8"),
    )
    victim = next(c for c in cases if c["expected_facts"])
    victim["expected_facts"][0]["value"] = 123456789
    doctored = tmp_path / "dev.json"
    doctored.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    empty = tmp_path / "holdout.json"
    empty.write_text("[]", encoding="utf-8")
    assert oracle.verify([doctored, empty]) != 0
