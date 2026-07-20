"""P10/P11 bounded N-version resolution for high-risk analytical plans."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from .compiler import compile_plan
from .executor import QueryExecutor
from .open_planner import OpenAnalyticalPlanner, OpenPlannerError
from .query_ir import LogicalQueryPlan
from .semantic_parser import AnalyticalRequest


class AdjudicationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["primary", "alternate", "unresolved"]
    reason_issue_type: str | None = None
    detail: str


class ConsensusError(ValueError):
    pass


@dataclass(frozen=True)
class ConsensusResult:
    plan: LogicalQueryPlan
    selected: str
    plan_disagreement: bool
    result_disagreement: bool
    adjudicated: bool
    alternate_attempts: int
    reason: str


def _normal_plan(plan: LogicalQueryPlan) -> str:
    payload = plan.model_dump(mode="json", exclude={"plan_id"})
    for node in payload["nodes"]:
        node.pop("cost_estimate", None)
        node.pop("risk_estimate", None)
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        value = value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _execution_signature(repository: Any, plan: LogicalQueryPlan) -> dict[str, Any]:
    compiled = compile_plan(plan)
    executor = QueryExecutor(repository)
    try:
        result = executor.execute(compiled)
    finally:
        executor.close()
    rows = [[_scalar(value) for value in row] for row in result.frame.itertuples(index=False, name=None)]
    return {
        "schema": list(result.frame.columns), "row_count": len(rows), "rows": rows,
        "postconditions": list(compiled.postconditions),
    }


class NVersionResolver:
    def __init__(self, repository: Any, alternate_client: Any | None, adjudicator_client: Any | None):
        self.repository = repository
        method = "plan_analytical_alternate" if alternate_client and hasattr(
            alternate_client, "plan_analytical_alternate"
        ) else "plan_analytical"
        self.alternate = OpenAnalyticalPlanner(alternate_client, planner_method=method)
        self.adjudicator_client = adjudicator_client

    def resolve(
        self, question: str, request: AnalyticalRequest, country: str,
        primary: LogicalQueryPlan,
    ) -> ConsensusResult:
        try:
            alternate_result = self.alternate.plan(question, request, country)
        except OpenPlannerError as exc:
            raise ConsensusError(f"P10 không tạo được alternate plan hợp lệ: {exc}") from exc
        alternate = alternate_result.plan
        plan_disagreement = _normal_plan(primary) != _normal_plan(alternate)
        if not plan_disagreement:
            return ConsensusResult(
                primary, "primary", False, False, False,
                alternate_result.attempts, "Hai planner tạo plan normal form giống nhau.",
            )

        primary_signature = _execution_signature(self.repository, primary)
        alternate_signature = _execution_signature(self.repository, alternate)
        result_disagreement = primary_signature != alternate_signature
        if not result_disagreement:
            return ConsensusResult(
                primary, "primary", True, False, False,
                alternate_result.attempts, "Plan khác cấu trúc nhưng execution signature tương đương.",
            )
        if self.adjudicator_client is None or not hasattr(self.adjudicator_client, "adjudicate_plans"):
            raise ConsensusError("P8/P10 bất đồng kết quả nhưng P11 adjudicator chưa khả dụng.")
        bundle = {
            "question": question,
            "candidates": {
                "primary": {"plan": primary.model_dump(mode="json"), "signature": primary_signature},
                "alternate": {"plan": alternate.model_dump(mode="json"), "signature": alternate_signature},
            },
            "constraints": {"may_create_plan": False, "allowed_verdicts": ["primary", "alternate", "unresolved"]},
        }
        try:
            verdict = AdjudicationOutput.model_validate(self.adjudicator_client.adjudicate_plans(bundle))
        except (ValueError, TypeError, RuntimeError) as exc:
            raise ConsensusError(f"P11 trả verdict không hợp lệ: {exc}") from exc
        if verdict.verdict == "unresolved":
            raise ConsensusError(f"P11 unresolved: {verdict.detail}")
        selected = primary if verdict.verdict == "primary" else alternate
        return ConsensusResult(
            selected, verdict.verdict, True, True, True,
            alternate_result.attempts, verdict.detail,
        )
