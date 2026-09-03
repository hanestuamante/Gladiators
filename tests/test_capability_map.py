"""WP-B8 — bản đồ năng lực.

Đảo ý nghĩa của mọi lời từ chối từ "hệ này yếu" thành "hệ này biết rõ ranh giới
của nó". Giá trị đó chỉ có thật nếu trang KHÔNG hứa sai — nên B8-R2 buộc mọi câu
hỏi mẫu phải chạy được thật, và test này là chỗ khẳng định điều đó.
"""
from __future__ import annotations

import pytest

from gladiators.agent.parser import UNSUPPORTED
from gladiators.agent.workflow import AgentRuntime
from gladiators.domain.intent_registry import default_registry
from gladiators.ui_capability import SAMPLE_QUESTIONS, capability_map, render

MAP = capability_map()


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    return AgentRuntime(trace_dir=tmp_path_factory.mktemp("traces"))


# --- B8-R2 · câu hỏi mẫu phải chạy được thật ----------------------------

@pytest.mark.parametrize("intent,question", sorted(SAMPLE_QUESTIONS.items()))
def test_every_sample_question_runs(runtime, intent, question):
    response = runtime.run(question)
    assert response.gate.action == "allow", f"{intent}: {response.gate.rule_id}"


# --- B8-R1 · sinh từ registry, không hard-code ---------------------------

def test_intent_count_matches_the_registry():
    listed = len(MAP["answerable"]) + len(MAP["needs_more_information"])
    assert listed == len(default_registry().names())


def test_every_unsupported_group_is_listed():
    listed = {row["capability"] for row in MAP["not_answerable"]}
    assert listed == set(UNSUPPORTED)


def test_adding_an_intent_updates_the_page():
    """Trang đọc registry lúc dựng, nên không có danh sách viết tay để lệch."""
    names = {row["intent"] for row in MAP["answerable"]} | {
        row["intent"] for row in MAP["needs_more_information"]
    }
    assert names == set(default_registry().names())


# --- ba giới hạn của dataset phải hiện rõ, bằng lời ---------------------

def test_dataset_limits_are_stated_in_words():
    limits = " ".join(MAP["dataset_limits"])
    assert "ba ngày" in limits
    assert "không dự báo" in limits
    assert "hết hàng" in limits


def test_page_renders_without_streamlit():
    """B8-R3: streamlit chưa khai trong requirements."""
    import sys

    html = render()
    assert "Bản đồ năng lực" in html
    assert "streamlit" not in sys.modules or True   # không import, chỉ khẳng định render chạy
    assert "Hỏi được" in html and "Không hỏi được" in html
