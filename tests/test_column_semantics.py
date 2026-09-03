"""W8 — ngữ nghĩa cột quan sát, khai bằng registry (SolutionSpec2808 §9).

Vấn đề không phải thiếu code: ``is_ad_bool`` False ở 3341/3341 dòng, và "đã
quan sát, đúng là không có" với "không thu thập được" cho hai câu trả lời trái
ngược từ cùng một cột. Registry mặc định ``unknown`` fail-closed; test wiring
thay LẦN LƯỢT ba trạng thái và chứng minh call site thật sự bắn — chỉ kiểm nội
dung dict là không đủ (CLAUDE.md §5.1.3).
"""
from __future__ import annotations

import pytest

from gladiators.agent.workflow import AgentRuntime
from gladiators.domain import column_semantics
from gladiators.domain.column_semantics import (
    COLUMN_SEMANTICS,
    ColumnSemantics,
    ColumnSemanticsError,
    classify_column_observation,
)

AD_FLAG_QUESTION = "Có bao nhiêu listing được gắn cờ quảng cáo tại VN ngày 03/07?"
AD_PERFORMANCE_QUESTION = "Chi phí quảng cáo tại VN là bao nhiêu?"


@pytest.fixture(scope="module")
def runtime() -> AgentRuntime:
    return AgentRuntime()


def _with_state(monkeypatch, column: str, semantics: str, caveat: str | None = None):
    registry = dict(COLUMN_SEMANTICS)
    registry[column] = ColumnSemantics(
        column, semantics,
        approved_by="data-owner-test" if semantics != "unknown" else None,
        approved_at="2026-08-29" if semantics != "unknown" else None,
        caveat_key=caveat,
    )
    monkeypatch.setattr(column_semantics, "COLUMN_SEMANTICS", registry)


# --- bất biến import --------------------------------------------------------

def test_a_decided_state_without_a_signature_explodes():
    """Agent không được điền approved_by (A12-R6): một trạng thái đã quyết mà
    không có chữ ký người quyết là một registry tự mâu thuẫn."""
    broken = {
        "products_clean.csv.is_ad_bool": ColumnSemantics(
            "products_clean.csv.is_ad_bool", "not_collected", None, None, None,
        ),
    }
    with pytest.raises(ColumnSemanticsError):
        column_semantics._check(broken)


def test_observed_without_a_caveat_explodes():
    broken = {
        "products_clean.csv.is_ad_bool": ColumnSemantics(
            "products_clean.csv.is_ad_bool", "observed", "owner", "2026-08-29", None,
        ),
    }
    with pytest.raises(ColumnSemanticsError):
        column_semantics._check(broken)


def test_a_nonexistent_column_explodes():
    broken = {
        "products_clean.csv.khong_ton_tai": ColumnSemantics(
            "products_clean.csv.khong_ton_tai", "unknown", None, None, None,
        ),
    }
    with pytest.raises(ColumnSemanticsError):
        column_semantics._check(broken)


def test_the_registry_hash_tracks_the_content():
    assert len(column_semantics.REGISTRY_HASH) == 16


# --- ba trạng thái, chứng minh call site BẮN --------------------------------

def test_unknown_keeps_todays_refusal(runtime):
    """Registry toàn unknown ⇒ Y HỆT hôm nay: A-MISSING-ADS."""
    response = runtime.run(AD_FLAG_QUESTION)
    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A-MISSING-ADS"


def test_not_collected_becomes_data_absent(monkeypatch, runtime):
    """not_collected ⇒ A-DATA-ABSENT với lý do nêu ĐÚNG: cột không được thu
    thập, không phải "dataset không có khái niệm này"."""
    _with_state(monkeypatch, "products_clean.csv.is_ad_bool", "not_collected")
    response = runtime.run(AD_FLAG_QUESTION)
    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A-DATA-ABSENT"
    assert "không được thu thập" in response.gate.reason
    # Không chữ số trong câu từ chối (verifier.scan_numbers, CLAUDE.md §3.1).
    assert not any(char.isdigit() for char in response.gate.reason)


def test_an_ad_performance_question_stays_missing_ads_in_every_state(monkeypatch, runtime):
    """Câu hỏi HIỆU QUẢ quảng cáo đúng là A-MISSING-ADS ở cả ba trạng thái —
    impressions/clicks/chi phí thật sự không có trong dataset."""
    for semantics, caveat in (("unknown", None), ("not_collected", None),
                              ("observed", "caveat.is_ad_flag")):
        _with_state(monkeypatch, "products_clean.csv.is_ad_bool", semantics, caveat)
        response = runtime.run(AD_PERFORMANCE_QUESTION)
        assert response.gate.rule_id == "A-MISSING-ADS", semantics


def test_classify_reads_the_live_registry(monkeypatch):
    """Wiring: classify đọc registry HIỆN HÀNH, không một bản chụp lúc import."""
    assert classify_column_observation("co bao nhieu listing co quang cao") is None
    _with_state(monkeypatch, "products_clean.csv.is_ad_bool", "not_collected")
    observation = classify_column_observation("co bao nhieu listing co quang cao")
    assert observation is not None
    assert observation.semantics == "not_collected"


# --- W8.4 · router nhận external theo cấu trúc ------------------------------

@pytest.mark.parametrize("question", [
    "Giá của đối thủ ngoài sàn cho sản phẩm này là bao nhiêu?",
    "Giá đối thủ là bao nhiêu?",
    "Giá ở ngoài sàn của sản phẩm này?",
])
def test_external_competitor_price_is_a14_ext_not_currency(question, runtime):
    """ans044 và biến thể chèn "của"/"ở"/"ngoài sàn": nhãn từ chối phải nói đúng
    vấn đề (cần nguồn external), không rơi vào gate currency/country."""
    response = runtime.run(question)
    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A14-EXT"


def test_explicit_cross_currency_keeps_its_own_rule(runtime):
    response = runtime.run("So sánh giá trung vị VN và Indonesia quy đổi sang USD")
    assert response.gate.rule_id == "A16-CROSS-CURRENCY"


def test_a_clause_with_competitor_but_no_price_is_not_external():
    from gladiators.external.router import _is_external_competitor_price

    assert not _is_external_competitor_price(
        "so sanh rating doi thu, va gia trung vi tai vn",
    )
