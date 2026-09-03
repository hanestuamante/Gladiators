"""Rule-based QueryRiskScore và escalation ladder — V2 mục 7.9."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gladiators.domain.relations import RELATIONS, find_path

from .query_ir import Op, LogicalQueryPlan
# Ngân sách A1.4 — dùng CHUNG hằng số của bộ sinh kế hoạch: hai bản sao là
# đúng cách vị từ chấp nhận và bộ sinh lệch nhau về cùng một giới hạn.
from .synthesizer import RELATION_EDGE_BUDGET as _RELATION_EDGE_BUDGET
from .validator import validate_plan

EscalationMode = Literal["single", "critic", "nversion", "blocked"]

# Lớp xuất xứ của plan. Thang leo thang tồn tại để review một plan do MÔ HÌNH
# viết — schema_linking, entity_margin, new_metric đều là bất định của bước ánh
# xạ chữ→ký hiệu. Một plan tất định không chứa output nào của mô hình, nên đưa
# nó cho critic (bản thân critic là một mô hình) không thêm thông tin nào về nó.
PlanProvenance = Literal[
    "deterministic_synthesis", "deterministic_template", "certified_macro", "llm_ir",
]
_DETERMINISTIC_PROVENANCE = frozenset({
    "deterministic_synthesis", "deterministic_template", "certified_macro",
})

# 12 operator của IR. Danh sách lấy TỪ Op, không chép tay: một bản sao là đúng
# cách hai danh sách lệch nhau khi thêm operator thứ mười ba.
_IR_OPS = frozenset(Op.__args__)


def deterministic_plan_is_acceptable(plan: LogicalQueryPlan) -> tuple[bool, str]:
    """Plan tất định có được chạy mà không cần critic hay không (W7.2).

    Đây KHÔNG phải một ngưỡng điểm nới lỏng. Nó là danh sách những tính chất mà
    thang leo thang đang dùng điểm số để ƯỚC LƯỢNG, kiểm trực tiếp trên plan:
    một critic là mô hình, và một mô hình không nói được điều gì về một plan
    không có mô hình nào trong đó.

    Sáu điều kiện, TẤT CẢ phải đúng; sai bất kỳ ⇒ blocked như hôm nay.
    """
    verdict = validate_plan(plan)
    if not verdict.valid:
        return False, "plan_invalid"

    joins = [node for node in plan.nodes if node.op == "Join"]
    for node in plan.nodes:
        if node.op not in _IR_OPS:
            return False, f"operator_ngoai_hop_dong:{node.op}"

    for node in joins:
        spec = RELATIONS.get(node.relation or "")
        if spec is None:
            return False, f"relation_chua_chung_nhan:{node.relation}"
        # Đường dài đúng 1: registry đổi hình (thêm nan hoa trung gian) mà không
        # ai review sẽ hiện ra ở đây thay vì chạy im lặng qua một đường mới.
        path = find_path(spec.left, spec.right)
        if path is None or len(path) != 1:
            return False, f"duong_quan_he_khong_dai_mot:{node.relation}"

    if len(joins) > _RELATION_EDGE_BUDGET:
        return False, f"vuot_ngan_sach_quan_he:{len(joins)}"

    first_aggregate = next(
        (index for index, node in enumerate(plan.nodes) if node.op == "Aggregate"),
        None,
    )
    for index, node in enumerate(plan.nodes):
        spec = RELATIONS.get(node.relation or "") if node.op == "Join" else None
        if spec is None:
            continue
        if spec.fanout_effect != "none":
            # INV-DEDUPE-BEFORE-AGGREGATE: fanout rồi tổng hợp là đếm trùng.
            deduped = any(
                other.op == "Dedupe"
                for other in plan.nodes[index + 1:first_aggregate]
            ) if first_aggregate is not None else True
            if not deduped:
                return False, f"fanout_khong_dedupe:{spec.name}"
        if spec.temporal_validity == "static_latest_only":
            # Enrichment tĩnh dùng như panel theo ngày: mỗi ngày sẽ nhận cùng
            # một giá trị và bảng kết quả trông như một chuỗi thời gian thật.
            if len(plan.time_scope) != 1:
                return False, f"static_latest_only_nhieu_moc:{spec.name}"
            if any("dim.date" in (node.group_by or ()) for node in plan.nodes):
                return False, f"static_latest_only_group_theo_ngay:{spec.name}"

    return True, "vi_tu_dat"


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
    # Mặc định "llm_ir" ⇒ mọi call site chưa cập nhật giữ NGUYÊN hành vi hôm nay.
    plan_provenance: PlanProvenance = "llm_ir",
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
    # Vị từ chạy TRƯỚC cả nhánh complexity_level == "L3", không chỉ trước phép
    # so với tau1: đường template bị chặn bằng một cơ chế THỨ HAI độc lập với
    # ngưỡng, và vòng qua mỗi tau1 sẽ làm W7 trông như đã xong trong khi một nửa
    # cơ chế còn nguyên (§8.3.1).
    if plan_provenance in _DETERMINISTIC_PROVENANCE:
        acceptable, reason = deterministic_plan_is_acceptable(plan)
        if acceptable:
            # Điểm và factor VẪN được tính và ghi trace nguyên vẹn — chúng là
            # quan sát, và bỏ đi thì không ai đo được vị từ này có đang che một
            # plan đáng ngờ hay không.
            requested = (
                "nversion" if score >= config.tau2 or complexity_level == "L4"
                else "critic" if score >= config.tau1 or complexity_level == "L3"
                else "single"
            )
            return QueryRiskResult(
                score, tuple(factors), requested, "single", True,
                "Plan tất định đạt vị từ chấp nhận; thang leo thang chỉ áp cho "
                "plan do mô hình sinh.",
            )
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
