"""TopicRouter — ultimate solution §6.5.

Selects which slice of the semantic layer a question needs.  This is MAC-SQL's
Selector: it narrows the schema the planner sees, so a wrong narrowing is worse
than no narrowing -- the planner cannot ask for what it was never shown.

Three properties follow from that asymmetry:

**Resolved refs always beat alias guesses.**  When the structured request has
already bound a ref, the alias index is not consulted for it.  Lexical fallback
runs only over phrases nothing else resolved.

**Overflow keeps everything.**  ``overflow`` does not mean "more than two
topics"; §6.5 is explicit that the router never truncates.  Dropping a third
topic is how a question silently gets answered on two-thirds of its meaning --
exactly the class of bug the date-window and country-scope probes caught.

**Four failure states, not one.**  ``core_only``, ``unknown``, ``overflow`` and
``gate_disabled`` mean different things and are traced separately; collapsing
them would make the routing metrics unreadable.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..domain import topics
from ..domain.alias_index import AliasIndex, default_alias_index, normalize_surface
from ..domain.catalog import CATALOG
from ..domain.invariants import REGISTRY_HASH as INVARIANT_HASH

TOPIC_GATE_VERSION = "topic-gate.v1"
ROUTER_VERSION = "topic-router.v1"

RouteMode = Literal["core_only", "topic_scoped", "multi_topic", "unknown", "overflow"]

# Aspects are derived from request structure, never from words in the question:
# "giảm" appears in both a temporal-change question and a discount question.
_ASPECT_TEMPORAL = "A1"
_ASPECT_RANKING = "A2"
_ASPECT_GROUP_COMPARE = "A3"
_ASPECT_DISTRIBUTION = "A4"
_ASPECT_EXTERNAL = "A5"

# Refs the parser supplies for every request regardless of what was asked.
_SCOPE_REFS = frozenset({"dim.country", "dim.date"})


class RoutingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    mode: RouteMode
    domain_topic_ids: tuple[str, ...] = ()
    aspect_topic_ids: tuple[str, ...] = ()
    resolved_refs: tuple[str, ...] = ()
    unresolved_refs: tuple[str, ...] = ()
    required_relation_ids: tuple[str, ...] = ()
    routing_reasons: tuple[str, ...] = ()
    overflow_reason: str | None = None
    topic_gate_version: str = TOPIC_GATE_VERSION
    routing_hash: str = ""

    def effective_refs(self) -> tuple[str, ...]:
        """Refs the packer may draw on: CORE plus every selected topic."""
        refs = list(topics.TOPICS["CORE"].all_refs())
        for topic_id in self.domain_topic_ids + self.aspect_topic_ids:
            refs.extend(topics.effective_refs(topic_id))
        # Required refs travel through the route even when their owner topic was
        # not selected (§6.5) -- otherwise a bound ref becomes unrenderable.
        refs.extend(self.resolved_refs)
        return tuple(dict.fromkeys(refs))


class TopicRouter:
    def __init__(
        self,
        alias_index: AliasIndex | None = None,
        *,
        gate_enabled: bool = True,
    ):
        self.alias_index = alias_index or default_alias_index()
        self.gate_enabled = gate_enabled

    # -- ref resolution ----------------------------------------------------

    def _refs_from_request(self, request) -> tuple[list[str], list[str]]:
        """Refs the structured request already bound, plus phrases it could not."""
        resolved: list[str] = []
        unresolved: list[str] = []
        if request is None:
            return resolved, unresolved
        for item in list(getattr(request, "requested_measures", ()) or ()) + list(
            getattr(request, "requested_dimensions", ()) or ()
        ):
            ref = getattr(item, "ref", None)
            if ref and ref in CATALOG:
                resolved.append(ref)
            else:
                surface = getattr(item, "surface_text", None)
                if surface:
                    unresolved.append(str(surface))
        # Predicate fields are bound refs too: a country filter is what makes a
        # question multi-market, and dropping it here would lose the aspect.
        for predicate in getattr(request, "filters", ()) or ():
            ref = getattr(predicate, "field_ref", None)
            if ref and ref in CATALOG:
                resolved.append(ref)
        return list(dict.fromkeys(resolved)), list(dict.fromkeys(unresolved))

    @staticmethod
    def _country_values(request) -> tuple[str, ...]:
        for predicate in getattr(request, "filters", ()) or ():
            if getattr(predicate, "field_ref", None) != "dim.country":
                continue
            value = getattr(predicate, "value_binding", None)
            if isinstance(value, (list, tuple, set)):
                return tuple(str(v) for v in value)
            if value is not None:
                return (str(value),)
        return ()

    def _alias_fallback(self, text: str, already: set[str]) -> tuple[list[str], list[str]]:
        """Lexical candidates for what the request did not bind.

        An ambiguous surface contributes nothing: picking one of two refs by
        index order answers a different question than the one asked, and the
        caller has no way to know it happened.
        """
        found: list[str] = []
        ambiguous: list[str] = []
        for match in self.alias_index.find_in(normalize_surface(text)):
            if match.ambiguous:
                ambiguous.append(match.surface)
                continue
            ref = match.refs[0]
            if ref not in already:
                found.append(ref)
        return list(dict.fromkeys(found)), ambiguous

    # -- aspects -----------------------------------------------------------

    def _aspects(self, request) -> tuple[list[str], list[str]]:
        aspects: list[str] = []
        reasons: list[str] = []
        if request is None:
            return aspects, reasons
        time_scope = getattr(request, "time_scope", None)
        dates = tuple(getattr(time_scope, "dates", ()) or ()) if time_scope else ()
        mode = getattr(time_scope, "mode", None) if time_scope else None
        if len(dates) > 1 or mode == "transition" or getattr(request, "comparison", None):
            aspects.append(_ASPECT_TEMPORAL)
            reasons.append("aspect:temporal_window")
        if getattr(request, "ranking", None) is not None:
            aspects.append(_ASPECT_RANKING)
            reasons.append("aspect:ranking")
        grouped = tuple(getattr(request, "grouping", ()) or ()) or tuple(
            item for item in getattr(request, "requested_dimensions", ()) or ()
            if getattr(item, "ref", None)
        )
        if grouped:
            aspects.append(_ASPECT_GROUP_COMPARE)
            reasons.append("aspect:grouping")
        if len(self._country_values(request)) > 1:
            if _ASPECT_GROUP_COMPARE not in aspects:
                aspects.append(_ASPECT_GROUP_COMPARE)
            reasons.append("aspect:multi_country")
        operators = {str(op).lower() for op in getattr(request, "analytical_operators", ()) or ()}
        distribution = operators & {"median", "distribution", "percentile", "avg", "mean", "quantile"}
        if distribution:
            aspects.append(_ASPECT_DISTRIBUTION)
            reasons.append(f"aspect:distribution:{sorted(distribution)[0]}")
        return list(dict.fromkeys(aspects)), reasons

    # -- relations ---------------------------------------------------------

    def _required_relations(self, domain_ids: list[str], refs: list[str]) -> list[str]:
        """Minimal relation union for the selected topics.

        Kept as a union of declared paths rather than a fresh graph search: the
        router must not be able to invent an edge the relation registry never
        declared (notably shop-shelf to platform-category).
        """
        relations: list[str] = []
        non_sql = topics.non_sql_refs()
        for topic_id in domain_ids:
            card = topics.TOPICS[topic_id]
            owned = set(card.all_refs())
            if not owned & set(refs) - non_sql:
                continue
            relations.extend(card.relation_ids)
        return list(dict.fromkeys(relations))

    # -- entry point -------------------------------------------------------

    def route(self, question: str, request=None) -> RoutingResult:
        reasons: list[str] = []

        if not self.gate_enabled:
            # §6.5: gate off is its own state, not "unknown". Context falls back
            # to the legacy broad slice and no capability decision changes.
            return self._finish(
                mode="unknown", domain_ids=[], aspect_ids=[], resolved=[],
                unresolved=[], relations=[],
                reasons=["topic_gate_disabled"], overflow_reason=None,
                question=question,
            )

        resolved, unresolved_surfaces = self._refs_from_request(request)
        if resolved:
            reasons.append(f"resolved_refs:{len(resolved)}")

        fallback, ambiguous = self._alias_fallback(question, set(resolved))
        if fallback:
            reasons.append(f"alias_fallback:{len(fallback)}")
        if ambiguous:
            reasons.append(f"alias_ambiguous:{len(ambiguous)}")

        all_refs = list(dict.fromkeys(resolved + fallback))
        aspect_ids, aspect_reasons = self._aspects(request)
        reasons.extend(aspect_reasons)

        owners = [topics.OWNER_BY_REF[ref] for ref in all_refs if ref in topics.OWNER_BY_REF]
        domain_ids = list(dict.fromkeys(o for o in owners if topics.TOPICS[o].kind == "domain"))
        # A5 owns context.* refs, so a context ref selects the aspect that
        # guarantees those refs never compile into SQL.
        if any(topics.OWNER_BY_REF.get(ref) == _ASPECT_EXTERNAL for ref in all_refs):
            aspect_ids.append(_ASPECT_EXTERNAL)
            reasons.append("aspect:external_context")
        aspect_ids = list(dict.fromkeys(aspect_ids))

        relations = self._required_relations(domain_ids, all_refs)

        # Scope refs do not count as the question binding anything: the parser
        # injects a country filter (and often a date) on every request, so
        # counting them would make ``unknown`` unreachable and route a question
        # about data we do not hold -- stock, margin -- as a valid CORE slice.
        content_refs = [ref for ref in all_refs if ref not in _SCOPE_REFS]

        if not content_refs:
            mode: RouteMode = "unknown"
            reasons.append("scope_refs_only" if all_refs else "no_ref_bound")
        elif not domain_ids:
            mode = "core_only"
            reasons.append("core_refs_only")
        elif len(domain_ids) == 1:
            mode = "topic_scoped"
        else:
            mode = "multi_topic"
            reasons.append(f"domains:{len(domain_ids)}")

        return self._finish(
            mode=mode, domain_ids=domain_ids, aspect_ids=aspect_ids,
            resolved=all_refs, unresolved=unresolved_surfaces + ambiguous,
            relations=relations, reasons=reasons, overflow_reason=None,
            question=question,
        )

    def mark_overflow(self, result: RoutingResult, reason: str) -> RoutingResult:
        """Escalate a route the packer/decomposer could not satisfy (§6.5).

        Reachable only from downstream: overflow means hard context did not
        pack, there was no atomic path, and no gated decomposition signature fit
        inside 2--4 subplans. All topic metadata is preserved -- the decomposer
        or a fail-closed answer handles it, and the router never truncates.
        """
        return result.model_copy(update={
            "mode": "overflow",
            "overflow_reason": reason,
            "routing_reasons": result.routing_reasons + (f"overflow:{reason}",),
        })

    def _finish(self, *, mode, domain_ids, aspect_ids, resolved, unresolved,
                relations, reasons, overflow_reason, question) -> RoutingResult:
        payload = {
            "mode": mode,
            "domains": sorted(domain_ids),
            "aspects": sorted(aspect_ids),
            "refs": sorted(resolved),
            "relations": sorted(relations),
            "router": ROUTER_VERSION,
            "topics": topics.REGISTRY_HASH,
            "invariants": INVARIANT_HASH,
            "aliases": self.alias_index.index_hash,
        }
        routing_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:16]
        return RoutingResult(
            mode=mode,
            domain_topic_ids=tuple(domain_ids),
            aspect_topic_ids=tuple(aspect_ids),
            resolved_refs=tuple(resolved),
            unresolved_refs=tuple(unresolved),
            required_relation_ids=tuple(relations),
            routing_reasons=tuple(reasons),
            overflow_reason=overflow_reason,
            routing_hash=routing_hash,
        )


_DEFAULT: TopicRouter | None = None


def default_router() -> TopicRouter:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = TopicRouter()
    return _DEFAULT
