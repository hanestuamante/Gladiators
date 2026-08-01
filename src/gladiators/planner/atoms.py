"""Request atoms — ultimate solution §3.4.

One representation, shared by the decomposer and by A22, whose only job is to
make "did we drop part of the question?" a set comparison instead of a judgement
call.

Every silent-wrong-answer found while probing this system was a dropped
constraint: a second country, a date window, a grouping dimension, a ranking
direction. In each case the plan was internally coherent and the answer was
confidently wrong. Atoms exist so that coverage is checked rather than assumed --
if an atom is not covered by a plan or by a composition, that is a defect the
validator can see, not a nuance a reviewer has to notice.

``atom_id`` is a content hash of kind, ref and canonical value. Never a uuid or
a timestamp: two runs of the same question must produce the same atom ids, or
coverage cannot be compared across a repair or a replay.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

AtomKind = Literal[
    "measure", "dimension", "filter", "country", "date",
    "entity", "aggregation", "operator", "output_shape_kind", "compound_part",
]

# Only scope atoms may legitimately appear in several subrequests: asking each
# half of a comparison about the same dates is not a duplicated requirement.
SHAREABLE_KINDS: frozenset[str] = frozenset({"country", "date"})


class RequestAtom(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    atom_id: str
    kind: AtomKind
    semantic_ref: str | None = None
    value: Any = None
    shareable: bool = False


def _canonical(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return json.dumps(sorted(str(v) for v in value), ensure_ascii=False)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def make_atom(kind: AtomKind, *, semantic_ref: str | None = None,
              value: Any = None, shareable: bool | None = None) -> RequestAtom:
    payload = f"{kind}|{semantic_ref or ''}|{_canonical(value)}"
    return RequestAtom(
        atom_id=f"{kind[:3]}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:10]}",
        kind=kind, semantic_ref=semantic_ref, value=value,
        shareable=SHAREABLE_KINDS.__contains__(kind) if shareable is None else shareable,
    )


def atomize_request(digest, request) -> tuple[RequestAtom, ...]:
    """Decompose a request into the units a plan must account for.

    Deliberately literal: this must not normalise away a constraint in the name
    of tidiness, because a constraint tidied away here is one nothing downstream
    can notice is missing.
    """
    atoms: list[RequestAtom] = []

    for binding in getattr(request, "requested_measures", ()) or ():
        if getattr(binding, "ref", None):
            atoms.append(make_atom("measure", semantic_ref=binding.ref))
    for binding in getattr(request, "requested_dimensions", ()) or ():
        if getattr(binding, "ref", None):
            atoms.append(make_atom("dimension", semantic_ref=binding.ref))
    for ref in getattr(request, "grouping", ()) or ():
        atoms.append(make_atom("dimension", semantic_ref=str(ref)))

    for predicate in getattr(request, "filters", ()) or ():
        ref = getattr(predicate, "field_ref", None)
        if not ref:
            continue
        value = getattr(predicate, "value_binding", None)
        if ref == "dim.country":
            # One atom per country: a two-market question that produced a single
            # composite atom would be "covered" by a plan that answered one of
            # them, which is exactly the scope-drop bug this guards against.
            for code in (value if isinstance(value, (list, tuple, set)) else [value]):
                if code is not None:
                    atoms.append(make_atom("country", semantic_ref=ref, value=str(code)))
            continue
        atoms.append(make_atom("filter", semantic_ref=ref, value=value))

    time_scope = getattr(request, "time_scope", None)
    for date in tuple(getattr(time_scope, "dates", ()) or ()) if time_scope else ():
        atoms.append(make_atom("date", semantic_ref="dim.date", value=str(date)))

    for entity in getattr(request, "resolved_entities", ()) or ():
        key = getattr(entity, "resolved_key", None) or getattr(entity, "surface_text", None)
        if key:
            atoms.append(make_atom(
                "entity", semantic_ref=f"entity.{getattr(entity, 'entity_type', 'unknown')}",
                value=str(key),
            ))

    for operator in getattr(request, "analytical_operators", ()) or ():
        atoms.append(make_atom("operator", value=str(operator)))

    ranking = getattr(request, "ranking", None)
    if ranking is not None:
        # Direction is part of the requirement, not a detail: asking for the
        # lowest price and answering with the highest was a ~3000x error.
        atoms.append(make_atom("aggregation", semantic_ref=getattr(ranking, "order_by", None),
                               value=f"rank:{getattr(ranking, 'direction', 'desc')}"))

    shape = getattr(request, "requested_output_shape", None)
    if shape:
        atoms.append(make_atom("output_shape_kind", value=str(shape)))

    for sub_id in getattr(digest, "sub_request_ids", ()) or ():
        atoms.append(make_atom("compound_part", value=str(sub_id)))

    return tuple(dict.fromkeys(atoms))


def non_shareable(atoms: tuple[RequestAtom, ...]) -> frozenset[str]:
    return frozenset(atom.atom_id for atom in atoms if not atom.shareable)


def coverage_gap(
    atoms: tuple[RequestAtom, ...], covered_ids: frozenset[str]
) -> tuple[frozenset[str], frozenset[str]]:
    """``(uncovered, unknown)`` -- what was dropped and what was invented."""
    required = non_shareable(atoms)
    known = {atom.atom_id for atom in atoms}
    return frozenset(required - covered_ids), frozenset(covered_ids - known)
