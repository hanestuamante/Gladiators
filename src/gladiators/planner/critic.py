"""Bounded Plan Critic P9 contract — V2 mục 7.7 và 13.4.

Chống critic-hallucination (bài học cq03 trong smoke test Groq 20/07): critic từng
false-reject plan hợp lệ vì tự suy đoán physical columns khi không được cung cấp
catalog. Hai lớp phòng vệ ở đây:

1. **Input đủ ngữ cảnh**: payload gửi LLM kèm catalog slice của đúng các ref plan
   dùng (kèm physical mapping) + relation spec của các Join + guidance nêu rõ những
   nhóm lỗi deterministic validator ĐÃ xác nhận — critic không cần (và không được)
   báo lại.
2. **Lọc issue sai kiểm chứng được**: với plan đã qua deterministic validator, các
   nhóm lỗi mà validator phủ đầy đủ (ref tồn tại, filter op, join path, budget,
   output schema) nếu LLM vẫn báo thì đó là phán đoán sai máy chứng minh được →
   drop và ghi lại, không cho phép chặn plan. Critic chỉ giữ tiếng nói ở các nhóm
   semantic nằm ngoài khả năng kiểm cơ học: grain_mismatch, fanout_risk,
   unit_mismatch, temporal_mismatch, unsupported_claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gladiators.domain.catalog import CATALOG
from gladiators.domain.relations import RELATIONS

from .query_ir import LogicalQueryPlan
from .validator import validate_plan

CriticIssueCode = Literal[
    "missing_semantic_object", "wrong_filter", "wrong_join_path", "grain_mismatch",
    "fanout_risk", "unit_mismatch", "temporal_mismatch", "unsupported_claim",
    "budget_exceeded", "schema_invalid",
]

# Nhóm lỗi deterministic validator phủ đầy đủ — plan đã valid thì LLM issue thuộc
# nhóm này là verifiably false.
_DETERMINISTIC_COVERED: frozenset[str] = frozenset({
    "missing_semantic_object", "wrong_filter", "wrong_join_path",
    "budget_exceeded", "schema_invalid",
})


class CriticIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: CriticIssueCode
    node_id: str | None = None
    message: str = Field(min_length=1)


class CriticOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issues: list[CriticIssue]


@dataclass(frozen=True)
class CriticReview:
    issues: tuple[CriticIssue, ...]
    dropped: tuple[CriticIssue, ...] = ()


def _plan_refs(plan: LogicalQueryPlan) -> tuple[str, ...]:
    refs = {ref for node in plan.nodes for ref in node.refs + node.group_by}
    refs.update(predicate.ref for node in plan.nodes for predicate in node.predicates)
    refs.update(node.rank_by for node in plan.nodes if node.rank_by)
    refs.update(field.semantic_ref for field in plan.requested_output_shape if field.semantic_ref)
    return tuple(sorted(ref for ref in refs if ref in CATALOG))


def _critic_payload(question: str, plan: LogicalQueryPlan) -> dict:
    catalog_slice = [
        {
            "ref": ref, "kind": CATALOG[ref].kind, "type": CATALOG[ref].type,
            "unit": CATALOG[ref].unit, "grain": CATALOG[ref].grain,
            "physical": CATALOG[ref].physical,
            "valid_aggregations": CATALOG[ref].valid_aggregations,
            "allowed_filters": CATALOG[ref].allowed_filters,
            "caveats": CATALOG[ref].caveats,
        }
        for ref in _plan_refs(plan)
    ]
    relations = [
        {
            "name": spec.name, "join_keys": spec.join_keys, "cardinality": spec.cardinality,
            "input_grain": spec.input_grain, "output_grain": spec.output_grain,
            "fanout_effect": spec.fanout_effect, "dedupe_strategy": spec.dedupe_strategy,
        }
        for node in plan.nodes if node.op == "Join" and node.relation in RELATIONS
        for spec in (RELATIONS[node.relation],)
    ]
    return {
        "question": question,
        "plan": plan.model_dump(mode="json"),
        "catalog_slice": catalog_slice,
        "relations": relations,
        "guidance": (
            "Deterministic validator ĐÃ xác nhận: refs tồn tại trong catalog, filter op hợp lệ, "
            "join path đúng relation registry, budget trong hạn và expected_schema khớp "
            "requested_output_shape — KHÔNG báo lại các nhóm đó. expected_schema là semantic "
            "output contract, được phép chứa field phục vụ downstream node theo IR contract. "
            "Không suy đoán physical columns; ánh xạ physical nằm trong catalog_slice.physical. "
            "Chỉ báo issue khi nêu được node_id tồn tại và invariant/ref vi phạm kiểm được."
        ),
    }


class PlanCritic:
    """Critic không sửa plan; chỉ trả issue list. Thiếu provider thì fail-closed."""

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def review(self, question: str, plan: LogicalQueryPlan) -> CriticReview:
        deterministic = validate_plan(plan)
        if not deterministic.valid:
            return CriticReview(issues=tuple(
                CriticIssue(code=issue.code, node_id=issue.node_id, message=issue.message)
                for issue in deterministic.issues
            ))
        if self.llm_client is None or not hasattr(self.llm_client, "critique_plan"):
            raise RuntimeError("Plan critic được yêu cầu nhưng chưa có LLM provider hỗ trợ P9.")
        output = CriticOutput.model_validate(
            self.llm_client.critique_plan(question, _critic_payload(question, plan))
        )
        node_ids = {node.node_id for node in plan.nodes}
        kept: list[CriticIssue] = []
        dropped: list[CriticIssue] = []
        for issue in output.issues:
            if issue.code in _DETERMINISTIC_COVERED:
                dropped.append(issue)  # validator đã pass nhóm này — phán đoán sai kiểm chứng được
            elif issue.node_id is not None and issue.node_id not in node_ids:
                dropped.append(issue)  # trỏ node không tồn tại — không kiểm được
            else:
                kept.append(issue)
        return CriticReview(issues=tuple(kept), dropped=tuple(dropped))
