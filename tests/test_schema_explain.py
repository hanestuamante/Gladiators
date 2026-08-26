"""WP-A7 — intent giải thích quan hệ giữa entity.

`RelationSpec` đã mang sẵn mọi thứ cần để trả lời: cardinality, temporal_validity,
fanout_effect, join_keys, interpretation. Chưa intent nào đọc chúng.

Cạm bẫy chết người của WP này: câu trả lời **không có evidence nào**, mà
`verifier.scan_numbers` quét mọi số và đòi evidence cho từng số. Chuỗi `"1:N"`
chứa chữ số và sẽ bị chấm là số bịa — nên A7-R1 cấm in ký hiệu cardinality.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gladiators.agent.verifier import scan_numbers
from gladiators.agent.workflow import AgentRuntime
from gladiators.domain.relation_prose import explain
from gladiators.domain.relations import RELATIONS

SUITE = json.loads(Path("eval/questions_schema.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    return AgentRuntime(trace_dir=tmp_path_factory.mktemp("traces"))


def test_shop_listing_relation(runtime):
    response = runtime.run("Shop và listing liên quan thế nào?")
    assert response.gate.action == "allow"
    answer = response.answer
    assert "thuộc về một" in answer, "phải nêu lực lượng BẰNG LỜI"
    assert "shop_id" in answer, "phải nêu khoá nối"
    assert "làm giàu tĩnh" in answer, "belongs_to chỉ có một mốc thời gian"


# --- A7-R1 · không chữ số trong answer, cho CẢ 8 case ---------------------

@pytest.mark.parametrize("case", SUITE, ids=lambda c: c["id"])
def test_answer_has_no_digits(runtime, case):
    response = runtime.run(case["question"])
    assert response.gate.action == "allow"
    assert scan_numbers(response.answer) == [], (
        "câu trả lời không có evidence nên mọi chữ số bị chấm là số bịa"
    )
    assert response.verification.get("passed") is True


def test_no_relation_pair_can_produce_a_digit():
    """Khoá ở tầng nguồn, không chỉ ở tám câu của suite."""
    seen: set[tuple[str, str | None]] = set()
    for spec in RELATIONS.values():
        for pair in ((spec.left, spec.right), (spec.left, None), (spec.right, None)):
            if pair in seen:
                continue
            seen.add(pair)
            assert scan_numbers(explain(*pair)) == [], f"{pair} sinh chữ số"


# --- A7-R3 · không bịa một cạnh không có trong registry -------------------

def test_shelf_vs_platform_warns(runtime):
    """Hai hệ phân loại có cột trùng tên `category_id` nhưng KHÔNG có đường nối."""
    answer = runtime.run("Kệ shop và danh mục sàn liên kết ra sao?").answer
    assert "không có đường nối được chứng nhận" in answer


def test_unknown_pair_is_honest():
    answer = explain("Shop", "PlatformCategory")
    assert "không có đường nối được chứng nhận" in answer
    assert "qua quan hệ" not in answer, "không được bịa tên một quan hệ"


# --- A7-R2 · không sinh Evidence -----------------------------------------

def test_explanation_emits_no_evidence(runtime):
    """Đây không phải một tuyên bố về dữ liệu, nên không có gì cần chống lưng."""
    response = runtime.run("Shop và listing liên quan thế nào?")
    assert response.evidence == []
    assert response.claims == ()


# --- không bind được entity thì KHÔNG cướp intent -------------------------

@pytest.mark.parametrize("question", [
    "Giá trung vị tại VN",
    "Có bao nhiêu listing có voucher tại VN ngày 03/07?",
])
def test_questions_about_numbers_keep_their_intent(runtime, question):
    assert runtime.run(question).request.intent != "schema_relation_explain"
