"""Deterministic Plan Validator — V2 mục 7.7, không dùng LLM."""
from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict

from gladiators.domain.catalog import CATALOG
from gladiators.domain.invariant_handlers import (
    InvariantContext,
    InvariantViolation,
    enforce_invariants,
)
from gladiators.domain.relations import RELATIONS, RELATION_LEFT_SOURCES

from .query_ir import LogicalQueryPlan, PlanNode

IssueCode = Literal[
    "missing_semantic_object", "wrong_filter", "wrong_join_path", "grain_mismatch",
    "fanout_risk", "unit_mismatch", "temporal_mismatch", "unsupported_claim",
    "budget_exceeded", "schema_invalid", "tier_violation", "non_physical_grouping",
]

# Outward code for a validation issue, so a plan defect reaches the caller as a
# decision that can be looked up rather than an uncaught CompilationError.
RULE_ID_BY_ISSUE: dict[str, str] = {"non_physical_grouping": "A19-PLAN-GROUPING"}
DEFAULT_PLAN_RULE_ID = "A19-PLAN"


def plan_rule_id(issues: tuple[PlanIssue, ...] | list[PlanIssue]) -> str:
    for issue in issues:
        if issue.code in RULE_ID_BY_ISSUE:
            return RULE_ID_BY_ISSUE[issue.code]
    return DEFAULT_PLAN_RULE_ID
# §E3: snapshot được quản trị sống ở ``domain.invariant_handlers`` cùng rule thi
# hành chúng (INV-SNAPSHOT-SCOPE). Giữ một set thứ hai ở đây là cách hai danh
# sách ngày lệch nhau khi dataset đổi — W30 làm nó thành một HÀM vì danh sách
# giờ đọc từ bản dữ liệu, và một `frozenset` tính lúc import sẽ đóng băng lịch
# của bản dữ liệu có mặt lúc process khởi động.
def allowed_dates() -> frozenset[str]:
    from gladiators.domain.invariant_handlers import governed_dates

    return frozenset(governed_dates())


class PlanIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: IssueCode
    node_id: str | None = None
    message: str


class PlanValidationResult(BaseModel):
    valid: bool
    issues: tuple[PlanIssue, ...]
    depth: int


def _depths(plan: LogicalQueryPlan, issues: list[PlanIssue]) -> tuple[dict[str, int], dict[str, PlanNode]]:
    nodes = {node.node_id: node for node in plan.nodes}
    visiting: set[str] = set()
    memo: dict[str, int] = {}

    def visit(node_id: str) -> int:
        if node_id not in nodes:
            issues.append(PlanIssue(code="schema_invalid", node_id=node_id, message="Input node không tồn tại."))
            return 0
        if node_id in visiting:
            issues.append(PlanIssue(code="schema_invalid", node_id=node_id, message="Plan phải là DAG, phát hiện cycle."))
            return 0
        if node_id in memo:
            return memo[node_id]
        visiting.add(node_id)
        depth = 1 + max((visit(parent) for parent in nodes[node_id].inputs), default=0)
        visiting.remove(node_id)
        memo[node_id] = depth
        return depth

    for node_id in nodes:
        visit(node_id)
    return memo, nodes


def _ancestors(node: PlanNode, nodes: dict[str, PlanNode]) -> tuple[PlanNode, ...]:
    result: list[PlanNode] = []
    seen: set[str] = set()
    stack = list(node.inputs)
    while stack:
        node_id = stack.pop()
        if node_id in seen or node_id not in nodes:
            continue
        seen.add(node_id)
        parent = nodes[node_id]
        result.append(parent)
        stack.extend(parent.inputs)
    return tuple(result)


