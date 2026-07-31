"""Deterministic request↔plan↔evidence↔answer alignment (A22)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gladiators.contracts import Evidence, ResponseClaim
from gladiators.domain.catalog import CATALOG
from gladiators.planner.query_ir import LogicalQueryPlan
from gladiators.planner.macros import CertifiedShape

from .context import RequestDigest

IssueCode = Literal[
    "measure_dropped",
    "measure_substituted",
    "shape_mismatch",
    "qualifier_ignored",
    "entity_unbound",
    "subrequest_dropped",
    "scope_dropped",
    "temporal_window_narrowed",
]


@dataclass(frozen=True)
class AlignmentIssue:
    code: IssueCode
    detail: str
    request_side: tuple[str, ...] = ()
    plan_side: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlignmentVerdict:
    aligned: bool
    issues: tuple[AlignmentIssue, ...]

    @property
    def rule_id(self) -> str | None:
        if self.aligned:
            return None
        return {
            "measure_dropped": "A22-ALIGN-MEASURE",
            "measure_substituted": "A22-ALIGN-MEASURE",
            "shape_mismatch": "A22-ALIGN-SHAPE",
            "qualifier_ignored": "A22-ALIGN-QUALIFIER",
            "entity_unbound": "A22-ALIGN-ENTITY",
            "subrequest_dropped": "A22-ALIGN-SUBREQUEST",
            "scope_dropped": "A22-ALIGN-SCOPE",
            "temporal_window_narrowed": "A22-ALIGN-TEMPORAL",
        }[self.issues[0].code]

    def as_dict(self) -> dict:
        return {
            "aligned": self.aligned,
            "rule_id": self.rule_id,
            "issues": [
                {
                    "code": item.code,
                    "detail": item.detail,
                    "request_side": list(item.request_side),
                    "plan_side": list(item.plan_side),
                }
                for item in self.issues
            ],
        }


def plan_refs(plan: LogicalQueryPlan) -> tuple[str, ...]:
    refs = {ref for node in plan.nodes for ref in node.refs + node.group_by}
    refs.update(predicate.ref for node in plan.nodes for predicate in node.predicates)
    refs.update(node.rank_by for node in plan.nodes if node.rank_by)
    refs.update(
        field.semantic_ref for field in plan.requested_output_shape if field.semantic_ref
    )
    return tuple(sorted(ref for ref in refs if ref))


def _shape_issues(digest: RequestDigest, plan: LogicalQueryPlan) -> list[AlignmentIssue]:
    output = next(node for node in plan.nodes if node.node_id == plan.output_node)
    has_rank = any(node.op == "Rank" for node in plan.nodes)
    issues: list[AlignmentIssue] = []
    if digest.requested_output_shape == "scalar" and (
        output.expected_cardinality != "1" or has_rank and (output.limit or 1) > 1
    ):
        issues.append(AlignmentIssue(
            "shape_mismatch",
            "Request cần scalar nhưng plan có thể trả nhiều dòng.",
            (digest.requested_output_shape,),
            (output.expected_cardinality,),
        ))
    elif digest.requested_output_shape == "ranking" and not has_rank:
        issues.append(AlignmentIssue(
            "shape_mismatch", "Request cần ranking nhưng plan không có Rank.",
            ("ranking",), (output.op,),
        ))
    elif digest.requested_output_shape == "comparison":
        comparison_shape = (
            output.expected_cardinality == "2"
            or output.expected_cardinality.startswith("<=")
            and int(output.expected_cardinality[2:]) >= 2
            or len(output.group_by) >= 1
        )
        if not comparison_shape:
            issues.append(AlignmentIssue(
                "shape_mismatch", "Request cần comparison nhưng plan không tạo nhiều nhóm.",
                ("comparison",), (output.expected_cardinality,),
            ))
    return issues


def check_plan_alignment(
    digest: RequestDigest,
    refs_or_plan: tuple[str, ...] | LogicalQueryPlan,
    plan_output_shape: str | None = None,
    *,
    supporting_refs: frozenset[str] = frozenset(),
) -> AlignmentVerdict:
    plan = refs_or_plan if isinstance(refs_or_plan, LogicalQueryPlan) else None
    refs = set(plan_refs(plan) if plan else refs_or_plan)
    requested = set(digest.requested_measures)
    missing = tuple(sorted(requested - refs))
    issues: list[AlignmentIssue] = []
    if missing:
        issues.append(AlignmentIssue(
            "measure_dropped",
            "Plan không giữ measure đã được liên kết từ câu hỏi: " + ", ".join(missing),
            missing,
            tuple(sorted(refs)),
        ))

    # Only inspect output semantic refs for substitution. Intermediate refs may
    # legitimately support a derived metric (for example price × sold).
    if plan is not None:
        output_refs = {
            field.semantic_ref for field in plan.requested_output_shape if field.semantic_ref
        }
        unexpected = tuple(sorted(
            ref for ref in output_refs - requested - set(supporting_refs)
            if ref in CATALOG and CATALOG[ref].kind in {"measure", "derived_metric"}
        ))
        if requested and unexpected:
            issues.append(AlignmentIssue(
                "measure_substituted",
                "Plan output thay bằng measure không được hỏi: " + ", ".join(unexpected),
                tuple(sorted(requested)),
                unexpected,
            ))
        issues.extend(_shape_issues(digest, plan))
        if digest.entity_refs:
            binds_entity = any(
                node.op == "ResolveValue"
                or any(
                    str(predicate.value) in entity_ref
                    for predicate in node.predicates for entity_ref in digest.entity_refs
                )
                for node in plan.nodes
            )
            if not binds_entity:
                issues.append(AlignmentIssue(
                    "entity_unbound",
                    "Entity/ID trong câu hỏi không được bind vào plan.",
                    digest.entity_refs,
                    (),
                ))
    elif plan_output_shape and digest.requested_output_shape != "table":
        if digest.requested_output_shape != plan_output_shape:
            issues.append(AlignmentIssue(
                "shape_mismatch",
                f"Request shape={digest.requested_output_shape}, plan shape={plan_output_shape}.",
                (digest.requested_output_shape,),
                (plan_output_shape,),
            ))
    return AlignmentVerdict(not issues, tuple(issues))


def _evidence_ref(item: Evidence) -> str | None:
    if item.source_path and item.source_path in CATALOG:
        return item.source_path
    aliases = {
        "listing_count": "derived.product_count",
        "estimated_recent_revenue": "derived.estimated_recent_revenue",
        "highest_revenue_proxy_date": "dim.date",
        "price": "measure.price",
        "monthly_sold": "measure.monthly_sold",
    }
    candidate = aliases.get(item.metric)
    if candidate:
        return candidate
    for prefix in ("measure.", "derived."):
        if prefix + item.metric in CATALOG:
            return prefix + item.metric
    return None


def check_evidence_alignment(
    digest: RequestDigest, evidence: list[Evidence],
) -> AlignmentVerdict:
    if any(item.metric == "result_count" and item.attrs.get("empty_result") for item in evidence):
        return AlignmentVerdict(True, ())
    refs = {_evidence_ref(item) for item in evidence}
    missing = tuple(sorted(set(digest.requested_measures) - refs))
    issues: list[AlignmentIssue] = []
    if missing:
        issues.append(AlignmentIssue(
            "measure_dropped",
            "Evidence không phủ measure đã hỏi: " + ", ".join(missing),
            missing,
            tuple(sorted(ref for ref in refs if ref)),
        ))
    if digest.requested_output_shape == "comparison":
        groups = {
            str(item.attrs.get("group")) for item in evidence if item.attrs.get("group") is not None
        }
        if len(groups) < 2:
            issues.append(AlignmentIssue(
                "shape_mismatch", "Evidence comparison không có đủ hai nhóm.",
                ("comparison",), tuple(sorted(groups)),
            ))

    issues.extend(_scope_issues(digest, evidence))
    return AlignmentVerdict(not issues, tuple(issues))


def _scope_issues(
    digest: RequestDigest, evidence: list[Evidence],
) -> list[AlignmentIssue]:
    """Country/date coverage checks (V2 §4.4).

    These compare attribute *sets* and never consult the catalog, so unlike the
    measure/shape checks they are valid on any producer — certified macro or
    analytical plan.  ``check_evidence_scope_alignment`` exposes them for the
    macro path, where a ref-level measure check would misfire: a macro may
    legitimately answer ``measure.monthly_sold`` with ``derived.monthly_sold_delta``.
    """
    issues: list[AlignmentIssue] = []

    # Answering one market for a two-market question is an alignment failure even
    # when the number returned is correct for the market it did cover.  Only
    # judged when the evidence carries country attributes at all -- otherwise the
    # producer has no way to express scope and there is nothing to compare.
    covered_countries = {
        str(item.attrs["country"]) for item in evidence if item.attrs.get("country")
    }
    if digest.countries and covered_countries:
        dropped = tuple(sorted(set(digest.countries) - covered_countries))
        if dropped:
            issues.append(AlignmentIssue(
                "scope_dropped",
                "Evidence không phủ hết country đã hỏi: " + ", ".join(dropped),
                tuple(digest.countries),
                tuple(sorted(covered_countries)),
            ))

    # TemporalCompare must use the previous/current dates that were asked for,
    # never the nearest available pair.  Answering the trailing leg of a
    # multi-day window can invert the sign of the change, so a narrowed window is
    # an alignment failure even though the leg itself is computed correctly.
    if len(digest.date_window) == 2:
        spans = [
            (str(item.attrs["previous_date"]), str(item.attrs["date"]))
            for item in evidence
            if item.attrs.get("previous_date") and item.attrs.get("date")
        ]
        if spans:
            start, end = min(s for s, _ in spans), max(e for _, e in spans)
            if (start, end) != (digest.date_window[0], digest.date_window[1]):
                issues.append(AlignmentIssue(
                    "temporal_window_narrowed",
                    "Evidence phủ cửa sổ {}→{} thay vì {}→{} đã hỏi.".format(
                        start, end, digest.date_window[0], digest.date_window[1],
                    ),
                    tuple(digest.date_window),
                    (start, end),
                ))
    return issues


def check_evidence_scope_alignment(
    digest: RequestDigest, evidence: list[Evidence],
) -> AlignmentVerdict:
    """Scope-only alignment for producers without a semantic plan (macros)."""
    if any(item.metric == "result_count" and item.attrs.get("empty_result") for item in evidence):
        return AlignmentVerdict(True, ())
    issues = _scope_issues(digest, evidence)
    return AlignmentVerdict(not issues, tuple(issues))


def check_answer_alignment(
    digest: RequestDigest,
    evidence: list[Evidence],
    claims: tuple[ResponseClaim, ...],
    answer: str,
) -> AlignmentVerdict:
    if any(item.metric == "result_count" and item.attrs.get("empty_result") for item in evidence):
        return AlignmentVerdict(True, ())
    refs_by_id = {item.evidence_id: _evidence_ref(item) for item in evidence}
    claimed = {refs_by_id.get(claim.evidence_id) for claim in claims}
    missing = tuple(sorted(set(digest.requested_measures) - claimed))
    issues = ()
    if missing and "Giới hạn" not in answer and "Chưa trả lời được" not in answer:
        issues = (AlignmentIssue(
            "subrequest_dropped",
            "Answer không bind hoặc nêu giới hạn cho measure: " + ", ".join(missing),
            missing,
            tuple(sorted(ref for ref in claimed if ref)),
        ),)
    return AlignmentVerdict(not issues, issues)


def check_macro_shape(
    digest: RequestDigest, shape: CertifiedShape,
) -> AlignmentVerdict:
    forbidden = tuple(sorted(set(digest.qualifiers) & set(shape.forbidden_qualifiers)))
    issues: list[AlignmentIssue] = []
    if forbidden:
        issues.append(AlignmentIssue(
            "qualifier_ignored",
            "Điều kiện ngoài phạm vi macro được chứng nhận: " + ", ".join(forbidden),
            forbidden,
            tuple(sorted(shape.forbidden_qualifiers)),
        ))
    return AlignmentVerdict(not issues, tuple(issues))
