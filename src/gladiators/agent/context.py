"""Typed alignment-context carrier.

ContextBundle always owns guarded copies.  It never mutates Evidence instances,
which remain the verifier's source of truth.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from gladiators.contracts import Evidence, StructuredRequest
from gladiators.external.injection_guard import sanitize_internal_text

from .parser import normalize_date_range

Stage = Literal["parse", "plan", "critic", "alternate", "adjudicate", "generate", "extract"]

BUDGETS: dict[tuple[Stage, str], int] = {
    ("plan", "P8"): 6000,
    ("critic", "P9"): 4000,
    ("alternate", "P10"): 6000,
    ("adjudicate", "P11"): 3000,
    ("generate", "P2"): 4000,
    ("extract", "P6"): 2000,
}


class RequestDigest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    normalized_question: str
    language: Literal["vi", "id", "unknown"]
    intent: str
    countries: tuple[str, ...] = ()
    entity_refs: tuple[str, ...] = ()
    requested_measures: tuple[str, ...] = ()
    requested_dimensions: tuple[str, ...] = ()
    requested_output_shape: Literal["scalar", "table", "ranking", "comparison"]
    qualifiers: tuple[str, ...] = ()
    sub_request_ids: tuple[str, ...] = ()
    # V2 §4.4: the digest must carry the date range that was asked for, so a
    # temporal answer can be checked against it instead of being trusted.
    date_range: tuple[str, ...] = ()
    # W5.1: phép tổng hợp câu hỏi nêu tường minh, khoá xuyên bốn lớp. Không có
    # nó ở digest thì alignment không có gì để đối chiếu và một câu hỏi trung
    # bình được trả bằng trung vị vẫn "khớp" mọi thứ khác.
    requested_aggregation: str | None = None


class ContextBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    stage: Stage
    purpose: str
    request_digest: RequestDigest
    plan_refs: tuple[str, ...] = ()
    plan_hash: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    guard_hits: tuple[str, ...] = ()
    prompt_version: str
    dataset_version: str
    budget_tokens: int
    dropped: tuple[str, ...] = ()
    context_hash: str = ""

    def with_hash(self) -> "ContextBundle":
        canonical = json.dumps(
            {
                "stage": self.stage,
                "purpose": self.purpose,
                "request_digest": self.request_digest.model_dump(mode="json"),
                "plan_refs": list(self.plan_refs),
                "plan_hash": self.plan_hash,
                "payload": self.payload,
                "prompt_version": self.prompt_version,
                "dataset_version": self.dataset_version,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
        return self.model_copy(update={"context_hash": digest})

    def trace_summary(self) -> dict[str, Any]:
        return {
            "context_hash": self.context_hash,
            "plan_hash": self.plan_hash,
            "budget_tokens": self.budget_tokens,
            "guard_hits": list(self.guard_hits),
            "dropped": list(self.dropped),
        }


def guarded_evidence_payload(
    evidence: list[Evidence],
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """Return guarded copies of evidence.value and string attrs."""
    payloads: list[dict[str, Any]] = []
    hits: list[str] = []
    for item in evidence:
        data = item.model_dump(mode="json")
        if isinstance(data.get("value"), str):
            guarded = sanitize_internal_text(data["value"])
            data["value"] = guarded.text
            hits.extend(f"{item.evidence_id}:value:{hit}" for hit in guarded.hits)
        attrs = data.get("attrs")
        if isinstance(attrs, dict):
            for key, raw in tuple(attrs.items()):
                if not isinstance(raw, str):
                    continue
                guarded = sanitize_internal_text(raw)
                attrs[key] = guarded.text
                hits.extend(f"{item.evidence_id}:attrs.{key}:{hit}" for hit in guarded.hits)
        payloads.append(data)
    return payloads, tuple(hits)


def request_digest(request: StructuredRequest) -> RequestDigest:
    analytical = request.analytical or {}

    def refs(key: str) -> tuple[str, ...]:
        result = []
        for item in analytical.get(key, ()):
            if isinstance(item, dict) and item.get("ref") and not item.get("unresolved"):
                result.append(str(item["ref"]))
        return tuple(dict.fromkeys(result))

    entities = tuple(
        f"{item.get('kind')}:{item.get('value')}"
        for item in request.entities
        if isinstance(item, dict) and item.get("kind") and item.get("value")
    )
    raw = str(request.slots.get("raw_text", ""))
    return RequestDigest(
        normalized_question=str(analytical.get("normalized_question") or raw),
        language=request.language,
        intent=request.intent,
        countries=request.countries or ((request.country,) if request.country else ()),
        entity_refs=entities,
        requested_measures=refs("requested_measures"),
        requested_dimensions=refs("requested_dimensions"),
        requested_output_shape=str(analytical.get("requested_output_shape") or "table"),
        qualifiers=tuple(str(x) for x in request.slots.get("qualifiers", ())),
        requested_aggregation=(
            str(analytical["requested_aggregation"])
            if analytical.get("requested_aggregation") else None
        ),
        date_range=tuple(normalize_date_range(request.date_range)),
        sub_request_ids=tuple(
            str(item.get("sub_id")) for item in request.slots.get("sub_requests", ())
            if isinstance(item, dict) and item.get("sub_id")
        ),
    )