def validate_plan(plan: LogicalQueryPlan) -> PlanValidationResult:
    issues: list[PlanIssue] = []
    depths, nodes = _depths(plan, issues)
    depth = max(depths.values(), default=0)

    if len(plan.nodes) > plan.budget.max_nodes:
        issues.append(PlanIssue(code="budget_exceeded", message="Số node vượt max_nodes."))
    if depth > plan.budget.max_depth:
        issues.append(PlanIssue(code="budget_exceeded", message="Độ sâu DAG vượt max_depth."))
    if plan.subplan_count > plan.budget.max_subplans:
        issues.append(PlanIssue(code="budget_exceeded", message="Số subplan vượt max_subplans."))
    # W11.2 §12.3.1: một node share với ShareDefinition phải khai schema đúng
    # ba ref tử/mẫu/tỷ lệ — plan KHÔNG được tự thay tử số hay mẫu số. Validator
    # mở closure từ registry, không tin schema plan tự khai.
    from gladiators.domain.metrics import METRICS

    for node in plan.nodes:
        if node.op != "Aggregate" or node.aggregation != "share":
            continue
        for ref in node.refs:
            spec = METRICS.get(ref.split(".", 1)[1]) if ref.startswith("derived.") else None
            if spec is None or spec.share is None:
                continue
            schema_refs = [field.semantic_ref for field in node.expected_schema]
            required = [
                f"derived.{spec.share.numerator_metric}",
                f"derived.{spec.share.denominator_metric}",
                ref,
            ]
            if schema_refs[-3:] != required:
                issues.append(PlanIssue(
                    code="schema_invalid", node_id=node.node_id,
                    message="Share phải khai đúng ba ref tử/mẫu/tỷ lệ theo "
                            "ShareDefinition: " + ", ".join(required),
                ))

    if plan.output_node not in nodes:
        issues.append(PlanIssue(code="schema_invalid", message="output_node không tồn tại."))
    elif nodes[plan.output_node].expected_schema != plan.requested_output_shape:
        issues.append(PlanIssue(code="schema_invalid", node_id=plan.output_node,
                                message="Schema output node không khớp requested_output_shape."))
    # time_scope ngoài 3 snapshot: kiểm bởi INV-SNAPSHOT-SCOPE qua dispatcher ở
    # cuối hàm. Nhánh hard-code cũ bị xoá cùng merge unit để không chấm hai lần.

    consumers: dict[str, list[PlanNode]] = defaultdict(list)
    for node in plan.nodes:
        for input_id in node.inputs:
            consumers[input_id].append(node)

        node_refs = set(node.refs + node.group_by)
        if node.rank_by:
            node_refs.add(node.rank_by)
        node_refs.update(field.semantic_ref for field in node.expected_schema if field.semantic_ref)
        for ref in sorted(node_refs):
            if ref not in CATALOG:
                issues.append(PlanIssue(code="missing_semantic_object", node_id=node.node_id,
                                        message=f"Semantic ref không tồn tại: {ref}"))
            elif CATALOG[ref].source_tier != "btc_dataset" or CATALOG[ref].kind == "context":
                issues.append(PlanIssue(
                    code="tier_violation", node_id=node.node_id,
                    message=f"{ref} thuộc tier/context ngoài btc_dataset và không được vào LogicalQueryPlan.",
                ))

        # A3: grouping by a ref with no physical column used to pass validation
        # and then fail in ``_column_for``. The validator believed the catalog's
        # declaration; only the compiler consulted reality. Ask the same question
        # the compiler will ask, one layer earlier.
        for ref in sorted(set(node.group_by) | ({node.rank_by} if node.rank_by else set())):
            obj = CATALOG.get(ref)
            if obj is not None and not obj.physical and not obj.counts_unit:
                issues.append(PlanIssue(
                    code="non_physical_grouping", node_id=node.node_id,
                    message=(
                        f"{ref} là đơn vị phân tích, không có cột vật lý để GROUP BY/ORDER BY."
                    ),
                ))

        for predicate in node.predicates:
            obj = CATALOG.get(predicate.ref)
            if obj is None:
                issues.append(PlanIssue(code="missing_semantic_object", node_id=node.node_id,
                                        message=f"Predicate ref không tồn tại: {predicate.ref}"))
            elif predicate.op not in obj.allowed_filters:
                issues.append(PlanIssue(code="wrong_filter", node_id=node.node_id,
                                        message=f"Filter {predicate.op} không hợp lệ cho {predicate.ref}."))
            elif obj.source_tier != "btc_dataset" or obj.kind == "context":
                issues.append(PlanIssue(
                    code="tier_violation", node_id=node.node_id,
                    message=f"Predicate {predicate.ref} thuộc tier/context ngoài btc_dataset.",
                ))

        if node.op == "Scan" and node.source is None:
            issues.append(PlanIssue(code="schema_invalid", node_id=node.node_id,
                                    message="Scan bắt buộc khai báo source artifact."))
        if node.op != "Scan" and node.source is not None:
            issues.append(PlanIssue(code="schema_invalid", node_id=node.node_id,
                                    message="Chỉ Scan được khai báo source artifact."))

        if node.op == "Join":
            relation = RELATIONS.get(node.relation or "")
            if relation is None:
                issues.append(PlanIssue(code="wrong_join_path", node_id=node.node_id,
                                        message=f"Relation không tồn tại: {node.relation}"))
            else:
                ancestor_sources = {item.source for item in _ancestors(node, nodes) if item.source}
                allowed_sources = set(RELATION_LEFT_SOURCES.get(relation.name, ()))
                if not ancestor_sources or not ancestor_sources.issubset(allowed_sources):
                    issues.append(PlanIssue(
                        code="wrong_join_path", node_id=node.node_id,
                        message=(
                            f"Relation {relation.name} yêu cầu left source {sorted(allowed_sources)}, "
                            f"nhận {sorted(ancestor_sources)}."
                        ),
                    ))
                if node.input_grain != relation.input_grain or node.output_grain != relation.output_grain:
                    issues.append(PlanIssue(code="grain_mismatch", node_id=node.node_id,
                                            message="Grain Join không khớp relation registry."))
                if relation.fanout_effect != "none" and node.dedupe_policy != relation.dedupe_strategy:
                    issues.append(PlanIssue(code="fanout_risk", node_id=node.node_id,
                                            message="Join fanout thiếu dedupe policy bắt buộc."))

        if node.op == "Aggregate":
            for ref in node.refs:
                obj = CATALOG.get(ref)
                if obj and node.aggregation not in obj.valid_aggregations:
                    issues.append(PlanIssue(code="wrong_filter", node_id=node.node_id,
                                            message=f"Aggregation {node.aggregation} không hợp lệ cho {ref}."))
            ancestors = _ancestors(node, nodes)
            has_single_snapshot = len(plan.time_scope) == 1 or "dim.date" in node.group_by or any(
                p.ref == "dim.date" and p.op == "eq" for ancestor in ancestors for p in ancestor.predicates
            )
            if not has_single_snapshot:
                issues.append(PlanIssue(code="temporal_mismatch", node_id=node.node_id,
                                        message="Aggregate cross-sectional phải chọn đúng một snapshot."))

        if (
            node.op == "TemporalCompare" and node.time_scope is not None
            and len(node.time_scope) == 2
        ):
            # W6.1: dạng hai đầu mút phải khai ĐÚNG ba trường start/end/delta
            # và trả đúng một dòng.
            names = [field.name for field in node.expected_schema]
            shape_ok = (
                len(names) == 3
                and names[0].endswith("_start") and names[1].endswith("_end")
                and names[2].endswith("_delta")
            )
            if not shape_ok or node.expected_cardinality != "1":
                issues.append(PlanIssue(
                    code="schema_invalid", node_id=node.node_id,
                    message="TemporalCompare hai đầu mút phải khai đúng ba trường "
                            "_start/_end/_delta và cardinality 1.",
                ))
        if node.op == "TemporalCompare" and len(plan.time_scope) < 2:
            issues.append(PlanIssue(code="temporal_mismatch", node_id=node.node_id,
                                    message="TemporalCompare cần ít nhất 2 snapshot hợp lệ."))
        if node.op == "Dedupe" and node.dedupe_policy not in {
            "one_row_per_listing", "one_snapshot_per_listing", "metric_grain_required",
        }:
            issues.append(PlanIssue(code="schema_invalid", node_id=node.node_id,
                                    message="Dedupe bắt buộc có policy thuộc allow-list."))
        if node.op == "DeriveMetric" and any(
            CATALOG.get(ref) is None or CATALOG[ref].kind != "derived_metric" for ref in node.refs
        ):
            issues.append(PlanIssue(code="schema_invalid", node_id=node.node_id,
                                    message="DeriveMetric chỉ nhận derived metric refs."))
        if node.op == "ResolveValue" and (
            not node.refs or any(CATALOG.get(ref) is None or CATALOG[ref].kind != "entity" for ref in node.refs)
        ):
            issues.append(PlanIssue(code="schema_invalid", node_id=node.node_id,
                                    message="ResolveValue bắt buộc nhận entity refs."))
        if node.op == "Similarity" and "derived.similarity_score" not in node.refs:
            issues.append(PlanIssue(code="schema_invalid", node_id=node.node_id,
                                    message="Similarity bắt buộc emit derived.similarity_score."))
        if node.op == "Union" and len(node.inputs) != 2:
            issues.append(PlanIssue(code="schema_invalid", node_id=node.node_id,
                                    message="Union bắt buộc có đúng hai input."))
        if node.op == "Rank" and (not node.rank_by or node.limit is None):
            issues.append(PlanIssue(code="schema_invalid", node_id=node.node_id,
                                    message="Rank bắt buộc có rank_by và limit."))
        if len(set(node.units) & {"VND", "IDR"}) > 1:
            issues.append(PlanIssue(code="unit_mismatch", node_id=node.node_id,
                                    message="Không trộn VND và IDR trong cùng measure."))
        if any(term in invariant.lower() for invariant in node.invariants for term in ("causal", "forecast")):
            issues.append(PlanIssue(code="unsupported_claim", node_id=node.node_id,
                                    message="IR v1.0 không hỗ trợ causal/forecast claim."))

    # §E3: hard invariant của stage "plan" chạy qua dispatcher, không còn bản
    # hard-code song song. Sentinel/dedupe/shelf/currency/snapshot-scope trước
    # đây được kiểm ở đây bằng set ref riêng — và set đó đã lệch khỏi spec.
    issues.extend(_issue_from(violation) for violation in enforce_invariants(
        "plan", InvariantContext(stage="plan", plan=plan)
    ))
    return PlanValidationResult(valid=not issues, issues=tuple(issues), depth=depth)


# Violation typed → ``PlanIssue``. Dispatcher chỉ nói rule nào vỡ; ánh xạ sang
# code mà planner/critic đã biết đọc thuộc về tầng này.
_INVARIANT_ISSUE_CODE: dict[str, str] = {
    "INV-PRICE-SENTINEL-EXCLUDED": "wrong_filter",
    "INV-DEDUPE-BEFORE-AGGREGATE": "fanout_risk",
    "INV-SHELF-NOT-PLATFORM-CATEGORY": "wrong_join_path",
    "INV-CURRENCY-NO-MIX": "unit_mismatch",
    "INV-SNAPSHOT-SCOPE": "temporal_mismatch",
}


def _issue_from(violation: InvariantViolation) -> PlanIssue:
    detail = ", ".join(f"{key}={value}" for key, value in sorted(violation.details.items()))
    return PlanIssue(
        code=_INVARIANT_ISSUE_CODE.get(violation.invariant_id, "schema_invalid"),
        node_id=violation.node_id,
        message=f"{violation.invariant_id}: {violation.message_key}"
                + (f" ({detail})" if detail else ""),
    )
