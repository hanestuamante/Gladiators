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
    # §4.2: span, scores and margin belong in the trace; the UI only ever sees
    # the business message built from the state.
    entity_resolution: object | None = None


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

    # §4.2: three distinct failure states, each with its own remedy, instead of
    # one boolean that could only ever produce one message.
    result = ctx.resolver.classify(entity_text, candidates)
    ctx.entity_resolution = result
    if result.state == "resolved":
        ctx.resolved_listing_key = result.candidates[0].listing_key
        return
    if result.state == "not_found":
        ctx.clarify = GateDecision(
            action="abstain",
            rule_id="A-ENTITY-NOT-FOUND",
            reason="Không tìm thấy listing nào khớp mã hoặc tên trong dữ liệu hiện có.",
        )
        return
    if result.state == "invalid_extraction":
        ctx.clarify = GateDecision(
            action="abstain",
            rule_id="A-ENTITY-NOT-FOUND",
            reason="Không tìm thấy listing nào khớp phần mô tả sản phẩm trong câu hỏi.",
            answerable_alternative="Hãy nêu listing key, mã sản phẩm hoặc tên đầy đủ hơn.",
        )
        return
    # ambiguous_broad: hand back the shortlist rather than guessing. §4.2 forbids
    # breaking the tie by picking the best-selling listing, which would turn "which
    # one did you mean" into a confident wrong answer. Scores stay in the trace;
    # the message carries names only, and never a threshold.
    names = tuple(item.display_name[:70] for item in result.candidates)
    shortlist = "; ".join(names)
    ctx.clarify = GateDecision(
        action="clarify", rule_id="A-AMBIGUOUS",
        # Carried so the verifier can tell an echoed product name from a claim.
        quoted_texts=names,
        reason=f"Có nhiều listing gần giống nhau: {shortlist}.",
        answerable_alternative="Hãy chọn một trong các listing trên, hoặc đưa listing key chính xác.",
    )


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
    dates = sorted(str(item) for item in (ctx.request.date_range or []))
    window = (dates[0], dates[-1]) if len(dates) >= 2 else None
    evidence = ctx.tools.sales_decline(ctx.resolved_listing_key, window=window)
    if window is not None and not evidence:
        _record(ctx, "get_sales_transitions", {
            "listing_key": ctx.resolved_listing_key, "window": list(window),
        }, [])
        ctx.clarify = GateDecision(
            action="abstain", rule_id="A-NO-EVIDENCE",
            reason="Các chặng transition không phủ kín cửa sổ được hỏi, nên "
                   "không tính được biến động cho đúng cửa sổ đó.",
        )
        return
    _record(ctx, "get_sales_transitions", {
        "listing_key": ctx.resolved_listing_key,
        **({"window": list(window)} if window else {}),
    }, evidence)


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
    from gladiators.analytics.tools import SparseObservationError

    try:
        evidence = ctx.tools.execute_analytical_plan(ctx.logical_plan)
    except SparseObservationError as exc:
        # W29-R1 — phạm vi quá thưa để phát biểu về nó. `clarify`, KHÔNG phải
        # `abstain`: câu hỏi TRẢ LỜI ĐƯỢC, chỉ không ở cái grain thời gian người
        # dùng nêu. Dùng đúng idiom `ctx.clarify` mà `_resolve_entity` đã dùng,
        # nên `dispatch()` dừng sớm bằng cơ chế có sẵn.
        ctx.clarify = GateDecision(
            action="clarify", rule_id="A-SPARSE-OBSERVATION", reason=str(exc),
            clarification_slot="observation_window",
            answerable_alternative=(
                "Hệ thống trả lời được theo lần quan sát gần nhất của từng "
                "listing, và sẽ nêu rõ cửa sổ quan sát."
            ),
        )
        ctx.calls.append(ToolCall(
            name="execute_analytical_plan", status="error",
            error="sparse_observation",
        ))
        return
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


@tool("explain_relation")
def _explain_relation(ctx: ToolContext) -> None:
    """WP-A7 — giải thích quan hệ, đọc thẳng từ registry.

    KHÔNG sinh ``Evidence`` (A7-R2): đây không phải một tuyên bố về dữ liệu, nên
    không có con số nào cần chống lưng. Kết quả đi qua ``slots`` để ``_generate``
    dựng câu chữ.
    """
    from gladiators.domain.relation_prose import explain

    entities = ctx.request.slots.get("relation_entities") or []
    if not entities:
        return
    left = entities[0]
    right = entities[1] if len(entities) > 1 else None
    ctx.request.slots["relation_explanation"] = explain(left, right)
    _record(ctx, "explain_relation", {"entities": list(entities)}, [])
