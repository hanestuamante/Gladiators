"""Invariant dispatch — Metadata Model & Binding Layer §E3.

``InvariantSpec.validator_id`` là mười một chuỗi trông như tham chiếu tới một
handler và không được dereference ở đâu cả: `rg validator_id src tests` chỉ thấy
khai báo, build, hash, prompt và test contract kiểm rằng chuỗi *có dấu chấm*.
Enforcement thật nằm rải rác trong validator/gate/alignment/wording, không có
liên kết máy-kiểm nào giữa spec và code.

Một ID trông hợp lệ nhưng không bao giờ được gọi nguy hơn thiếu registry, vì
prompt và context làm người đọc tin rule đã được enforce. Và hai tập đã lệch
thật: `INV-PRICE-SENTINEL-EXCLUDED` khai `measure.price` trong khi validator
chặn cả `measure.price_original` (§J1).

Module này biến ID thành callable. Handler ĐỌC ``spec.semantic_refs`` và
``spec.operators`` thay vì giữ bản sao riêng, nên spec và code không thể lệch
nữa mà không ai thấy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .invariants import INVARIANTS, InvariantSpec, InvariantStage, Severity

# Sentinel giá: 999999999 không phải giá cao nhất, nó là "không có giá".
PRICE_SENTINEL = 999_999_999


def governed_dates() -> tuple[str, ...]:
    """Những ngày bản dữ liệu đang phục vụ THẬT SỰ quan sát (W30).

    Trước W30 đây là một tuple ba phần tử viết tay. Nó đúng trên bộ đóng băng,
    nên không phép kiểm nào bắt được rằng nó mô tả MỘT bản dữ liệu chứ không mô
    tả một bất biến. ``INV-SNAPSHOT-SCOPE`` không đổi nghĩa — nó vẫn nói "chỉ
    được dùng ngày đã thu"; chỉ là danh sách ngày không còn viết tay.
    """
    from .calendar import default_calendar

    return default_calendar().dates


def __getattr__(name: str):
    # PEP 562: giữ ``from … import GOVERNED_DATES`` chạy được, nhưng hoãn việc
    # đọc bản dữ liệu tới lúc consumer thật sự cần — module này nằm trên đường
    # import của gần như mọi thứ.
    if name == "GOVERNED_DATES":
        return governed_dates()
    raise AttributeError(name)


class InvariantDispatchError(ValueError):
    """Raised at import khi một spec không resolve tới handler thật."""


@dataclass(frozen=True)
class InvariantViolation:
    invariant_id: str
    stage: InvariantStage
    severity: Severity
    message_key: str
    node_id: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class InvariantContext:
    """Mọi thứ một handler được phép nhìn, và không hơn.

    ``evidence`` là tuple các object BẤT BIẾN — handler chỉ đọc. Sửa Evidence gốc
    làm ``verifier._claim_value_matches`` lệch và đẩy mọi câu trả lời sang
    ``A-VERIFICATION-FINAL`` (bất biến hệ thống #4).
    """

    stage: InvariantStage
    request: Any = None
    plan: Any = None
    execution: Any = None
    evidence: tuple[Any, ...] = ()
    answer: str | None = None
    wording_violations: tuple[Mapping[str, str], ...] = ()


@runtime_checkable
class InvariantHandler(Protocol):
    handler_id: str
    handler_version: str
    stages: frozenset[InvariantStage]

    def validate(
        self, spec: InvariantSpec, context: InvariantContext
    ) -> tuple[InvariantViolation, ...]: ...


@dataclass(frozen=True)
class _Handler:
    """Base: giữ metadata, để subclass lo phần quyết định."""

    handler_id: str
    handler_version: str
    stages: frozenset[InvariantStage]

    def violation(
        self, spec: InvariantSpec, context: InvariantContext,
        *, node_id: str | None = None, **details: object,
    ) -> InvariantViolation:
        return InvariantViolation(
            invariant_id=spec.invariant_id, stage=context.stage, severity=spec.severity,
            message_key=spec.message_key, node_id=node_id, details=details,
        )

    def validate(
        self, spec: InvariantSpec, context: InvariantContext
    ) -> tuple[InvariantViolation, ...]:
        raise NotImplementedError


def _nodes(plan: Any) -> Sequence[Any]:
    return tuple(getattr(plan, "nodes", ()) or ())


def _ancestors(node: Any, by_id: Mapping[str, Any]) -> tuple[Any, ...]:
    seen: list[Any] = []
    stack = list(getattr(node, "inputs", ()) or ())
    visited: set[str] = set()
    while stack:
        node_id = stack.pop()
        if node_id in visited or node_id not in by_id:
            continue
        visited.add(node_id)
        current = by_id[node_id]
        seen.append(current)
        stack.extend(getattr(current, "inputs", ()) or ())
    return tuple(seen)


# --- handlers -------------------------------------------------------------

@dataclass(frozen=True)
class _SentinelExcluded(_Handler):
    """Trap #5: rank/aggregate trên giá phải chứng minh sentinel đã bị loại.

    Tập ref đến TỪ SPEC. Trước §J1 handler giữ set riêng
    ``{"measure.price", "measure.price_original"}`` còn spec khai một ref — code
    bảo vệ nhiều hơn spec tuyên bố, và không có test nào so được hai bên.
    """

    def validate(self, spec, context):
        plan = context.plan
        if plan is None or not spec.semantic_refs:
            return ()
        by_id = {node.node_id: node for node in _nodes(plan)}
        operators = set(spec.operators) or {"Aggregate", "Rank"}
        violations: list[InvariantViolation] = []
        for node in _nodes(plan):
            if node.op not in operators:
                continue
            consumed = set(node.refs)
            if getattr(node, "rank_by", None):
                consumed.add(node.rank_by)
            for ref in sorted(consumed & set(spec.semantic_refs)):
                excluded = any(
                    predicate.ref == ref
                    and predicate.op in {"lt", "lte"}
                    and isinstance(predicate.value, (int, float))
                    and float(predicate.value) <= PRICE_SENTINEL
                    for ancestor in _ancestors(node, by_id)
                    for predicate in ancestor.predicates
                )
                if not excluded:
                    violations.append(self.violation(
                        spec, context, node_id=node.node_id, ref=ref, op=node.op,
                        sentinel=PRICE_SENTINEL,
                    ))
        return tuple(violations)


@dataclass(frozen=True)
class _DedupeBeforeAggregate(_Handler):
    """Trap #12: Aggregate sau một Join fanout phải đi qua Dedupe."""

    def validate(self, spec, context):
        plan = context.plan
        if plan is None:
            return ()
        from .relations import RELATIONS

        by_id = {node.node_id: node for node in _nodes(plan)}
        violations: list[InvariantViolation] = []
        for node in _nodes(plan):
            if node.op != "Aggregate":
                continue
            ancestors = _ancestors(node, by_id)
            fanout = [
                item for item in ancestors
                if item.op == "Join" and item.relation in RELATIONS
                and RELATIONS[item.relation].fanout_effect != "none"
            ]
            if fanout and not any(item.op == "Dedupe" for item in ancestors):
                violations.append(self.violation(
                    spec, context, node_id=node.node_id,
                    relations=sorted(item.relation for item in fanout),
                ))
        return tuple(violations)


@dataclass(frozen=True)
class _NoShelfToPlatformEdge(_Handler):
    """Trap #2/#3: không có edge ShopCategory ↔ PlatformCategory.

    Kiểm bằng relation registry chứ không bằng tên: hai taxonomy có cột trùng
    tên (`category_id`, `shop_id`) nên suy theo tên là đúng cách tạo ra edge bị
    cấm.
    """

    def validate(self, spec, context):
        plan = context.plan
        if plan is None:
            return ()
        from .relations import RELATIONS

        forbidden = {"ShopCategory", "PlatformCategory"}
        violations: list[InvariantViolation] = []
        for node in _nodes(plan):
            if node.op != "Join":
                continue
            relation = RELATIONS.get(node.relation or "")
            if relation is None:
                continue
            if {relation.left, relation.right} == forbidden:
                violations.append(self.violation(
                    spec, context, node_id=node.node_id, relation=relation.name,
                ))
        return tuple(violations)


@dataclass(frozen=True)
class _SnapshotScope(_Handler):
    """Mọi time scope phải nằm trong ba snapshot được quản trị."""

    def validate(self, spec, context):
        scope: tuple[str, ...] = ()
        if context.plan is not None:
            scope = tuple(getattr(context.plan, "time_scope", ()) or ())
        elif context.request is not None:
            scope = tuple(getattr(context.request, "date_range", ()) or ())
        outside = sorted(set(scope) - set(governed_dates()))
        if outside:
            return (self.violation(spec, context, dates=outside),)
        return ()


@dataclass(frozen=True)
class _CurrencyNoMix(_Handler):
    """VND và IDR không được cộng/so trực tiếp.

    Một plan aggregate qua nhiều country trên ref tiền tệ tạo ra con số trông
    bình thường và không mang nghĩa gì.
    """

    def validate(self, spec, context):
        plan = context.plan
        if plan is None or not spec.semantic_refs:
            return ()
        by_id = {node.node_id: node for node in _nodes(plan)}
        operators = set(spec.operators) or {"Aggregate", "Union", "Rank"}
        violations: list[InvariantViolation] = []
        for node in _nodes(plan):
            if node.op not in operators:
                continue
            consumed = set(node.refs) | ({node.rank_by} if getattr(node, "rank_by", None) else set())
            monetary = sorted(consumed & set(spec.semantic_refs))
            if not monetary:
                continue
            # An toàn khi: group theo country, hoặc có predicate ghim đúng một
            # country ở đâu đó phía trên.
            grouped = "dim.country" in set(getattr(node, "group_by", ()) or ())
            pinned = any(
                predicate.ref == "dim.country"
                and (predicate.op == "eq"
                     or (predicate.op == "in" and len(_as_list(predicate.value)) == 1))
                for ancestor in _ancestors(node, by_id) + (node,)
                for predicate in ancestor.predicates
            )
            if not grouped and not pinned:
                violations.append(self.violation(
                    spec, context, node_id=node.node_id, refs=monetary, op=node.op,
                ))
        return tuple(violations)


def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, (list, tuple)) else [value]


