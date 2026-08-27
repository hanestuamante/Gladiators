"""Màn hình sổ vết — Spec2308 §WP-B9.

Màn hình này tồn tại để trả lời *"làm sao tôi biết số này không phải bịa?"*. Nếu
chính nó cảnh báo sai, nó dạy người đọc bỏ qua cảnh báo — và khi đó nó tệ hơn
việc không có màn hình nào.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gladiators.api import app
from gladiators.ui_trace import TraceNotFound, load_trace, render, trace_summary


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def trace_id(client: TestClient) -> str:
    response = client.post(
        "/ask", json={"text": "Có bao nhiêu listing tại Việt Nam ngày 03/07?"},
    )
    return response.json()["trace_id"]


def test_a_valid_trace_id_renders_all_three_blocks(client, trace_id):
    html = client.get(f"/trace/{trace_id}").text
    assert client.get(f"/trace/{trace_id}").status_code == 200
    assert "Mỗi con số nối về đâu" in html
    assert "Chặng dừng và lý do" in html
    assert "Ngân sách" in html


def test_every_claimed_number_carries_its_source(client, trace_id):
    data = client.get(f"/trace/{trace_id}.json").json()
    assert data["claims"]
    for claim in data["claims"]:
        assert claim["evidence_id"]
        assert claim["source"]
        assert claim["dataset_version"]


def test_a_clean_answer_raises_no_false_alarm(client, trace_id):
    """Bản quét viết tay đầu tiên báo [3.0, 1.0, 2026.0] cho một câu trả lời hoàn
    toàn hợp lệ — nó không biết verifier đã che ngày ISO và token citation trước
    khi quét."""
    assert client.get(f"/trace/{trace_id}.json").json()["unbacked_numbers"] == []


def test_a_number_without_evidence_shows_a_warning():
    trace = {"response": {
        "trace_id": "aaaaaaaaaaaa", "answer": "Có 999 listing.",
        "claims": [], "evidence": [],
        "verification": {"passed": False, "unsupported": [999.0]},
        "gate": {"action": "allow", "rule_id": "A-ALLOW", "reason": ""},
        "planning": {}, "request": {},
    }}
    assert trace_summary(trace)["unbacked_numbers"] == [999.0]
    assert "Số không nối được tới evidence" in render(trace)


def test_the_stage_timeline_separates_a_skipped_stage_from_a_fast_one(client, trace_id):
    stages = client.get(f"/trace/{trace_id}.json").json()["stages"]
    assert len(stages) == 9
    assert {stage["key"] for stage in stages} >= {"parse", "gate", "verify"}


def test_all_gate_issues_are_shown_not_only_the_winning_one():
    """Issue thua giải thích vì sao lời từ chối này chứ không phải một lời từ
    chối khác."""
    trace = {"response": {
        "trace_id": "aaaaaaaaaaaa", "answer": "", "claims": [], "evidence": [],
        "verification": {}, "planning": {}, "request": {},
        "gate": {
            "action": "abstain", "rule_id": "A-B", "reason": "…",
            "issues": [
                {"rule_id": "A-A", "reason": "một", "fixable": True},
                {"rule_id": "A-B", "reason": "hai", "fixable": False},
            ],
            "selected_issue_id": "A-B",
        },
    }}
    html = render(trace)
    assert "A-A" in html and "A-B" in html
    assert "KHÔNG khắc phục được" in html


@pytest.mark.parametrize(
    "bad", ["../../etc/passwd", "..", "ZZZZZZZZZZZZ", "abc", "3b07f4af19d", "", "3B07F4AF19D4"],
)
def test_the_loader_rejects_every_id_that_is_not_twelve_hex_digits(bad):
    """B9-R3. Ghép chuỗi vào một Path rồi tin nó nằm trong thư mục là cách mọi
    lỗi path traversal bắt đầu. Phép kiểm nằm ở TẦNG NẠP chứ không ở tầng HTTP:
    "/trace/.." bị client chuẩn hoá thành "/" nên nó không bao giờ chạm handler,
    và một test dựa vào mã 404 ở đó sẽ kiểm phép chuẩn hoá URL thay vì kiểm luật.
    """
    with pytest.raises(TraceNotFound):
        load_trace(bad)


@pytest.mark.parametrize(
    "bad", ["../../etc/passwd", "ZZZZZZZZZZZZ", "abc", "3b07f4af19d"],
)
def test_a_bad_trace_id_is_404_not_500(client, bad):
    assert client.get(f"/trace/{bad}").status_code == 404
    assert client.get(f"/trace/{bad}.json").status_code == 404


def test_the_screen_only_reads_and_never_replays():
    """B9-R1. Chạy lại là một tính năng khác và sẽ cho số khác, nên nó sẽ trả lời
    một câu hỏi khác với câu người dùng đang hỏi."""
    from pathlib import Path

    source = Path("src/gladiators/ui_trace.py").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    assert "AgentRuntime" not in code
    assert ".run(" not in code
