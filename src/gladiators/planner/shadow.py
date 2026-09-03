"""Shadow routing and decomposition — ultimate solution §6.5 / §8.11 / P5.

Runs the topic router, context packer and decomposer alongside the live planner
and records what they *would* have done.  It never touches the plan, the gate
decision, or the answer.

This is the prescribed state, not a half-measure. §6.5 says a topic that has not
passed its gate falls back to the legacy broad slice and traces
``topic_gate_disabled`` without changing the capability decision; §8.11 says a
shadow verdict is recorded and absolutely not executed. The gate artifact is
currently closed pending six reviewer-owned metrics, so shadow is the only
honest way to have this machinery running on real traffic.

The point of running it at all is that a component nothing calls is a component
nobody is measuring. Shadow turns the routing metrics in §7.3 from a number
computed over an eval corpus into a number computed over what users actually ask.

**Every failure here is swallowed.** A shadow observation that can break a live
answer is worse than no observation, so this module reports its own errors as
data rather than raising them.
"""
from __future__ import annotations

import time
from typing import Any

from ..domain import topics
from .atoms import atomize_request
from .context_packer import context_metrics, pack_context
from .feasibility import analyze
from .prompt_library import build_atomic_plan_context
from .topic_router import TopicRouter

SHADOW_VERSION = "shadow.v1"


class ShadowObserver:
    """Computes routing/decomposition metadata for the trace. Never decides."""

    def __init__(self, router: TopicRouter | None = None, *, enabled: bool = True):
        self.router = router or TopicRouter()
        self.enabled = enabled

    def observe(
        self, question: str, request, digest, *, dataset_version: str,
        plan_refs: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        """Return trace fields. Returns an error record rather than raising."""
        if not self.enabled:
            return {"shadow_version": SHADOW_VERSION, "shadow_enabled": False}

        started = time.perf_counter()
        try:
            return self._observe(
                question, request, digest, dataset_version, plan_refs, started,
            )
        except Exception as error:  # noqa: BLE001 - shadow must never break a live answer
            return {
                "shadow_version": SHADOW_VERSION,
                "shadow_enabled": True,
                "shadow_error": f"{type(error).__name__}: {error}"[:200],
            }

    def _observe(self, question, request, digest, dataset_version, plan_refs, started):
        routing = self.router.route(question, request)

        countries: tuple[str, ...] = ()
        atom_count = 0
        if request is not None and digest is not None:
            atoms = atomize_request(digest, request)
            atom_count = len(atoms)
            countries = tuple(
                str(a.value) for a in atoms if a.kind == "country" and a.value
            )

        feasibility = analyze(request, routing, countries=countries) if request else None

        packed = None
        metrics: dict[str, Any] = {}
        if digest is not None:
            items = build_atomic_plan_context(digest, routing)
            packed = pack_context(
                "atomic_plan", dataset_version,
                getattr(digest, "normalized_question", "")[:0] or "shadow",
                routing.routing_hash, items,
            )
            metrics = context_metrics(
                packed, used_plan_refs=plan_refs,
                selected_relations=routing.required_relation_ids,
            )

        return {
            "shadow_version": SHADOW_VERSION,
            "shadow_enabled": True,
            # §6.5: four distinct states, traced separately.
            "routing_mode": routing.mode,
            "routing_hash": routing.routing_hash,
            "domain_topics": list(routing.domain_topic_ids),
            "aspect_topics": list(routing.aspect_topic_ids),
            "required_relations": list(routing.required_relation_ids),
            "topic_gate_version": routing.topic_gate_version,
            # The gate is closed, so the live path used the legacy broad slice.
            # Recording that explicitly keeps "shadow ran" distinguishable from
            # "shadow changed something", which it never does.
            "topic_gate_disabled": True,
            "context_applied": False,
            "atom_count": atom_count,
            "atomic_feasible": None if feasibility is None else feasibility.feasible,
            "atomic_blockers": [] if feasibility is None else list(feasibility.blockers),
            "target_grain": None if feasibility is None else feasibility.target_grain,
            "shadow_context_tokens": None if packed is None else packed.estimated_tokens,
            "shadow_context_hash": None if packed is None else packed.context_hash,
            "context_precision": metrics.get("context_precision"),
            "catalog_miss_count": metrics.get("catalog_miss_count"),
            "topics_registry_hash": topics.REGISTRY_HASH,
            "shadow_latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
