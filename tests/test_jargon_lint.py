"""§4.7 jargon lint: internal vocabulary must not reach a user-facing answer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gladiators.agent.wording import JARGON_LEXICON_VERSION, check_jargon
from gladiators.agent.workflow import AgentRuntime

SUITES = (
    "eval/dr2607.json", "eval/questions.json", "eval/questions_v2.json",
    "eval/questions_boundaries.json", "eval/questions_a19.json",
)


@pytest.fixture(scope="module")
def runtime(tmp_path_factory) -> AgentRuntime:
    return AgentRuntime(trace_dir=tmp_path_factory.mktemp("jargon"))


def _questions() -> list[str]:
    seen: list[str] = []
    for name in SUITES:
        path = Path(name)
        if not path.exists():
            continue
        for case in json.loads(path.read_text(encoding="utf-8")):
            if isinstance(case, dict) and case.get("question"):
                seen.append(case["question"])
    return seen


def test_lexicon_is_versioned():
    assert JARGON_LEXICON_VERSION


@pytest.mark.parametrize("answer, term", [
    ("Plan sai expected_cardinality", "expected_cardinality"),
    ("1 validation error for LogicalQueryPlan", "logicalqueryplan"),
    ("Không tìm thấy trong artifact hiện tại", "artifact"),
    ("semantic catalog chưa expose trường này", "semantic catalog"),
])
def test_internal_vocabulary_is_flagged(answer, term):
    assert term in {item["term"] for item in check_jargon(answer)}


def test_internal_rule_ids_are_flagged_but_kept_for_traces():
    # §4.7: rule ids stay in trace/API machine fields, never in the prose.
    violations = check_jargon("Bị chặn bởi A22-ALIGN-COUNTRY và A19-PLAN")
    assert {item["term"] for item in violations} == {"A22-ALIGN-COUNTRY", "A19-PLAN"}


def test_plain_business_wording_passes():
    assert check_jargon("Có 668 listing tại VN, snapshot 2026-07-03.") == []
    assert check_jargon("Cần làm rõ: hãy chọn một thị trường.") == []


def test_no_real_answer_leaks_internal_vocabulary(runtime):
    """The lint is worthless unless it holds on the answers we actually ship."""
    offenders = []
    for question in _questions():
        violations = check_jargon(runtime.run(question).answer)
        if violations:
            offenders.append((question[:60], [item["term"] for item in violations]))
    assert not offenders, f"internal vocabulary reached the answer: {offenders}"