@dataclass(frozen=True)
class _EvidenceDateRange(_Handler):
    """Evidence phải phủ đúng khoảng ngày được hỏi."""

    def validate(self, spec, context):
        request, evidence = context.request, context.evidence
        if request is None or not evidence:
            return ()
        requested = set(getattr(request, "date_range", ()) or ())
        if not requested:
            return ()
        covered: set[str] = set()
        for item in evidence:
            covered |= set(getattr(item, "date_range", ()) or ())
            window = getattr(item, "snapshot_window", None)
            if window:
                covered |= set(_as_list(window))
        missing = sorted(requested - covered)
        if missing and covered:
            return (self.violation(spec, context, missing_dates=missing),)
        return ()


@dataclass(frozen=True)
class _EvidenceCountryCoverage(_Handler):
    """Evidence phải phủ mọi country được hỏi, kiểm bằng field chứ không bằng text."""

    def validate(self, spec, context):
        request, evidence = context.request, context.evidence
        if request is None or not evidence:
            return ()
        requested = {str(code).lower() for code in getattr(request, "countries", ()) or ()}
        if not requested:
            return ()
        covered: set[str] = set()
        for item in evidence:
            for code in _as_list(getattr(item, "countries", ()) or ()):
                covered.add(str(code).lower())
            scope = getattr(item, "country_code", None)
            if scope:
                covered.add(str(scope).lower())
        missing = sorted(requested - covered)
        if missing and covered:
            return (self.violation(spec, context, missing_countries=missing),)
        return ()


