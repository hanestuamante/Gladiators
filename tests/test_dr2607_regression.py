from __future__ import annotations

import json
from pathlib import Path

import pytest

from gladiators.agent.workflow import AgentRuntime


SUITE = json.loads(Path("eval/dr2607.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def runtime(tmp_path_factory) -> AgentRuntime:
    return AgentRuntime(trace_dir=tmp_path_factory.mktemp("dr2607-traces"))


@pytest.fixture(scope="module")
def responses(runtime):
    return {case["id"]: runtime.run(case["question"]) for case in SUITE}


def test_dr2607_suite_contains_exactly_40_unique_source_questions():
    assert [case["id"] for case in SUITE] == [f"tc{i:02d}" for i in range(1, 41)]
    assert len({case["question"] for case in SUITE}) == 40
    assert all(case["source"] == "docs/qa/DR TASK 1407.md" for case in SUITE)
    assert "sentinel" not in SUITE[18]["question"].casefold()
    assert "một mã hoàn toàn" not in SUITE[19]["question"].casefold()


def test_executable_route_contracts(responses):
    for case in SUITE:
        if case["expected_action"] is None:
            continue
        response = responses[case["id"]]
        assert response.gate.action == case["expected_action"], case["id"]
        if case["allowed_rule_ids"]:
            assert response.gate.rule_id in case["allowed_rule_ids"], case["id"]
        assert response.gate.rule_id not in case["forbidden_rule_ids"], case["id"]


@pytest.mark.parametrize("case_id", ["tc29", "tc39"])
def test_measure_substitution_never_allows_listing_count(case_id, responses):
    response = responses[case_id]
    assert response.gate.action != "allow"
    assert response.gate.rule_id != "A-ALLOW"
    assert not (
        response.gate.action == "allow"
        and response.request.slots.get("analytical_kind") == "listing_count"
    )


@pytest.mark.parametrize("case_id", ["tc21", "tc22", "tc24", "tc30"])
def test_macro_qualifiers_are_not_silently_substituted(case_id, responses):
    response = responses[case_id]
    assert response.gate.action == "clarify"
    assert response.gate.rule_id == "A22-ALIGN-QUALIFIER"
    assert "ngoài phạm vi" in response.gate.reason


@pytest.mark.parametrize("case_id", ["tc08", "tc23", "tc25", "tc31"])
def test_compound_requests_preserve_supported_and_unsupported_parts(
    case_id, responses,
):
    response = responses[case_id]
    assert response.request.slots.get("partial_unsupported")
    assert "Chưa trả lời được" in response.answer
    if case_id == "tc08":
        # The supported sales part is entity-ambiguous, so asking for an exact
        # listing is safer than picking one Kinh Đô product.
        assert response.gate.rule_id == "A-AMBIGUOUS"
    else:
        assert response.gate.action == "allow"
        assert response.gate.rule_id == "A22-ALIGN-SUBREQUEST"
        assert response.evidence
        assert all(item.attrs.get("sub_id") == "sr1" for item in response.evidence)


@pytest.mark.parametrize("case_id", ["tc09", "tc20", "tc26"])
def test_id_label_is_not_parsed_as_indonesia(case_id, responses):
    assert "id" not in responses[case_id].request.countries


def test_nonexistent_item_uses_entity_not_found(responses):
    response = responses["tc20"]
    assert response.request.entity_text == "111222333444"
    assert response.gate.rule_id == "A-ENTITY-NOT-FOUND"


def test_quote_insensitivity_is_at_least_38_of_40(runtime):
    stable = 0
    for case in SUITE:
        question = case["question"]
        variants = (
            question,
            f'"{question}"',
            f"“{question}”",
            f'*"{question}"*',
        )
        signatures = {
            (
                response.request.intent,
                response.request.countries,
                response.gate.action,
                response.gate.rule_id,
            )
            for response in (runtime.run(variant) for variant in variants)
        }
        stable += len(signatures) == 1
    assert stable >= 38
