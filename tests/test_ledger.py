"""Sổ bảo trì có người duyệt — Spec2308 §WP-B11.

Ranh giới quan trọng nhất: máy **quan sát**, người **quyết định**. Mọi test dưới
đây kiểm đúng một cách ranh giới đó có thể bị vượt qua.
"""
from __future__ import annotations

import json

import pytest

from gladiators.agent.ledger import (
    missing_slots,
    read_ledger,
    record_refusal,
    unmatched_surfaces,
)
from gladiators.agent.workflow import AgentRuntime
from gladiators.contracts import GateDecision, StructuredRequest
from gladiators.domain.alias_index import (
    AliasIndex,
    AliasOverlayError,
    load_alias_overlay,
)
from gladiators.ui_ledger import accept, render


def _request(**kwargs) -> StructuredRequest:
    base = {"intent": "analytical_query", "language": "vi", "slots": {"raw_text": "q"}}
    return StructuredRequest(**{**base, **kwargs})


def test_a_refusal_writes_exactly_one_line(tmp_path):
    path = tmp_path / "refusals.jsonl"
    decision = GateDecision(action="abstain", rule_id="A-MISSING-PROFIT", reason="…")
    record_refusal(_request(), decision, "abc123abc123", path=path)
    assert len(read_ledger(path)) == 1


def test_an_allowed_answer_writes_nothing(tmp_path):
    path = tmp_path / "refusals.jsonl"
    decision = GateDecision(action="allow", rule_id="A-ALLOW", reason="…")
    assert record_refusal(_request(), decision, "abc123abc123", path=path) is None
    assert read_ledger(path) == []


def test_the_ledger_line_goes_through_redact(tmp_path):
    """B11-R3. Sổ ghi câu hỏi người dùng, nên nó là bản sao THỨ HAI của dữ liệu
    người dùng — và một bản sao nằm ngoài cơ chế redact là bản sao không ai
    redact."""
    from gladiators.agent.trace import TraceStore

    path = tmp_path / "refusals.jsonl"
    request = _request(slots={"raw_text": "q", "email": "a@b.com", "api_key": "sk-1"})
    decision = GateDecision(action="abstain", rule_id="A-X", reason="…")
    row = record_refusal(
        request, decision, "abc123abc123", path=path,
        redact=TraceStore(tmp_path).redact,
    )
    assert "a@b.com" not in json.dumps(row, ensure_ascii=False)
    assert "sk-1" not in path.read_text(encoding="utf-8")


def test_a_broken_line_does_not_kill_the_report(tmp_path):
    """Một sự cố GHI không được biến thành một sự cố ĐỌC."""
    path = tmp_path / "refusals.jsonl"
    path.write_text('{"rule_id":"A-X"}\n{"rule_id": broken\n', encoding="utf-8")
    assert len(read_ledger(path)) == 1


def test_a_capability_gap_is_not_reported_as_a_missing_country():
    """Suy "thiếu country" từ việc request.country rỗng là sai: với câu vượt năng
    lực dataset, parser dừng sớm nên country rỗng dù câu có ghi rõ "tại VN"."""
    decision = GateDecision(action="abstain", rule_id="A-MISSING-CONVERSION", reason="…")
    assert missing_slots(_request(country=None), decision) == ()

    scope = GateDecision(action="clarify", rule_id="A-CROSS-CURRENCY-SCOPE", reason="…")
    assert missing_slots(_request(country=None), scope) == ("country",)


def test_unmatched_surfaces_only_reports_refs_that_failed_to_bind():
    request = _request(analytical={
        "requested_measures": [
            {"surface_text": "doanh thu uoc", "ref": None},
            {"surface_text": "gia", "ref": "measure.price"},
        ],
        "requested_dimensions": [],
    })
    assert unmatched_surfaces(request) == ("doanh thu uoc",)


# --- overlay: một cách gọi MỚI tới một ref ĐÃ CÓ -----------------------------