@dataclass(frozen=True)
class _ZeroRowIsAResult(_Handler):
    """Không hàng nào khớp là một KẾT QUẢ, không phải lỗi.

    Handler tồn tại để chặn chiều ngược lại: không ai được "sửa" zero-row bằng
    cách nới filter hay đổi scope. Vi phạm là khi execution báo zero row nhưng
    scope đã bị đổi so với plan.
    """

    def validate(self, spec, context):
        execution = context.execution
        if execution is None:
            return ()
        if getattr(execution, "relaxed_filters", False):
            return (self.violation(spec, context, reason="relaxed_filters_on_empty"),)
        return ()


@dataclass(frozen=True)
class _FilterLiteralIsDatasetValue(_Handler):
    """Zero-row chỉ là một KẾT QUẢ khi bộ lọc chứng minh được nó đã chạy đúng.

    Hai cách vi phạm, cả hai đều làm số 0 trở nên vô nghĩa: một literal chưa
    được chứng minh tồn tại trong value index (``brand='bibica'`` khi dữ liệu
    ghi ``Bibica``), hoặc số predicate thực thi lệch số predicate trong plan
    (một bộ lọc rơi mất giữa plan và SQL). Đọc ``spec.semantic_refs`` thay vì
    giữ bản sao danh sách ref — hai danh sách là hai chỗ để chúng lệch nhau.
    """

    def validate(self, spec, context):
        execution = context.execution
        if execution is None or getattr(execution, "row_count", None) != 0:
            return ()
        executed = getattr(execution, "executed_predicate_count", None)
        planned = getattr(execution, "planned_predicate_count", None)
        if executed is not None and planned is not None and executed != planned:
            return (self.violation(
                spec, context, reason="predicate_count_mismatch",
            ),)
        unverified = sorted(
            ref for ref, verified in getattr(execution, "filter_bindings", ()) or ()
            if ref in spec.semantic_refs and not verified
        )
        if unverified:
            return (self.violation(
                spec, context, reason="unverified_literal", refs=unverified,
            ),)
        return ()


