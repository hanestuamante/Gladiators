"""P8 semantic planner with deterministic validation and one bounded repair."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from gladiators.domain.catalog import CATALOG
from gladiators.domain.relations import RELATIONS
from gladiators.agent.context import ContextBundle

from .analytical import build_analytical_plan, infer_deterministic_template
from .query_ir import LogicalQueryPlan
from .semantic_parser import AnalyticalRequest, CatalogSlicer
from .validator import PlanIssue, validate_plan


class OpenPlannerError(ValueError):
    pass


@dataclass(frozen=True)
class OpenPlannerResult:
    plan: LogicalQueryPlan
    mode: str
    attempts: int
    feedback: tuple[dict[str, Any], ...] = ()
    catalog_refs: tuple[str, ...] = ()
    context: dict[str, Any] | None = None


def _used_refs(plan: LogicalQueryPlan) -> set[str]:
    refs = {ref for node in plan.nodes for ref in node.refs + node.group_by}
    refs.update(predicate.ref for node in plan.nodes for predicate in node.predicates)
    refs.update(node.rank_by for node in plan.nodes if node.rank_by)
    refs.update(field.semantic_ref for field in plan.requested_output_shape if field.semantic_ref)
    return refs


class OpenAnalyticalPlanner:
    """LLM chỉ chọn semantic refs/IR; validator và compiler giữ quyền quyết định."""

    def __init__(
        self, llm_client: Any | None, catalog_limit: int = 30,
        planner_method: str = "plan_analytical",
    ):
        self.llm_client = llm_client
        self.catalog_limit = catalog_limit
        self.planner_method = planner_method
        self.slicer = CatalogSlicer()

    def _catalog_slice(self, question: str, request: AnalyticalRequest) -> tuple[str, ...]:
        lexical = [item.ref for item in self.slicer.select(question, self.catalog_limit)]
        required = [
            item.ref for item in request.requested_measures + request.requested_dimensions
            if item.ref
        ] + [predicate.field_ref for predicate in request.filters]
        ordered = list(dict.fromkeys(required + ["dim.country", "dim.date", "entity.product_listing"] + lexical))
        return tuple(ordered[: self.catalog_limit])

    @staticmethod
    def _catalog_payload(refs: tuple[str, ...]) -> list[dict[str, Any]]:
        return [
            {
                "ref": ref, "kind": CATALOG[ref].kind, "type": CATALOG[ref].type,
                "unit": CATALOG[ref].unit, "grain": CATALOG[ref].grain,
                "valid_aggregations": CATALOG[ref].valid_aggregations,
                "allowed_filters": CATALOG[ref].allowed_filters,
                "time_semantics": CATALOG[ref].time_semantics,
                "answerability": CATALOG[ref].answerability,
                "source_tier": CATALOG[ref].source_tier,
                "caveats": CATALOG[ref].caveats,
                "traps": CATALOG[ref].traps,
            }
            for ref in refs
        ]

    @staticmethod
    def _relations_payload() -> list[dict[str, Any]]:
        return [
            {
                "name": relation.name, "left": relation.left, "right": relation.right,
                "cardinality": relation.cardinality, "input_grain": relation.input_grain,
                "output_grain": relation.output_grain, "fanout_effect": relation.fanout_effect,
                "dedupe_strategy": relation.dedupe_strategy,
                "temporal_validity": relation.temporal_validity,
            }
            for relation in RELATIONS.values()
        ]

    def plan(
        self, question: str, request: AnalyticalRequest, country: str,
        context_bundle: ContextBundle | None = None,
    ) -> OpenPlannerResult:
        template = infer_deterministic_template(request)
        if template:
            return OpenPlannerResult(
                plan=build_analytical_plan(template, country), mode="deterministic_template", attempts=0,
            )
        if self.llm_client is None or not hasattr(self.llm_client, self.planner_method):
            raise OpenPlannerError("Không có semantic planner provider cho câu hỏi ngoài certified template.")

        refs = self._catalog_slice(question, request)
        base_payload = {
            "question": question,
            "analytical_request": request.model_dump(mode="json"),
            "catalog_slice": self._catalog_payload(refs),
            "relations": self._relations_payload(),
            "constraints": {
                "ir_version": "1.0", "semantic_refs_only": True,
                "allowed_dates": ["2026-07-01", "2026-07-02", "2026-07-03"],
                "max_nodes": 12, "max_depth": 6, "max_subplans": 4,
                "country": country, "repair_limit": 1,
            },
        }
        if context_bundle is not None:
            context_bundle = context_bundle.model_copy(
                update={"payload": base_payload},
            ).with_hash()
            base_payload = context_bundle.payload
        feedback: list[dict[str, Any]] = []
        for attempt in range(2):
            payload = {**base_payload, "validator_feedback": feedback or None, "attempt": attempt + 1}
            try:
                raw = getattr(self.llm_client, self.planner_method)(payload)
                plan = LogicalQueryPlan.model_validate(raw.get("plan", raw) if isinstance(raw, dict) else raw)
            except (ValidationError, TypeError, ValueError, RuntimeError, KeyError) as exc:
                feedback = [{"code": "schema_invalid", "node_id": None, "message": str(exc)}]
                continue
            validation = validate_plan(plan)
            issues = [issue.model_dump() for issue in validation.issues]
            outside = sorted(_used_refs(plan) - set(refs))
            issues.extend(
                PlanIssue(
                    code="missing_semantic_object", node_id=None,
                    message=f"Ref nằm ngoài catalog slice: {ref}",
                ).model_dump()
                for ref in outside
            )
            if not issues:
                return OpenPlannerResult(
                    plan=plan, mode="llm_semantic_plan", attempts=attempt + 1,
                    feedback=tuple(feedback), catalog_refs=refs,
                    context=context_bundle.trace_summary() if context_bundle else None,
                )
            feedback = issues
        summary = "; ".join(f"{item['code']}: {item['message']}" for item in feedback[:5])
        raise OpenPlannerError(f"Plan không hợp lệ sau 1 vòng repair: {summary}")