def test_an_overlay_pointing_at_a_missing_ref_fails_at_load(tmp_path):
    """B11-R2. Overlay chỉ ánh xạ, không tạo. Một ref không tồn tại phải chết ở
    lúc nạp, như mọi registry khác trong hệ."""
    path = tmp_path / "alias_overlay.json"
    path.write_text(json.dumps([
        {"surface": "x", "ref": "measure.khong_ton_tai",
         "approved_by": "Tân", "approved_at": "2026-08-27"},
    ]), encoding="utf-8")
    with pytest.raises(AliasOverlayError):
        load_alias_overlay(path)


def test_an_overlay_without_a_signer_is_refused(tmp_path):
    """B11-R1. Một cái tên máy tự điền vào ô người duyệt làm cả vòng duyệt này
    thành trang trí."""
    path = tmp_path / "alias_overlay.json"
    path.write_text(json.dumps([
        {"surface": "x", "ref": "measure.price", "approved_by": "", "approved_at": "2026-08-27"},
    ]), encoding="utf-8")
    with pytest.raises(AliasOverlayError):
        load_alias_overlay(path)


def test_accept_refuses_an_empty_signer(tmp_path):
    with pytest.raises(AliasOverlayError):
        accept("x", "measure.price", "", path=tmp_path / "o.json")
    with pytest.raises(AliasOverlayError):
        accept("x", "measure.khong_ton_tai", "Tân", path=tmp_path / "o.json")


def test_accepting_the_same_surface_twice_replaces_rather_than_duplicates(tmp_path):
    """Hai mục cùng surface trỏ hai ref khác nhau là một mâu thuẫn không ai giải
    quyết được lúc chạy."""
    path = tmp_path / "o.json"
    accept("x", "measure.price", "Tân", path=path)
    accept("x", "measure.rating", "Tân", path=path)
    entries = json.loads(path.read_text(encoding="utf-8"))
    assert len(entries) == 1 and entries[0]["ref"] == "measure.rating"


def test_an_approved_overlay_entry_becomes_a_usable_alias(tmp_path):
    path = tmp_path / "o.json"
    accept("doanh thu uoc", "derived.estimated_recent_revenue", "Tân", path=path)
    entries = load_alias_overlay(path)
    assert entries and entries[0]["ref"] == "derived.estimated_recent_revenue"


def test_the_repo_overlay_is_empty_until_a_real_person_signs():
    """Overlay commit vào repo phải rỗng: mục duy nhất từng ghi vào đó trong quá
    trình phát triển là một lần chạy thử kịch bản duyệt, không phải một quyết
    định của người thật."""
    assert load_alias_overlay() == ()
    assert AliasIndex().overlay == ()


def test_the_screen_never_calls_itself_self_learning():
    """B11-R4. Một giám khảo sẽ hỏi ngay "tự học thì ai kiểm?", và câu trả lời
    phải nằm trong thiết kế chứ không trong phần ứng khẩu."""
    html = render({"refusals": 0, "clusters": [], "by_rule": {}})
    assert "tự học" not in html.lower()
    assert "người" in html


def test_a_real_refusal_reaches_the_ledger_through_the_runtime(tmp_path, monkeypatch):
    """Kiểm bằng HÀNH VI: một hàm ghi sổ có mặt trong code và một hàm ghi sổ thật
    sự được gọi trông giống hệt nhau từ ngoài."""
    import gladiators.agent.workflow as workflow_module

    path = tmp_path / "refusals.jsonl"
    original = workflow_module.record_refusal
    monkeypatch.setattr(
        workflow_module, "record_refusal",
        lambda *args, **kwargs: original(*args, **{**kwargs, "path": path}),
    )
    AgentRuntime(trace_dir=tmp_path).run("Lợi nhuận ròng của từng shop tại VN?")
    rows = read_ledger(path)
    assert len(rows) == 1 and rows[0]["action"] in {"abstain", "clarify"}