@dataclass(frozen=True)
class _WordingRule(_Handler):
    """Bọc ``agent.wording.check_wording``; mỗi rule tag map về một invariant.

    Handler không tự lint lại: một bản sao thứ hai của lexicon là đúng cách hai
    tập từ ngữ lệch nhau.
    """

    rules: frozenset[str] = frozenset()

    def validate(self, spec, context):
        if context.answer is None and not context.wording_violations:
            return ()
        violations = context.wording_violations
        if not violations and context.answer is not None:
            from ..agent.wording import check_wording

            violations = tuple(check_wording(context.answer))
        hits = [item for item in violations if item.get("rule") in self.rules]
        return tuple(
            self.violation(spec, context, rule=item.get("rule"), term=item.get("term"))
            for item in hits
        )


INVARIANT_HANDLERS: dict[str, InvariantHandler] = {
    handler.handler_id: handler
    for handler in (
        _SentinelExcluded(
            "sentinel.price_excluded_before_rank", "1.0", frozenset({"plan", "execution"}),
        ),
        _DedupeBeforeAggregate(
            "grain.dedupe_before_aggregate", "1.0", frozenset({"plan", "execution"}),
        ),
        _NoShelfToPlatformEdge(
            "relation.no_shelf_to_platform_edge", "1.0", frozenset({"plan"}),
        ),
        _SnapshotScope(
            "temporal.scope_within_governed_snapshots", "1.0",
            frozenset({"request", "plan", "evidence"}),
        ),
        _CurrencyNoMix(
            "currency.no_cross_market_arithmetic", "1.0",
            frozenset({"request", "plan", "evidence"}),
        ),
        _EvidenceDateRange(
            "temporal.evidence_matches_requested_range", "1.0", frozenset({"evidence"}),
        ),
        _EvidenceCountryCoverage(
            "scope.evidence_covers_requested_countries", "1.0", frozenset({"evidence"}),
        ),
        _ZeroRowIsAResult(
            "execution.zero_row_is_a_result", "1.0", frozenset({"execution", "evidence"}),
        ),
        _FilterLiteralIsDatasetValue(
            "binding.filter_literal_exists_in_dataset", "1.0", frozenset({"execution"}),
        ),
        _WordingRule(
            "wording.no_causal_claim", "1.0", frozenset({"answer"}),
            rules=frozenset({"causal_language", "same_sku_claim", "forecast_claim"}),
        ),
        _WordingRule(
            "wording.proxy_labelled_as_estimate", "1.0", frozenset({"answer"}),
            rules=frozenset({"revenue_missing_estimate_label"}),
        ),
        _WordingRule(
            "wording.no_internal_jargon", "1.0", frozenset({"answer"}),
            rules=frozenset({"jargon", "internal_rule_id"}),
        ),
    )
}


