"""LegacyPlanningInputFactory — ultimate solution §8.8.

Converts a legacy ``plan(question, request, country, ...)`` call into the single
typed ``DecomposerInput`` the decomposer accepts.  §8.8 puts this in its own
class for one reason: the compatibility adapter must contain *no planning
logic*, and a conversion that lives inside the adapter always grows some.

The rule that keeps this honest is the assertion below. When a legacy caller
passes a ``country`` separately from the digest, the factory checks they agree
and fails if they do not. It never rewrites the digest to make the input line
up -- doing that would let a caller silently redirect a request to a different
market, which is the exact class of scope bug the atoms layer exists to catch.

This module is deleted together with the adapter.
"""
from __future__ import annotations

from ..agent.context import RequestDigest
from .context_packer import PackedContext, pack_context
from .decomposer import DecomposerInput, DecomposerInputMismatch
from .execution_plan import ExecutionContextSnapshot
from .topic_router import RoutingResult, TopicRouter


class LegacyPlanningInputFactory:
    """Normalises legacy arguments. Contains no planning rules."""

    def __init__(self, *, router: TopicRouter | None = None,
                 dataset_version: str = "unknown"):
        self.router = router or TopicRouter()
        self.dataset_version = dataset_version

    def from_legacy(
        self,
        *,
        question: str,
        request,
        country: str | None = None,
        digest: RequestDigest | None = None,
        context_bundle=None,
        routing: RoutingResult | None = None,
        context_snapshot: ExecutionContextSnapshot | None = None,
    ) -> DecomposerInput:
        normalized = getattr(request, "normalized_question", None) or question
        digest = digest or self._digest_from(request, normalized, country)

        if country and digest.countries and country not in digest.countries:
            # Never reconcile by rewriting the digest: that would let a caller
            # redirect a request to a market it did not ask about.
            raise DecomposerInputMismatch(
                f"country '{country}' không nằm trong digest.countries {digest.countries}"
            )

        routing = routing if routing is not None else self.router.route(normalized, request)
        snapshot = context_snapshot or self._snapshot()
        packed = self._packed(context_bundle, routing, snapshot)

        return DecomposerInput(
            normalized_question=normalized, request=request, digest=digest,
            routing=routing, packed_context=packed, context_snapshot=snapshot,
        )

    def _digest_from(self, request, normalized: str, country: str | None) -> RequestDigest:
        countries = (country,) if country else ()
        return RequestDigest(
            normalized_question=normalized,
            language=getattr(request, "language", "unknown"),
            intent="analytical", countries=countries,
            requested_measures=tuple(
                b.ref for b in getattr(request, "requested_measures", ()) or () if b.ref
            ),
            requested_dimensions=tuple(
                b.ref for b in getattr(request, "requested_dimensions", ()) or () if b.ref
            ),
            requested_output_shape=getattr(request, "requested_output_shape", "table"),
            date_range=tuple(getattr(getattr(request, "time_scope", None), "dates", ()) or ()),
        )

    def _snapshot(self) -> ExecutionContextSnapshot:
        from ..domain import topics
        from ..domain.alias_index import default_alias_index
        from ..domain.bindings import default_binding_snapshot
        from .decomposition_validator import DECOMPOSITION_GATE_VERSION
        from .topic_router import TOPIC_GATE_VERSION

        # §E1.3: catalog_hash và relation_hash trước đây điền bằng
        # ``topics.REGISTRY_HASH``, tức chữ ký của registry KHÁC. Catalog hoặc
        # relation đổi mà topic không đổi thì snapshot vẫn khai là cùng một thế
        # giới ngữ nghĩa — đúng loại lỗi mà snapshot sinh ra để chặn.
        binding = default_binding_snapshot()
        return ExecutionContextSnapshot(
            dataset_version=self.dataset_version,
            catalog_hash=binding.catalog_hash, alias_index_hash=default_alias_index().index_hash,
            relation_hash=binding.relation_hash, invariant_hash=binding.invariant_hash,
            capability_hash="legacy", topic_hash=topics.REGISTRY_HASH,
            config_hash="legacy", topic_gate_version=TOPIC_GATE_VERSION,
            decomposition_gate_version=DECOMPOSITION_GATE_VERSION,
            binding_hash=binding.binding_hash,
        )

    def _packed(self, context_bundle, routing, snapshot) -> PackedContext:
        digest_hash = getattr(context_bundle, "context_hash", None) or "legacy"
        return pack_context(
            "atomic_plan", snapshot.dataset_version, digest_hash,
            routing.routing_hash, [],
        )
