"""Bounded Plan Critic P9 contract — V2 mục 7.7 và 13.4."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .query_ir import LogicalQueryPlan
from .validator import validate_plan

CriticIssueCode = Literal[
    "missing_semantic_object", "wrong_filter", "wrong_join_path", "grain_mismatch",
    "fanout_risk", "unit_mismatch", "temporal_mismatch", "unsupported_claim",
    "budget_exceeded", "schema_invalid",
]


class CriticIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: CriticIssueCode
    node_id: str | None = None
    message: str = Field(min_length=1)


class CriticOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issues: list[CriticIssue]


class PlanCritic:
    """Critic không sửa plan; chỉ trả issue list. Thiếu provider thì fail-closed."""

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def review(self, question: str, plan: LogicalQueryPlan) -> CriticOutput:
        deterministic = validate_plan(plan)
        if not deterministic.valid:
            return CriticOutput(issues=[
                CriticIssue(code=issue.code, node_id=issue.node_id, message=issue.message)
                for issue in deterministic.issues
            ])
        if self.llm_client is None or not hasattr(self.llm_client, "critique_plan"):
            raise RuntimeError("Plan critic được yêu cầu nhưng chưa có LLM provider hỗ trợ P9.")
        output = self.llm_client.critique_plan(question, plan.model_dump(mode="json"))
        return CriticOutput.model_validate(output)
