"""Rule-based QueryRiskScore và escalation ladder — V2 mục 7.9."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gladiators.domain.relations import RELATIONS

from .query_ir import LogicalQueryPlan
from .validator import validate_plan

EscalationMode = Literal["single", "critic", "nversion", "blocked"]


@dataclass(frozen=True)
class RiskFactor:
    name: str
    score: int
    reason: str


@dataclass(frozen=True)
class QueryRiskResult:
    score: int
    factors: tuple[RiskFactor, ...]
    requested_mode: EscalationMode
    effective_mode: EscalationMode
    allowed: bool
    reason: str


@dataclass(frozen=True)
class EscalationConfig:
    tau1: int = 3
    tau2: int = 6
    enable_critic: bool = False
    enable_nversion: bool = False


def score_plan(
    plan: LogicalQueryPlan,
    *,
    complexity_level: str = "L2",
    schema_linking_ambiguous: bool = False,
    entity_near_margin: bool = False,
    low_coverage_or_anomaly: bool = False,
    newly_approved_metrics: frozenset[str] = frozenset(),
    config: EscalationConfig = EscalationConfig(),
) -> QueryRiskResult:
    verdict = validate_plan(plan)
    if not verdict.valid:
        return QueryRiskResult(
            score=10, factors=(RiskFactor("invalid_plan", 2, "Plan chưa qua deterministic validator."),),
            requested_mode="blocked", effective_mode="blocked", allowed=False,
            reason="Plan invalid phải repair hoặc A19-PLAN; không được escalation để bypass validator.",
        )

    factors: list[RiskFactor] = []
    joins = [node for node in plan.nodes if node.op == "Join"]
    join_score = 0 if not joins else 1 if len(joins) == 1 else 2
    factors.append(RiskFactor("relation_count", join_score, f"{len(joins)} join trong plan."))

    has_nm_or_transition = any(
        node.op == "Join" and node.relation in RELATIONS and RELATIONS[node.relation].cardinality == "N:M"
        for node in plan.nodes
    ) or sum(node.input_grain != node.output_grain for node in plan.nodes) >= 2
    factors.append(RiskFactor(
        "fanout_or_grain", 2 if has_nm_or_transition else 0,
        "Có N:M hoặc đổi grain nhiều lần." if has_nm_or_transition else "Không có N:M/đổi grain phức tạp.",
    ))

    temporal = any(node.op == "TemporalCompare" for node in plan.nodes)
    factors.append(RiskFactor("temporal", 1 if temporal else 0, "Có TemporalCompare." if temporal else "Không temporal window."))

    refs = {ref for node in plan.nodes for ref in node.refs}
    new_metric = bool(refs & newly_approved_metrics)
    factors.append(RiskFactor("new_metric", 2 if new_metric else 0, "Có metric mới chưa đủ verified runs." if new_metric else "Metric đã ổn định."))

    cross_country = any(node.op == "Union" for node in plan.nodes)
    factors.append(RiskFactor("cross_country", 1 if cross_country else 0, "Union hai scope/country." if cross_country else "Một scope country."))
    factors.append(RiskFactor("schema_linking", 2 if schema_linking_ambiguous else 0,
                              "Schema-linking margin thấp." if schema_linking_ambiguous else "Schema linking rõ."))
    factors.append(RiskFactor("entity_margin", 1 if entity_near_margin else 0,
                              "Entity resolve sát ngưỡng." if entity_near_margin else "Entity không sát ngưỡng."))
    complex_shape = verdict.depth > 3 or plan.subplan_count >= 2
    factors.append(RiskFactor("plan_shape", 2 if complex_shape else 0,
                              f"depth={verdict.depth}, subplans={plan.subplan_count}."))
    factors.append(RiskFactor("coverage_anomaly", 1 if low_coverage_or_anomaly else 0,
                              "Input có coverage thấp/anomaly." if low_coverage_or_anomaly else "Không có cờ coverage/anomaly."))

    score = sum(factor.score for factor in factors)
    requested: EscalationMode
    if score >= config.tau2 or complexity_level == "L4":
        requested = "nversion"
    elif score >= config.tau1 or complexity_level == "L3":
        requested = "critic"
    else:
        requested = "single"

    if requested == "nversion" and not config.enable_nversion:
        return QueryRiskResult(score, tuple(factors), requested, "blocked", False,
                               "N-version chưa qua acceptance bắt buộc hoặc đang bị kill-switch tắt.")
    if requested == "critic" and not config.enable_critic:
        return QueryRiskResult(score, tuple(factors), requested, "blocked", False,
                               "Plan critic chưa qua acceptance bắt buộc hoặc đang bị kill-switch tắt.")
    return QueryRiskResult(score, tuple(factors), requested, requested, True, "Escalation policy cho phép thực thi.")