def _check_dispatch(
    invariants: Mapping[str, InvariantSpec],
    handlers: Mapping[str, InvariantHandler],
) -> None:
    """Build-time: mọi spec phải resolve, và handler phải phủ mọi stage đã khai."""
    seen_versions: dict[str, str] = {}
    for handler_id, handler in handlers.items():
        if not handler.handler_version:
            raise InvariantDispatchError(f"{handler_id}: handler_version rỗng")
        if handler_id in seen_versions:
            raise InvariantDispatchError(f"handler_id trùng: {handler_id}")
        seen_versions[handler_id] = handler.handler_version

    for spec in invariants.values():
        handler = handlers.get(spec.validator_id)
        if handler is None:
            raise InvariantDispatchError(
                f"{spec.invariant_id}: validator_id không resolve tới handler: "
                f"{spec.validator_id}"
            )
        uncovered = sorted(set(spec.applies_to) - handler.stages)
        if uncovered:
            raise InvariantDispatchError(
                f"{spec.invariant_id}: handler {spec.validator_id} không phủ stage "
                f"{uncovered}"
            )

    unused = sorted(set(handlers) - {spec.validator_id for spec in invariants.values()})
    if unused:
        raise InvariantDispatchError(f"Handler không spec nào dùng: {unused}")


_check_dispatch(INVARIANTS, INVARIANT_HANDLERS)


def enforce_invariants(
    stage: InvariantStage, context: InvariantContext
) -> tuple[InvariantViolation, ...]:
    """Chạy mọi invariant khai báo ``stage`` và trả violation typed.

    Không tự sửa, không hạ severity, không bỏ qua. Caller quyết định biến
    violation thành ``PlanIssue``/``clarify``/``abstain`` — dispatcher chỉ nói
    rule nào bị vi phạm.
    """
    violations: list[InvariantViolation] = []
    for spec in sorted(INVARIANTS.values(), key=lambda item: item.invariant_id):
        if stage not in spec.applies_to:
            continue
        handler = INVARIANT_HANDLERS[spec.validator_id]
        violations.extend(handler.validate(spec, context))
    return tuple(violations)


def hard_violations(
    violations: tuple[InvariantViolation, ...]
) -> tuple[InvariantViolation, ...]:
    return tuple(item for item in violations if item.severity == "hard")


HANDLER_PAYLOAD: tuple[dict[str, object], ...] = tuple(
    {"id": handler.handler_id, "version": handler.handler_version,
     "stages": sorted(handler.stages)}
    for handler in sorted(INVARIANT_HANDLERS.values(), key=lambda item: item.handler_id)
)
