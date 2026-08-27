"""Trọng tài intent theo chính sách — Spec2308 §WP-A11.

Điều phải giữ tuyệt đối: ``P-A`` là hành vi hiện tại **từng bit**. Nếu không,
mọi con số so sánh P-A/P-B sau này đều so với một mốc đã bị dịch.
"""
from __future__ import annotations

import pytest

from gladiators.agent.intent_arbiter import (
    DEFAULT_POLICY,
    IntentLabelError,
    arbitrate,
    current_policy,
    two_way_clarify,
    validate_label,
)
from gladiators.contracts import StructuredRequest

ALLOWED = frozenset({"analytical_query", "open_analytical", "dataset_coverage"})


def _request(intent: str) -> StructuredRequest:
    return StructuredRequest(intent=intent, language="vi", country="vn", slots={})


def test_the_default_policy_is_the_current_behaviour():
    """A11-R3. Đổi mặc định cần một phép đo cho thấy P-B THẮNG, không phải hoà."""
    assert DEFAULT_POLICY == "P-A"


def test_an_unknown_policy_value_falls_back_to_p_a(monkeypatch):
    """Biến môi trường gõ sai không được phép mở một chính sách RỘNG HƠN."""
    monkeypatch.setenv("GLADIATORS_INTENT_POLICY", "P-Z")
    assert current_policy() == "P-A"
    monkeypatch.setenv("GLADIATORS_INTENT_POLICY", "P-B")
    assert current_policy() == "P-B"


def test_policy_a_returns_exactly_what_it_was_given():
    parsed, deterministic = _request("dataset_coverage"), _request("open_analytical")
    adjustments = ["open_analytical_precedence"]
    result, meta = arbitrate(
        deterministic, parsed, adjustments, policy="P-A",
        is_registered=lambda name: name in ALLOWED,
        capability_serves=lambda name, request: True,
    )
    assert result is parsed
    assert meta == {"policy": "P-A"}
    assert adjustments == ["open_analytical_precedence"]


def test_policy_b_takes_the_llm_label_only_when_the_contract_is_served():
    parsed, deterministic = _request("dataset_coverage"), _request("open_analytical")
    adjustments = ["open_analytical_precedence"]
    result, meta = arbitrate(
        deterministic, parsed, adjustments, policy="P-B",
        is_registered=lambda name: name in ALLOWED,
        capability_serves=lambda name, request: True,
    )
    assert result.intent == "dataset_coverage"
    assert meta["reason"] == "deterministic_open"
    # Gỡ ĐÚNG nhánh đã ghi đè nhãn, không gỡ nhánh nào khác: xoá cả danh sách sẽ
    # giấu mất các nhánh AN TOÀN đã bắn.
    assert adjustments == []


def test_policy_b_refuses_a_label_whose_contract_is_not_served():
    """Đây là điều kiện ngăn P-B lặp lại lỗi đã đo: DeepSeek gán "Có bao nhiêu
    listing ở VN?" thành dataset_coverage, mà hình dạng đã chứng nhận của macro
    đó không sinh được một con số vô hướng."""
    parsed, deterministic = _request("dataset_coverage"), _request("open_analytical")
    result, meta = arbitrate(
        deterministic, parsed, [], policy="P-B",
        is_registered=lambda name: name in ALLOWED,
        capability_serves=lambda name, request: False,
    )
    assert result is parsed
    assert meta["reason"] == "llm_label_not_served"


def test_policy_b_does_nothing_when_the_deterministic_parser_found_a_path():
    """P-B chỉ mở chỗ luật deterministic đang BÓ TAY, không mở chỗ nó đang đúng."""
    parsed, deterministic = _request("dataset_coverage"), _request("analytical_query")
    result, meta = arbitrate(
        deterministic, parsed, [], policy="P-B",
        is_registered=lambda name: name in ALLOWED,
        capability_serves=lambda name, request: True,
    )
    assert result is parsed
    assert meta["reason"] == "no_change"


def test_a_label_outside_the_registry_is_an_error_not_an_approximation():
    """A11-R5. Một nhãn sai được sửa thành nhãn gần nhất là một quyết định định
    tuyến do phép so chuỗi đưa ra."""
    assert validate_label("analytical_query", ALLOWED) == "analytical_query"
    assert validate_label("unsupported:profit", ALLOWED).startswith("unsupported:")
    with pytest.raises(IntentLabelError):
        validate_label("analytic_query", ALLOWED)


def test_two_close_candidates_become_a_two_option_clarify():
    assert two_way_clarify(("analytical_query", "dataset_coverage"), ALLOWED) == (
        "analytical_query", "dataset_coverage",
    )
    # Một ứng viên hợp lệ ⇒ không có gì để hỏi lại.
    assert two_way_clarify(("analytical_query", "nonsense"), ALLOWED) is None
    assert two_way_clarify(("analytical_query", "analytical_query"), ALLOWED) is None


def test_the_arbiter_never_touches_the_gate():
    """A11-R1. Nó chỉ đề xuất ``intent`` — không có tham số nào cho phép nó nói
    về hành động, và đó là ràng buộc theo CHỮ KÝ chứ không theo quy ước."""
    import inspect

    names = set(inspect.signature(arbitrate).parameters)
    assert not {"gate", "decision", "action"} & names
