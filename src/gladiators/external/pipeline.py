"""Phase 6 external context pipeline: plan -> fetch/replay -> extract -> admit.

The pipeline never produces internal facts or cross-tier arithmetic. Every live
record is clamped to ``context_only`` by deterministic admission.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Callable

from gladiators.contracts import Evidence

from .admission import admit_live_record
from .search_executor import SearchExecutor
from .search_planner import LiveSearchPlanner
from .web_extract import ExtractionError, WebExtractor


@dataclass(frozen=True)
class ExternalPipelineOutcome:
    evidence: tuple[Evidence, ...]
    plan_id: str | None
    failed_queries: tuple[str, ...]
    excluded_count: int
    quarantined_count: int
    cache_hits: int
    provider_calls: int
    ladder_reason: str | None


class ExternalContextPipeline:
    def __init__(
        self, planner: LiveSearchPlanner, executor: SearchExecutor, extractor: WebExtractor,
        *, mode: str = "cache_only", license: str = "project-demo-approved-context",
    ):
        if mode not in {"cache_only", "record", "live"}:
            raise ValueError("External mode không hợp lệ.")
        self.planner, self.executor, self.extractor = planner, executor, extractor
        self.mode, self.license = mode, license

    def run(
        self, question: str, *, purpose: str, market: str,
        evidence_id: Callable[[], str], dataset_version: str,
    ) -> ExternalPipelineOutcome:
        if reason := self.executor.preflight_failure(self.mode):
            return ExternalPipelineOutcome((), None, (), 0, 0, 0, 0, reason)
        try:
            plan = self.planner.plan(question, purpose=purpose, market=market, mode=self.mode)
        except Exception as exc:
            return ExternalPipelineOutcome(
                (), None, (), 0, 0, 0, 0,
                f"A15: live-search planning failed ({type(exc).__name__})",
            )
        execution = self.executor.execute(plan)
        evidence: list[Evidence] = []
        excluded = 0
        for response in execution.responses:
            for item in response.items:
                try:
                    record = self.extractor.extract(response, item)
                except ExtractionError:
                    excluded += 1
                    continue
                observed_at = (
                    datetime.combine(item.published_at, time.min, tzinfo=timezone.utc)
                    if item.published_at else response.retrieved_at
                )
                caveats = () if item.published_at else ("published_at_unknown_observed_at_uses_retrieved_at",)
                admitted = admit_live_record(
                    record, response, mapping_status="needs_review", observed_at=observed_at,
                    license=self.license, caveats=caveats,
                )
                if admitted.provenance is None:
                    excluded += 1
                    continue
                normalized_fields = record.normalized_fields()
                value = json.dumps(normalized_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                metric = {
                    "campaign_window": "context.campaign_window",
                    "theme_day": "context.theme_day",
                }.get(record.claim_type, "context.market_event")
                evidence.append(Evidence(
                    evidence_id=evidence_id(), source_tier="external", metric=metric,
                    value=value, unit=None, source_locator=admitted.provenance.source_locator,
                    source_path=response.cache_path, dataset_version=dataset_version,
                    attrs={
                        "claim_type": record.claim_type, "fields": normalized_fields,
                        "provider": response.provider, "search_query": record.search_query,
                        "result_rank": record.result_rank,
                        "observed_at": observed_at.isoformat(),
                        "retrieved_at": response.retrieved_at.isoformat(),
                        "url": record.result_url, "mapping_status": "needs_review",
                        "admission": admitted.decision.outcome,
                    },
                    provenance=admitted.provenance,
                ))
        reason = execution.ladder_reason
        if not evidence and reason is None:
            reason = "A15: no external record passed extraction/admission"
        return ExternalPipelineOutcome(
            tuple(evidence), plan.plan_id, execution.failed_queries, excluded,
            execution.quarantined_count, execution.cache_hits, execution.provider_calls, reason,
        )
