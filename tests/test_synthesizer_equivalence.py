"""A1-R1 — khoá tương đương của bộ sinh kế hoạch.

Ràng buộc quan trọng nhất của WP-A1: **chỉ được THÊM, không được ĐỔI**. Với mọi
câu hỏi mà ``synthesize()`` trước đây trả một plan, bản mới phải trả plan giống
hệt — so bằng ``model_dump_json()`` sau khi chuẩn hoá đoạn phiên bản của
``plan_id``.

Baseline chụp tại `fbd34d0`, trước khi RelationPlanner tồn tại: 173 câu của 9
suite, 58 câu có plan, 115 câu trả ``None``.

Câu trước đây ``None`` mà nay có plan là **mở rộng hợp lệ** — đó chính là mục
tiêu của WP. Chiều ngược lại thì không: một plan biến mất hoặc đổi hình nghĩa là
WP đã lấy đi năng lực đang có, và test này bắt đúng chiều đó.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from gladiators.planner.semantic_parser import DeterministicSemanticParser
from gladiators.planner.synthesizer import synthesize

BASELINE = json.loads(
    (Path(__file__).parent / "fixtures" / "synthesizer_equivalence_baseline.json")
    .read_text(encoding="utf-8")
)
PARSER = DeterministicSemanticParser()
QUESTIONS: dict[str, tuple[str, str]] = {}
for _suite in (
    "questions", "questions_v2", "questions_a19", "questions_boundaries",
    "questions_ambiguity", "questions_counting", "questions_critic",
    "dr2607", "semantic_linking",
):
    for _case in json.loads(Path(f"eval/{_suite}.json").read_text(encoding="utf-8")):
        if _case.get("question"):
            QUESTIONS[f"{_suite}:{_case['id']}"] = (
                _case["question"], _case.get("country") or "vn",
            )


def _plan_of(question: str, country: str):
    try:
        result = synthesize(PARSER.parse(question, "vi", country), country)
    except Exception as exc:                      # noqa: BLE001 — baseline ghi cả exception
        return {"exc": type(exc).__name__}
    if result is None:
        return None
    payload = json.loads(result.plan.model_dump_json())
    payload["plan_id"] = re.sub(r":1\.\d+$", "", str(payload.get("plan_id", "")))
    return payload


@pytest.mark.parametrize("key", sorted(k for k, v in BASELINE.items() if isinstance(v, dict)))
def test_existing_plans_are_unchanged(key):
    """Câu đã có plan phải giữ NGUYÊN plan đó."""
    question, country = QUESTIONS[key]
    assert _plan_of(question, country) == BASELINE[key]


def test_no_plan_is_lost():
    """Không câu nào đang có plan được phép rơi về None."""
    lost = [
        key for key, expected in BASELINE.items()
        if isinstance(expected, dict) and "exc" not in expected
        and _plan_of(*QUESTIONS[key]) is None
    ]
    assert lost == [], f"WP đã lấy đi plan của: {lost}"


def test_baseline_still_describes_the_same_corpus():
    """Baseline lệch tập câu hỏi thì nó không còn khoá được gì."""
    assert set(BASELINE) == set(QUESTIONS)
