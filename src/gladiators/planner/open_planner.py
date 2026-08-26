"""P8 semantic planner with deterministic validation and one bounded repair."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from gladiators.domain.catalog import CATALOG
from gladiators.domain.relations import RELATIONS
from gladiators.agent.context import ContextBundle

from .analytical import build_analytical_plan, infer_deterministic_template
from .synthesizer import synthesize
from .query_ir import CARDINALITY_GRAMMAR, LogicalQueryPlan
from .semantic_parser import AnalyticalRequest, CatalogSlicer
from .validator import PlanIssue, validate_plan


class OpenPlannerError(ValueError):
    """Planning failure with a UI-safe message and machine detail kept apart.

    §4.3/§4.4: schema errors must not reach the UI.  ``str(exc)`` used to carry
    the raw pydantic text ("1 validation error for LogicalQueryPlan nodes.0...")
    straight into the answer a user reads.  The structured issues stay on
    ``.issues`` for the trace and the bounded repair loop.
    """

    def __init__(self, message: str, issues: tuple[dict[str, Any], ...] = ()):
        super().__init__(message)
        self.issues = issues


@dataclass(frozen=True)
class OpenPlannerResult:
    plan: LogicalQueryPlan
    mode: str
    attempts: int
    feedback: tuple[dict[str, Any], ...] = ()
    catalog_refs: tuple[str, ...] = ()
    context: dict[str, Any] | None = None


LATEST_SNAPSHOT = "2026-07-03"


def _synthesis_beats_template(request: AnalyticalRequest) -> bool:
    """True when a certified template would answer this request incorrectly.

    Two signals, both verified against the data:

    * ascending ranking -- every template ranks descending, so "giá thấp nhất"
      came back as 3.033.180 instead of 1.000;
    * a named date other than the latest snapshot -- templates hard-code
      2026-07-03, so "ngày 01/07" came back with 668 instead of 581.
    """
    if request.ranking is not None and request.ranking.direction == "asc":
        return True
    # Một điều kiện ngoài country/date: template không có chỗ diễn đạt nó, nên
    # nó IM LẶNG biến mất. "Bao nhiêu listing của shop official tại VN" trả 668
    # — toàn bộ thị trường — trong khi đáp án là 465. Số sai tự tin, không phải
    # từ chối. (WP-A4 bind điều kiện, WP-A1 lọc nó sau join.)
    if any(
        predicate.field_ref not in {"dim.country", "dim.date"}
        for predicate in request.filters
    ):
        return True
    dates = tuple(request.time_scope.dates) if request.time_scope else ()
    if len(dates) == 1 and dates[0] != LATEST_SNAPSHOT:
        return True
    # Counting any unit other than the listing has no template at all, so the
    # alternative here is not a wrong number but an A19 refusal for a question
    # the data answers ("có bao nhiêu shop ở VN" -> 10).
    if any(
        item.ref and item.ref != "derived.product_count" and CATALOG[item.ref].counts_unit
        for item in request.requested_measures
    ):
        return True
    # A grouping the templates lack: listing_count collapses "theo từng shop"
    # into one unfiltered number. Enabling this needed the multi-row answer
    # renderer first -- before that, by_metric kept only the last row and the
    # answer read "Có 120 listing", one arbitrary shop's count presented as the
    # total. The synthesizer's unbound-qualifier guard keeps this from firing on
    # questions whose restriction was never parsed ("shop official").
    return bool([
        item for item in request.requested_dimensions
        if item.ref and item.ref not in {"dim.country", "dim.date"}
    ])


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
        use_synthesizer: bool = True,
    ):
        self.llm_client = llm_client
        self.catalog_limit = catalog_limit
        self.planner_method = planner_method
        # The N-version alternate turns this off: comparing an LLM plan against a
        # deterministic one is not N-version, it is one planner plus a fixture.
        # P10 has to reach the model or the disagreement signal means nothing.
        self.use_synthesizer = use_synthesizer
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
        # §5, first slice. The synthesizer only takes over where the frozen
        # templates are known to be *wrong* rather than merely absent: an
        # ascending ranking (templates are all "highest" and inverted the answer)
        # and a named non-latest date (templates hard-code 2026-07-03). In both
        # cases today's alternative is an A22 block, so synthesising is strictly
        # better than the status quo.
        #
        # It deliberately does NOT take over every in-grammar question yet. Doing
        # so answered "Rating theo brand không tồn tại tại VN" -- an adversarial
        # empty-result case -- with all 19 brands, because the parser never bound
        # the non-existent brand and the synthesizer silently widened the
        # question. Widening the trigger needs the entity-binding guard first.
        if self.use_synthesizer and _synthesis_beats_template(request):
            synthesized = synthesize(request, country)
            if synthesized is not None and validate_plan(synthesized.plan).valid:
                return OpenPlannerResult(
                    plan=synthesized.plan, mode="deterministic_synthesis", attempts=0,
                )
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
                # §4.3: the prompt states the same grammar the validator enforces.
                "expected_cardinality_grammar": CARDINALITY_GRAMMAR,
                "expected_cardinality_note": (
                    "Dùng số chính xác ('1') hoặc bound ('<=5'). Alias số nhiều chỉ hợp lệ "
                    "khi node khai limit; không tự đặt bound khi chưa biết số dòng."
                ),
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
        # Codes only in the message: they are a closed, reviewed vocabulary. The
        # free-text detail (which can embed a raw schema dump) stays on .issues
        # for the trace, never in the sentence a user reads.
        codes = sorted({str(item.get("code", "unknown")) for item in feedback})
        raise OpenPlannerError(
            "Không lập được plan hợp lệ sau một vòng sửa có ràng buộc"
            + (f" ({', '.join(codes)})" if codes else "")
            + ".",
            issues=tuple(feedback),
        )
