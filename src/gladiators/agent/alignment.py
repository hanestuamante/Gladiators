"""Deterministic request↔plan↔evidence↔answer alignment (A22)."""
from __future__ import annotations

import re
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
    # V2 §4.4 issue vocabulary. Names and outward codes are a contract; do not
    # rename without updating the stable-code table in the spec.
    "country_dropped",
    "date_range_narrowed",
    "aggregation_mismatch",
    "grouping_dropped",
    "filter_dropped",
    # Theme B: the question itself carries constraints. A "vì sao" question is
    # not answered by a count, and "giảm mạnh" is a claim about the data that
    # has to hold before anything downstream explains it.
    "causal_question_unanswered",
    "premise_contradicted",
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
            "country_dropped": "A22-ALIGN-COUNTRY",
            "date_range_narrowed": "A22-ALIGN-DATE",
            "aggregation_mismatch": "A22-ALIGN-AGGREGATION",
            "grouping_dropped": "A22-ALIGN-GROUPING",
            "filter_dropped": "A22-ALIGN-FILTER",
            "causal_question_unanswered": "A22-ALIGN-SHAPE",
            "premise_contradicted": "A22-ALIGN-PREMISE",
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
    # W11.2: một tỷ lệ đã khai mẫu số BẮT BUỘC mang tử số và mẫu số trong
    # output (hợp đồng ba ref, §12.3.1) — hai ref đó là support của measure
    # được hỏi, không phải một phép thay thế.
    share_supports: set[str] = set()
    for ref in requested:
        if ref.startswith("derived."):
            from gladiators.domain.metrics import METRICS

            spec = METRICS.get(ref.split(".", 1)[1])
            if spec is not None and spec.share is not None:
                share_supports.add(f"derived.{spec.share.numerator_metric}")
                share_supports.add(f"derived.{spec.share.denominator_metric}")
    missing = tuple(sorted(requested - refs))
    issues: list[AlignmentIssue] = []
    if missing:
        issues.append(AlignmentIssue(
            "measure_dropped",
            "Plan không giữ measure đã được liên kết từ câu hỏi: " + ", ".join(missing),
            missing,
            tuple(sorted(refs)),
        ))

    requested_aggregation = getattr(digest, "requested_aggregation", None)
    if plan is not None and requested_aggregation:
        # W5.1: phép tổng hợp là một phần của CÂU HỎI. Plan không mang node
        # Aggregate tương ứng, hoặc mang một phép khác, là đang trả lời một câu
        # hỏi khác — và không lớp nào phía sau phân biệt được hai con số đó.
        performed = {
            node.aggregation for node in plan.nodes
            if node.op == "Aggregate" and node.aggregation
        }
        if performed and requested_aggregation not in performed:
            issues.append(AlignmentIssue(
                "aggregation_mismatch",
                f"Câu hỏi yêu cầu phép tổng hợp {requested_aggregation} nhưng plan "
                "thực hiện: " + ", ".join(sorted(performed)) + ".",
                (requested_aggregation,),
                tuple(sorted(performed)),
            ))

    # Only inspect output semantic refs for substitution. Intermediate refs may
    # legitimately support a derived metric (for example price × sold).
    if plan is not None:
        output_refs = {
            field.semantic_ref for field in plan.requested_output_shape if field.semantic_ref
        }
        unexpected = tuple(sorted(
            ref for ref in output_refs - requested - set(supporting_refs) - share_supports
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

        # V2 §4.4 grouping_dropped: a dimension named in the question must be
        # touched by the plan.  Without this, "bao nhiêu listing của shop
        # official / thương hiệu NESCAFÉ / theo từng shop tại VN" all compile to
        # the bare listing_count template and return the same unfiltered 668,
        # which is a silent wrong answer for three different questions.
        dropped_dimensions = tuple(
            ref for ref in digest.requested_dimensions
            if ref in CATALOG and ref not in refs
        )
        if dropped_dimensions:
            issues.append(AlignmentIssue(
                "grouping_dropped",
                "Plan bỏ chiều đã hỏi: " + ", ".join(dropped_dimensions),
                dropped_dimensions,
                tuple(sorted(refs)),
            ))

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


def _empty_result_is_self_evident(evidence) -> bool:
    """Zero-row được miễn đối chiếu measure CHỈ KHI nó tự chứng minh được (W1.7).

    "Không dòng nào khớp" là một kết quả hợp lệ và nó không mang measure, nên
    check_evidence_alignment sẽ báo measure_dropped cho một câu trả lời đúng.
    Nhưng miễn VÔ ĐIỀU KIỆN thì một số 0 do lọc hỏng cũng được miễn — và hai
    số 0 đó trông giống hệt nhau. Tự chứng minh nghĩa là: số predicate thực thi
    khớp số predicate trong plan, và mọi literal đi lọc đã được xác nhận tồn
    tại trong value index.
    """
    for item in evidence:
        if item.metric != "result_count" or not item.attrs.get("empty_result"):
            continue
        executed = item.attrs.get("executed_predicate_count", 0)
        planned = item.attrs.get("planned_predicate_count", 0)
        if executed != planned:
            return False
        bindings = item.attrs.get("filter_bindings", ()) or ()
        if any(not verified for _ref, verified in bindings):
            return False
        return True
    return False


def check_evidence_alignment(
    digest: RequestDigest, evidence: list[Evidence],
) -> AlignmentVerdict:
    if _empty_result_is_self_evident(evidence):
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


def _country_codes(value: str) -> set[str]:
    """Expand an evidence country attribute into the codes it actually covers.

    Cross-market macros label their scope compositely -- ``"vn+id"`` and
    ``"vn+id_separate_nonmonetary"`` both mean *both* markets.  Comparing those
    strings to a digest of ``("vn",)`` made the country coverage check report a
    dropped scope for a question that was fully answered (found by the DeepSeek
    smoke test; offline the LLM parser never routed here).
    """
    return {part for part in value.replace("_", "+").split("+") if len(part) == 2}


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
        code
        for item in evidence if item.attrs.get("country")
        for code in _country_codes(str(item.attrs["country"]))
    }
    if digest.countries and covered_countries:
        dropped = tuple(sorted(set(digest.countries) - covered_countries))
        if dropped:
            issues.append(AlignmentIssue(
                "country_dropped",
                "Evidence không phủ hết country đã hỏi: " + ", ".join(dropped),
                tuple(digest.countries),
                tuple(sorted(covered_countries)),
            ))

    # TemporalCompare must use the previous/current dates that were asked for,
    # never the nearest available pair.  Answering the trailing leg of a
    # multi-day window can invert the sign of the change, so a narrowed window is
    # an alignment failure even though the leg itself is computed correctly.
    if len(digest.date_range) == 2:
        asked_start, asked_end = digest.date_range

        # Snapshot evidence: the observed date has to sit inside the asked range.
        # Templates default to the latest snapshot, so "bao nhiêu listing tại VN
        # ngày 01/07" was answered with the 03/07 count (668 instead of 581) and
        # labelled observed_date=2026-07-03.
        observed = sorted({
            str(item.attrs["observed_date"])
            for item in evidence if item.attrs.get("observed_date")
        })
        outside = [date for date in observed if not asked_start <= date <= asked_end]
        if outside:
            issues.append(AlignmentIssue(
                "date_range_narrowed",
                "Evidence quan sát ngày {} ngoài phạm vi {}→{} đã hỏi.".format(
                    ", ".join(outside), asked_start, asked_end,
                ),
                tuple(digest.date_range),
                tuple(observed),
            ))
        # B1: containment is not coverage. An end-of-period snapshot always sits
        # inside the window that contains it, so the check above could never see
        # a two-day question answered from one day -- "vì sao listing giảm từ
        # 01/07 đến 03/07" came back with the 03/07 count alone, gate=allow,
        # verified, "Độ tin cậy: High". The transition branch below already
        # compares the span it covers against the span asked for; this is the
        # same comparison, not a third concept.
        elif observed and asked_start != asked_end:
            covered = (min(observed), max(observed))
            if covered != (asked_start, asked_end):
                issues.append(AlignmentIssue(
                    "date_range_narrowed",
                    "Evidence chỉ phủ {}→{} thay vì {}→{} đã hỏi.".format(
                        covered[0], covered[1], asked_start, asked_end,
                    ),
                    tuple(digest.date_range),
                    tuple(observed),
                ))

        # Transition evidence: the span has to match the asked range exactly.
        # Only meaningful for a real range -- a single date cannot bound a delta.
        spans = [
            (str(item.attrs["previous_date"]), str(item.attrs["date"]))
            for item in evidence
            if item.attrs.get("previous_date") and item.attrs.get("date")
        ]
        if spans and asked_start != asked_end:
            start, end = min(s for s, _ in spans), max(e for _, e in spans)
            if (start, end) != (asked_start, asked_end):
                issues.append(AlignmentIssue(
                    "date_range_narrowed",
                    "Evidence phủ cửa sổ {}→{} thay vì {}→{} đã hỏi.".format(
                        start, end, asked_start, asked_end,
                    ),
                    tuple(digest.date_range),
                    (start, end),
                ))
    return issues


# A question that asks for a cause. Answering it with a count answers a
# different question -- exactly the substitution A22 exists to catch, but on the
# question side, which nothing inspected.
_CAUSAL_QUESTION_MARKERS = (
    "vi sao", "tai sao", "do dau", "nguyen nhan", "ly do",
    "mengapa", "kenapa", "why",
)

# A direction the question asserts about the data. It is a claim, not framing:
# "giảm mạnh" is false when the number rose, and explaining a fall that did not
# happen is worse than refusing.
_DECREASE_MARKERS = ("giam manh", "giam sut", "sut giam", "sut", "tut", "lao doc",
                     "chan lai", "cham lai", "turun", "menurun", "drop", "decline", "fell")
_INCREASE_MARKERS = ("tang manh", "tang vot", "tang truong", "but pha", "naik",
                     "melonjak", "surge", "spike", "rose", "grew")

_NUMBER = re.compile(r"\d")


def _premise_direction(question: str) -> int | None:
    """+1 when the question asserts a rise, -1 a fall, None when it asserts neither."""
    decrease = any(marker in question for marker in _DECREASE_MARKERS)
    increase = any(marker in question for marker in _INCREASE_MARKERS)
    if decrease == increase:
        return None  # neither, or both -- nothing unambiguous to check
    return -1 if decrease else 1


def _observed_direction(evidence: list[Evidence]) -> int | None:
    """Sign of the change the evidence shows across the observed dates."""
    by_date: dict[str, float] = {}
    for item in evidence:
        observed = item.attrs.get("observed_date")
        if observed is None or not isinstance(item.value, (int, float)) or isinstance(item.value, bool):
            continue
        if item.attrs.get("derivation_op"):
            # Một giá trị DẪN XUẤT (delta, share) không phải quan sát tại một
            # ngày — cho nó vào map ngày→giá trị là để một hiệu số đóng vai một
            # mức đo.
            continue
        by_date[str(observed)] = float(item.value)
    if len(by_date) < 2:
        return None
    dates = sorted(by_date)
    delta = by_date[dates[-1]] - by_date[dates[0]]
    if delta == 0:
        return 0
    return 1 if delta > 0 else -1


def check_question_alignment(
    digest: RequestDigest, answer: str, evidence: list[Evidence] | None = None,
) -> AlignmentVerdict:
    """Constraints the *question* carries, checked before its answer stands.

    Two failures live here because both are properties of the request, not of
    the plan or the evidence:

    * a causal question answered by a quantity (bgk13 asked *why* listings fell
      and was told *how many* there were);
    * a stated direction the data contradicts (they rose, 581 → 668).

    Both were invisible to every existing layer: the gate allowed it, the plan
    aligned, and the verifier passed because 668 genuinely had evidence behind
    it. It was the answer to a question nobody asked.
    """
    question = digest.normalized_question
    issues: list[AlignmentIssue] = []

    if any(marker in question for marker in _CAUSAL_QUESTION_MARKERS):
        # A quantity alone is not an account of a cause. Deliberately narrow:
        # only a bare numeric answer trips this, so a descriptive co-movement
        # answer (the most this dataset may claim) still passes.
        sentences = [part for part in re.split(r"[.;\n]", answer) if part.strip()]
        if len(sentences) <= 1 and _NUMBER.search(answer):
            issues.append(AlignmentIssue(
                "causal_question_unanswered",
                "Câu hỏi hỏi nguyên nhân nhưng câu trả lời chỉ đưa một con số.",
                ("causal_question",),
                ("scalar_answer",),
            ))

    stated = _premise_direction(question)
    observed = _observed_direction(evidence or [])
    if stated is not None and observed is not None and stated != observed:
        issues.append(AlignmentIssue(
            "premise_contradicted",
            "Câu hỏi giả định chiều biến động mà dữ liệu không xác nhận.",
            ("tăng" if stated > 0 else "giảm",),
            ("tăng" if observed > 0 else "giảm" if observed < 0 else "không đổi",),
        ))

    return AlignmentVerdict(not issues, tuple(issues))


def check_evidence_scope_alignment(
    digest: RequestDigest, evidence: list[Evidence],
) -> AlignmentVerdict:
    """Scope-only alignment for producers without a semantic plan (macros)."""
    if _empty_result_is_self_evident(evidence):
        return AlignmentVerdict(True, ())
    issues = _scope_issues(digest, evidence)
    return AlignmentVerdict(not issues, tuple(issues))


def check_answer_alignment(
    digest: RequestDigest,
    evidence: list[Evidence],
    claims: tuple[ResponseClaim, ...],
    answer: str,
) -> AlignmentVerdict:
    if _empty_result_is_self_evident(evidence):
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
