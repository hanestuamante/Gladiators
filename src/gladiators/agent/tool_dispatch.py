"""Generic tool dispatch — orchestrator gọi tool theo IntentSpec.tool_plan.

Điều kiện tiên quyết của Capability Router (V2 mục 7.3): thay vì workflow chứa
nhánh `if intent == "sales_decline": ...` cứng cho từng intent, orchestrator đọc
`tool_plan` từ Intent Registry rồi dispatch từng tool theo tên qua registry này.

Hệ quả: thêm intent mới = thêm 1 IntentSpec + (tái dùng hoặc thêm) tool handler,
KHÔNG sửa workflow core.

Mỗi handler nhận một `ToolContext` chung (đọc/ghi trạng thái tích lũy) và tự
append ToolCall + Evidence vào context. Handler có thể đặt `ctx.clarify` để yêu
cầu dừng plan và chuyển sang nhánh clarify (vd entity resolution mơ hồ).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from gladiators.analytics import AnalyticsTools
from gladiators.contracts import Evidence, GateDecision, ToolCall, StructuredRequest


@dataclass
class ToolContext:
    request: StructuredRequest
    tools: AnalyticsTools
    resolver: object
    resolved_listing_key: str | None = None
    clarify: GateDecision | None = None
    evidence: list[Evidence] = field(default_factory=list)
    calls: list[ToolCall] = field(default_factory=list)
    logical_plan: object | None = None


ToolHandler = Callable[[ToolContext], None]
_HANDLERS: dict[str, ToolHandler] = {}


def tool(name: str) -> Callable[[ToolHandler], ToolHandler]:
    """Đăng ký một tool handler theo tên (tên trùng khớp phần tử trong tool_plan)."""
    def decorator(fn: ToolHandler) -> ToolHandler:
        if name in _HANDLERS:
            raise ValueError(f"Tool đã đăng ký: {name}")
        _HANDLERS[name] = fn
        return fn
    return decorator


def _record(ctx: ToolContext, name: str, args: dict, evidence: list[Evidence]) -> None:
    ctx.evidence.extend(evidence)
    ctx.calls.append(ToolCall(
        name=name, args=args,
        status="ok" if evidence else "empty",
        evidence_ids=[e.evidence_id for e in evidence],
    ))


@tool("resolve_entity")
def _resolve_entity(ctx: ToolContext) -> None:
    entity_text = ctx.request.entity_text
    candidates = ctx.resolver.resolve(entity_text) if entity_text else []
    ctx.calls.append(ToolCall(name="resolve_entity", args={"entity_text": entity_text}, status="ok" if candidates else "empty"))
    if not candidates:
        ctx.clarify = GateDecision(
            action="abstain",
            rule_id="A-ENTITY-NOT-FOUND",
            reason="Không tìm thấy listing khớp entity/ID trong artifact hiện tại.",
        )
    elif ctx.resolver.ambiguous(candidates):
        ctx.clarify = GateDecision(action="clarify", rule_id="A-AMBIGUOUS", reason="Có nhiều listing gần giống; cần listing key hoặc URL chính xác hơn.")
    else:
        ctx.resolved_listing_key = candidates[0].listing_key


@tool("get_sales_transitions")
def _get_sales_transitions(ctx: ToolContext) -> None:
    if not ctx.resolved_listing_key:
        return
    snapshots = ctx.tools.repo.products.loc[
        ctx.tools.repo.products.product_listing_key.astype(str) == str(ctx.resolved_listing_key)
    ]
    if snapshots.date.astype(str).nunique() < 2:
        _record(ctx, "get_sales_transitions", {"listing_key": ctx.resolved_listing_key}, [])
        ctx.clarify = GateDecision(
            action="abstain", rule_id="A-INSUFFICIENT-SNAPSHOTS",
            reason="Listing chỉ có một snapshot; cần ít nhất hai snapshot hợp lệ để tính biến động.",
        )
        return
    evidence = ctx.tools.sales_decline(ctx.resolved_listing_key)
    _record(ctx, "get_sales_transitions", {"listing_key": ctx.resolved_listing_key}, evidence)


@tool("find_similar")
def _find_similar(ctx: ToolContext) -> None:
    if not ctx.resolved_listing_key:
        return
    evidence = ctx.tools.similar_products(ctx.resolved_listing_key)
    _record(ctx, "find_similar", {"listing_key": ctx.resolved_listing_key, "top_k": 5}, evidence)


@tool("compare_voucher_groups")
def _compare_voucher_groups(ctx: ToolContext) -> None:
    if not ctx.request.country:
        return
    evidence = ctx.tools.promotion_observation(ctx.request.country)
    _record(ctx, "compare_voucher_groups", {"country": ctx.request.country}, evidence)


@tool("compare_voucher_coverage")
def _compare_voucher_coverage(ctx: ToolContext) -> None:
    evidence = ctx.tools.voucher_coverage_by_country()
    _record(ctx, "compare_voucher_coverage", {}, evidence)


@tool("observe_discount_bucket")
def _observe_discount_bucket(ctx: ToolContext) -> None:
    evidence = ctx.tools.discount_bucket_observation()
    _record(ctx, "observe_discount_bucket", {"discount_percent": 50}, evidence)


@tool("describe_dataset_coverage")
def _describe_dataset_coverage(ctx: ToolContext) -> None:
    evidence = ctx.tools.dataset_coverage()
    _record(ctx, "describe_dataset_coverage", {}, evidence)


@tool("rank_voucher_profiles")
def _rank_voucher_profiles(ctx: ToolContext) -> None:
    if not ctx.request.country:
        return
    evidence = ctx.tools.voucher_profile_rank(ctx.request.country)
    _record(ctx, "rank_voucher_profiles", {"country": ctx.request.country}, evidence)


@tool("execute_analytical_plan")
def _execute_analytical_plan(ctx: ToolContext) -> None:
    if ctx.logical_plan is None:
        ctx.calls.append(ToolCall(name="execute_analytical_plan", status="error", error="Thiếu validated LogicalQueryPlan"))
        return
    evidence = ctx.tools.execute_analytical_plan(ctx.logical_plan)
    _record(ctx, "execute_analytical_plan", {"plan_id": ctx.logical_plan.plan_id}, evidence)


def dispatch(tool_plan: Iterable[str], ctx: ToolContext) -> None:
    """Chạy lần lượt các tool theo tool_plan; dừng sớm nếu một tool yêu cầu clarify."""
    for name in tool_plan:
        handler = _HANDLERS.get(name)
        if handler is None:
            ctx.calls.append(ToolCall(name=name, args={}, status="error", error=f"Không có handler cho tool '{name}'"))
            continue
        handler(ctx)
        if ctx.clarify is not None:
            break
