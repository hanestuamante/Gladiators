"""Deterministic A15/A17/A18/A21 admission with live context-only clamp."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from .contracts import AdmissionDecision, MappingState, SourceLocator
from .injection_guard import fields_match_utf8
from .search_contracts import ExtractedWebRecord, LiveSearchProvenance, SearchResponse


@dataclass(frozen=True)
class AdmissionResult:
    decision: AdmissionDecision
    provenance: LiveSearchProvenance | None


def _record_hash(record: ExtractedWebRecord) -> str:
    raw = json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def admit_live_record(
    record: ExtractedWebRecord, response: SearchResponse, *, mapping_status: MappingState,
    observed_at: datetime, license: str, caveats: tuple[str, ...] = (),
) -> AdmissionResult:
    digest = _record_hash(record)
    matching = next(
        (item for item in response.items if item.rank == record.result_rank and item.url == record.result_url),
        None,
    )
    if record.raw_content_hash != response.content_hash or matching is None or not fields_match_utf8(
        matching.snippet, record.fields,
    ):
        return AdmissionResult(AdmissionDecision(
            record_hash=digest, outcome="excluded", rule_id="A17",
            caveats=("source_span_or_hash_mismatch",),
        ), None)
    if mapping_status in {"unmapped", "rejected", "superseded"}:
        return AdmissionResult(AdmissionDecision(
            record_hash=digest, outcome="excluded", rule_id="A15",
            caveats=("external_entity_unmapped",),
        ), None)
    rule = "A18" if mapping_status in {"candidate", "needs_review"} else "A14-LIVE"
    all_caveats = tuple(dict.fromkeys((*caveats, "live_web_result_context_only")))
    provenance = LiveSearchProvenance(
        source_id="live_web_search", source_tier="external",
        source_locator=SourceLocator(kind="url", value=record.result_url),
        content_hash=response.content_hash, observed_at=observed_at,
        retrieved_at=response.retrieved_at, unit=None, currency=None,
        mapping_status=mapping_status, admission="context_only", license=license,
        caveats=all_caveats, provider=response.provider,
        search_query=record.search_query, result_rank=record.result_rank,
        source_spans=record.all_spans(),
    )
    return AdmissionResult(AdmissionDecision(
        record_hash=digest, outcome="context_only", rule_id=rule, caveats=all_caveats,
    ), provenance)
