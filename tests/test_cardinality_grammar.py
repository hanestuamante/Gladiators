"""expected_cardinality grammar and alias resolution — ultimate solution §4.3."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from gladiators.planner.query_ir import CARDINALITY_GRAMMAR, CARDINALITY_SYMBOLS, OutputField, PlanNode

OUTPUT = (OutputField(name="price", type="number", semantic_ref="measure.price"),)
BASE = dict(
    node_id="n1", op="Scan", source="products_clean.csv",
    input_grain="listing_snapshot", output_grain="listing_snapshot",
    expected_schema=OUTPUT,
)


def _node(cardinality: str, **extra) -> PlanNode:
    return PlanNode(**BASE, expected_cardinality=cardinality, **extra)


def test_grammar_constant_is_exported_for_prompt_and_validator():
    # §4.3: the prompt and the validator must state the same rule, so a plan is
    # never rejected against something the model was never told.
    # W30-R3: ngữ pháp nhận thêm KÝ HIỆU trên lịch snapshot. Tập ký hiệu là
    # ĐÓNG — nới thành chuỗi tự do sẽ cho LLM planner khai một cận không ai phân
    # giải được, tức một cận không tồn tại.
    assert CARDINALITY_GRAMMAR == r"^(<=)?(\d+|snapshot_rows|listings|snapshots)$"
    assert CARDINALITY_SYMBOLS == ("snapshot_rows", "listings", "snapshots")


@pytest.mark.parametrize("value", ["1", "5", "<=1", "<=10", "3341"])
def test_wellformed_values_pass_through_unchanged(value):
    node = _node(value)
    assert node.expected_cardinality == value
    assert node.original_cardinality is None


@pytest.mark.parametrize("alias", ["single", "one", "scalar", "SINGLE", " single "])
def test_exact_aliases_resolve_to_one_and_record_the_coercion(alias):
    node = _node(alias)
    assert node.expected_cardinality == "1"
    assert node.original_cardinality == alias


@pytest.mark.parametrize("alias", ["many", "multiple", "list", "several"])
def test_plural_alias_binds_only_to_a_stated_limit(alias):
    node = PlanNode(
        **{**BASE, "op": "Rank"}, expected_cardinality=alias,
        rank_by="measure.price", limit=5,
    )
    assert node.expected_cardinality == "<=5"
    assert node.original_cardinality == alias


@pytest.mark.parametrize("alias", ["many", "multiple", "list", "several", "lots", ""])
def test_unbounded_alias_is_rejected_rather_than_given_an_invented_bound(alias):
    # §4.3 forbids coercing to something like "<=10000": that turns "I don't know
    # how many" into a contract the executor would enforce against nothing.
    with pytest.raises(ValidationError) as excinfo:
        _node(alias)
    message = str(excinfo.value)
    assert CARDINALITY_GRAMMAR in message
    assert "10000" not in message


def test_rejection_message_is_contract_text_not_a_schema_dump():
    with pytest.raises(ValidationError) as excinfo:
        _node("many")
    # Assert on the message this module raises, not on str(ValidationError),
    # which pydantic decorates with its own docs URL.
    message = next(item["msg"] for item in excinfo.value.errors())
    # Actionable for a bounded repair, and free of internals a UI must not show.
    assert "limit" in message
    assert CARDINALITY_GRAMMAR in message
    assert "10000" not in message
    assert "traceback" not in message.lower()


def test_planner_failure_message_never_carries_a_schema_dump(tmp_path):
    """§4.3/§4.4: schema errors must not reach the UI."""
    from gladiators.agent.workflow import AgentRuntime

    class _RejectedPlan:
        provider, model, prompt_version = "test", "bad", "v1"

        def plan_analytical(self, payload):
            # The prompt must state the grammar it will be judged against.
            assert CARDINALITY_GRAMMAR == payload["constraints"]["expected_cardinality_grammar"]
            field = {"name": "price", "type": "number", "semantic_ref": "measure.price"}
            return {
                "plan_id": "open:x", "time_scope": ["2026-07-03"], "output_node": "n1",
                "requested_output_shape": [field],
                "nodes": [{
                    "node_id": "n1", "op": "Scan", "source": "products_clean.csv",
                    "input_grain": "listing_snapshot", "output_grain": "listing_snapshot",
                    "expected_schema": [field],
                    "expected_cardinality": "many",  # unbounded alias -> rejected
                }],
            }

    runtime = AgentRuntime(trace_dir=tmp_path, llm_client=_RejectedPlan())
    runtime.open_planner.use_synthesizer = False  # exercise the LLM plan path
    response = runtime.run("Brand nào có rating cao nhất tại VN?")

    assert response.gate.action == "abstain"
    answer = response.answer.lower()
    for leak in ("pydantic", "validation error", "traceback", "nodes.0", "expected_cardinality"):
        assert leak not in answer, f"schema internals reached the answer: {leak}"
