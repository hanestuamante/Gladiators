"""SubrequestPlanningService — ultimate solution §8.4, step 5.

Plans one subrequest at a time: routes it, packs a context scoped to it, and
builds an atomic plan — synthesizer first, model only if the synthesizer has no
grammar for it.

The service is injected rather than constructed inside the decomposer, and §8.4
is specific about why: the decomposer may not re-route the root. A component
that can rebuild the routing it was handed will eventually route differently
from the state its capability admission was decided against, and nothing
downstream would report the divergence. So the root ``RoutingResult`` is passed
through untouched and this service is the only thing allowed to route, and only
ever for a *new* subrequest.

Two consequences follow, both enforced here rather than by convention:

**No broad fallback when the root was not admitted.**  A subrequest inheriting a
broad slice its parent never earned would let decomposition become a way to see
more of the catalogue than the capability check permitted.

**Each subplan records its own routing, context hash, gate version and dataset
version.**  Without that a validator has to re-derive them from the plan, and a
re-derived value cannot detect the case where the plan and the context it was
built from disagree.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from ..domain import topics
from .context_packer import PackedContext, pack_context
from .execution_plan import (
    ExecutionOutputField,
    PlannedSubplanSpec,
    SubrequestProposal,
)
from .prompt_library import build_atomic_plan_context
from .query_ir import LogicalQueryPlan
from .synthesizer import synthesize
from .topic_router import RoutingResult, TopicRouter
from .validator import validate_plan

SERVICE_VERSION = "subrequest-planning.v1"

# §8.4 call budget: one planning call per subplan plus one bounded repair.
MAX_PLANNING_CALLS_PER_SUBPLAN = 1
MAX_REPAIRS_PER_SUBPLAN = 1


class SubrequestPlanningError(RuntimeError):
    def __init__(self, code: str, message: str, *, subplan_id: str = ""):
        super().__init__(message)
        self.code = code
        self.subplan_id = subplan_id


@dataclass
class SubrequestPlanningResult:
    spec: PlannedSubplanSpec
    source: str  # "synthesizer" | "llm" | "llm_repair"
    attempts: int = 0
    routing: RoutingResult | None = None
    packed_context: PackedContext | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def _hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()[:16]


def subrequest_digest_hash(root_digest, covered_atom_ids: tuple[str, ...]) -> str:
    """Derived deterministically from the root digest plus assigned atoms.

    §8.5 checks this against the same derivation, so a subrequest cannot claim a
    digest that does not follow from the request it was split out of.
    """
    root = getattr(root_digest, "model_dump", lambda **_: {})(mode="json")
    return _hash({"root": root, "atoms": sorted(covered_atom_ids)})


def _output_fields(plan: LogicalQueryPlan) -> tuple[ExecutionOutputField, ...]:
    """Canonical projection of the plan's own output shape.

    Taken from the plan rather than restated, because a hand-written field list
    that drifts from the plan is a schema mismatch nothing would catch until a
    composition tried to line two of them up.
    """
    from ..domain.catalog import CATALOG

    fields: list[ExecutionOutputField] = []
    for field_spec in plan.requested_output_shape:
        ref = field_spec.semantic_ref
        obj = CATALOG.get(ref) if ref else None
        unit = getattr(obj, "unit", None) or "dimension"
        currency = "local_currency" if unit == "local_currency" else None
        fields.append(ExecutionOutputField(
            name=field_spec.name, semantic_ref=ref, dtype=field_spec.type, unit=unit,
            currency_code=currency,
            # Money may not be summed across markets: VND and IDR have no rate
            # here, so a cross-scope aggregate would be a number with no unit.
            aggregatable_across_scope=unit != "local_currency",
        ))
    return tuple(fields)


class SubrequestPlanningService:
    """Routes, packs and plans a single subrequest (§8.4)."""

    def __init__(
        self, *, router: TopicRouter | None = None, plan_builder: Any | None = None,
        dataset_version: str = "unknown", root_admitted: bool = True,
        budget_tokens: int | None = None,
    ):
        self.router = router or TopicRouter()
        # Optional: only consulted when the synthesizer has no grammar.
        self.plan_builder = plan_builder
        self.dataset_version = dataset_version
        self.root_admitted = root_admitted
        self.budget_tokens = budget_tokens

    # -- step 5a: route and pack ------------------------------------------

    def route_and_pack(
        self, subrequest, digest, *, question: str | None = None,
    ) -> tuple[RoutingResult, PackedContext]:
        """Route this subrequest and pack a context scoped to it alone."""
        text = question or getattr(subrequest, "normalized_question", "") or ""
        routing = self.router.route(text, subrequest)

        if not self.root_admitted and routing.mode in {"unknown", "overflow"}:
            # Letting a subrequest fall back to the broad slice would make
            # decomposition a way to see more of the catalogue than the
            # capability check allowed.
            raise SubrequestPlanningError(
                "SUBREQUEST_BROAD_FALLBACK_FORBIDDEN",
                "Root capability chưa admit nên subrequest không được dùng broad slice.",
            )

        items = build_atomic_plan_context(digest, routing, allow_broad_slice=False)
        packed = pack_context(
            "atomic_plan", self.dataset_version, _hash(text), routing.routing_hash,
            items, budget_tokens=self.budget_tokens,
        )
        return routing, packed

    # -- step 5b: plan -----------------------------------------------------

    def plan_subrequest(
        self, proposal: SubrequestProposal, root_digest, *,
        country: str, question: str | None = None,
    ) -> SubrequestPlanningResult:
        subrequest = proposal.request
        routing, packed = self.route_and_pack(subrequest, root_digest, question=question)

        # Synthesizer first: it is deterministic, free, and where it has a
        # grammar it is strictly better than asking a model to rediscover one.
        attempts = 0
        source = "synthesizer"
        plan: LogicalQueryPlan | None = None
        synthesized = synthesize(subrequest, country) if subrequest is not None else None
        if synthesized is not None and validate_plan(synthesized.plan).valid:
            plan = synthesized.plan

        if plan is None and self.plan_builder is not None:
            attempts += 1
            source = "llm"
            plan = self._build_with_model(proposal, packed, routing, attempts)

        if plan is None:
            raise SubrequestPlanningError(
                "SUBREQUEST_PLAN_UNAVAILABLE",
                f"Không lập được atomic plan cho subrequest {proposal.subplan_id}.",
                subplan_id=proposal.subplan_id,
            )

        report = validate_plan(plan)
        if not report.valid:
            raise SubrequestPlanningError(
                "SUBREQUEST_PLAN_INVALID",
                f"Plan của {proposal.subplan_id} không qua validator.",
                subplan_id=proposal.subplan_id,
            )

        spec = PlannedSubplanSpec(
            subplan_id=proposal.subplan_id, request=subrequest,
            covered_atom_ids=proposal.covered_atom_ids,
            shared_atom_ids=proposal.shared_atom_ids,
            subrequest_digest_hash=subrequest_digest_hash(
                root_digest, proposal.covered_atom_ids,
            ),
            routing=routing, context_hash=packed.context_hash,
            topic_gate_version=routing.topic_gate_version,
            dataset_version=self.dataset_version,
            plan=plan, plan_hash=_hash(plan.model_dump(mode="json")),
            output_fields=_output_fields(plan),
        )
        return SubrequestPlanningResult(
            spec=spec, source=source, attempts=attempts, routing=routing,
            packed_context=packed,
            meta={
                "service_version": SERVICE_VERSION,
                "routing_mode": routing.mode,
                "context_tokens": packed.estimated_tokens,
                "grammar_path": getattr(synthesized, "grammar_path", None),
            },
        )

    def _build_with_model(self, proposal, packed, routing, attempts) -> LogicalQueryPlan | None:
        """One bounded call, plus at most one repair (§8.4 budget).

        Exceeding the budget fails closed rather than degrading to the nearest
        macro: a near-miss answer to a question that needed decomposition is a
        confidently wrong answer.
        """
        for attempt in range(MAX_PLANNING_CALLS_PER_SUBPLAN + MAX_REPAIRS_PER_SUBPLAN):
            try:
                candidate = self.plan_builder.build(
                    subplan_id=proposal.subplan_id, request=proposal.request,
                    packed_context=packed, routing=routing, attempt=attempt,
                )
            except Exception:  # noqa: BLE001 - a builder failure is not a crash
                return None
            if candidate is not None and validate_plan(candidate).valid:
                return candidate
        return None

    # -- step 5 over all subrequests --------------------------------------

    def plan_all(
        self, proposals: tuple[SubrequestProposal, ...], root_digest, *,
        country: str,
    ) -> tuple[SubrequestPlanningResult, ...]:
        results = []
        for proposal in proposals:
            results.append(self.plan_subrequest(proposal, root_digest, country=country))
        return tuple(results)
