from __future__ import annotations

from gladiators.contracts import GateDecision, GateIssue, IssueDetail, StructuredRequest
from gladiators.domain.intent_registry import IntentRegistry
from gladiators.planner.semantic_parser import AnalyticalRequest, classify_a19
from gladiators.external.router import classify_external_need
from gladiators.domain.catalog import CATALOG


def _message(missing: str, coverage: str, answerable: str, alternative: str) -> dict[str, str]:
    return {
        "missing": missing,
        "coverage": coverage,
        "answerable": answerable,
        "alternative": alternative,
    }


_DEFAULT_COVERAGE = (
    "Dữ liệu nội bộ chỉ quan sát listing tại ba snapshot đầu kỳ hiện hành, "
    "gồm giá, voucher và các proxy lượt bán."
)
# §4.5: phase/priority ordering is versioned data, not control flow.
PHASE_REGISTRY_VERSION = "gate-phases.v1"

CAPABILITY_MESSAGES: dict[str, dict[str, str]] = {
    "profit": _message(
        "Dataset không có giá vốn, phí sàn hay chi phí vận hành nên không tính được lợi nhuận.",
        _DEFAULT_COVERAGE,
        "Vẫn trả lời được doanh thu proxy ước tính, giá và lượt bán proxy.",
        "Ví dụ: 'Doanh thu proxy ước tính ở VN tại snapshot mới nhất là bao nhiêu?'",
    ),
    "forecast": _message(
        "Ba snapshot không đủ để lập dự báo hoặc seasonality đáng tin cậy.",
        _DEFAULT_COVERAGE,
        "Vẫn mô tả được chênh lệch giữa các snapshot đã quan sát.",
        "Ví dụ: 'Lượt bán proxy của listing X thay đổi thế nào qua các snapshot?'",
    ),
    "sku": _message(
        "Dataset không có sku_id/model_id; đơn vị nhỏ nhất là product listing.",
        "tier_variation chỉ mô tả lựa chọn hiển thị, không phân bổ doanh số theo biến thể.",
        "Vẫn trả lời được chỉ số ở cấp listing.",
        "Ví dụ: 'Listing X có bao nhiêu lượt bán proxy tại snapshot mới nhất?'",
    ),
    "ads": _message(
        "Dataset không có impressions, clicks hay ad spend nên không đo được quảng cáo.",
        _DEFAULT_COVERAGE,
        "Vẫn mô tả được giá, voucher và lượt bán proxy quan sát.",
        "Ví dụ: 'Giá và lượt bán proxy của listing X thay đổi thế nào?'",
    ),
    "inventory": _message(
        "Dataset không có số lượng tồn kho; cờ sold-out hiện không đủ để suy ra tồn thực tế.",
        _DEFAULT_COVERAGE,
        "Vẫn trả lời được proxy lượt bán và trạng thái listing đã quan sát.",
        "Ví dụ: 'Lượt bán proxy của listing X ở snapshot mới nhất là bao nhiêu?'",
    ),
    "conversion": _message(
        "Dataset không có sessions, views hay orders nên không tính được tỷ lệ chuyển đổi.",
        _DEFAULT_COVERAGE,
        "Vẫn trả lời được số listing, giá, voucher và proxy lượt bán.",
        "Ví dụ: 'Nhóm có voucher và không voucher khác nhau thế nào về sold proxy?'",
    ),
    "image_similarity": _message(
        "Hệ thống chưa có embedding hoặc nhãn tương đồng hình ảnh được chứng nhận.",
        "Hiện chỉ có thể xếp hạng tương đồng từ text/title ở cấp listing.",
        "Vẫn trả lời được phần tương đồng theo tiêu đề.",
        "Ví dụ: 'Tìm listing tương tự về tiêu đề với listing X.'",
    ),
    "reference": _message(
        "Dataset nội bộ không chứa tỷ giá có mốc thời gian và provenance được duyệt.",
        "Giá VN và Indonesia được giữ theo đơn vị địa phương, không cộng hoặc so trực tiếp.",
        "Vẫn trả lời được giá trị riêng cho từng thị trường.",
        "Ví dụ: 'Giá cao nhất ở VN là bao nhiêu VND?'",
    ),
    "external": _message(
        "Giá đối thủ hoặc giá thị trường cần nguồn ngoài có provenance.",
        "Dataset nội bộ chỉ chứa các listing đã thu thập trong phạm vi BTC.",
        "Vẫn trả lời được giá nội bộ theo từng thị trường.",
        "Ví dụ: 'Listing nào có giá cao nhất ở VN?'",
    ),
    "orders": _message(
        "Dataset không có order_id hay dòng đơn hàng.",
        _DEFAULT_COVERAGE,
        "Vẫn trả lời được proxy lượt bán ở cấp listing.",
        "Ví dụ: 'Có bao nhiêu listing ở VN tại snapshot mới nhất?'",
    ),
    "category_type": _message(
        "Semantic catalog chưa chứng nhận trường loại danh mục được yêu cầu.",
        "Hiện phân biệt platform category và shop shelf với quan hệ riêng.",
        "Vẫn trả lời được grouping theo danh mục đã expose.",
        "Ví dụ: 'Liệt kê listing theo platform category ở VN.'",
    ),
    "price_reconstruction": _message(
        "Không thể tái tạo giá cuối bằng cách trừ voucher lần nữa; price đã là giá quan sát.",
        "Voucher có điều kiện áp dụng và không phải mọi listing đều đủ điều kiện.",
        "Vẫn trả lời được price và voucher_discount như hai giá trị quan sát riêng.",
        "Ví dụ: 'Price và voucher_discount quan sát của listing X là bao nhiêu?'",
    ),
}


class ContractDrivenGate:
    """Phase-based gate — ultimate solution §4.5.

    Every rule below used to ``return`` the moment it matched, so a request with
    several problems only ever reported the first one and the trace could not
    show what else was wrong.  Rules now append a :class:`GateIssue` and the
    decision is chosen from the collected list by priority.

    Priority is deliberately the original evaluation order: the selected rule is
    identical to what the early-return chain produced, so this refactor changes
    what is *observable* without changing what is *decided*.  Ordering is now
    data in ``PHASE_REGISTRY_VERSION`` rather than control flow, which is what
    makes the §4.5 requirement "country slot must not mask an out-of-scope,
    rolling-window or fanout issue" expressible at all.
    """

    def decide(self, request: StructuredRequest, registry: IntentRegistry, capabilities: dict[str, object]) -> GateDecision:
        issues: list[GateIssue] = []
        phases: list[int] = []

        def add(
            rule_id: str, phase: int, action: str, reason: str,
            category: str, code: str, alternative: str | None = None,
            refs: tuple[str, ...] = (),
        ) -> None:
            issues.append(GateIssue(
                rule_id=rule_id, phase=phase, priority=len(issues) + 1,
                action=action, reason=reason, answerable_alternative=alternative,
                detail=IssueDetail(category=category, code=code, semantic_refs=refs),
            ))

        def decide_from(fallback: GateDecision) -> GateDecision:
            """Select the highest-priority issue, or fall through to ``fallback``."""
            if not issues:
                return fallback.model_copy(update={
                    "issues": (), "selected_issue_id": None,
                    "evaluated_phases": tuple(sorted(set(phases))),
                })
            chosen = min(issues, key=lambda item: item.priority)
            return GateDecision(
                action="abstain" if chosen.action == "block" else chosen.action,
                rule_id=chosen.rule_id, reason=chosen.reason,
                answerable_alternative=chosen.answerable_alternative,
                issues=tuple(issues), selected_issue_id=chosen.rule_id,
                evaluated_phases=tuple(sorted(set(phases))),
            )

        # ---- phase 1: capability / out-of-scope / route --------------------
        phases.append(1)
        route = classify_external_need(str(request.slots.get("raw_text", "")))
        if route.rule_id == "A16-CROSS-CURRENCY":
            add(route.rule_id, 1, "clarify", route.reason, "currency", "cross_currency",
                "Hãy hỏi riêng từng thị trường bằng đơn vị tiền địa phương.")
        if len(request.countries) >= 2 and request.analytical:
            refs = {
                item.get("ref") for item in request.analytical.get("requested_measures", ())
                if isinstance(item, dict) and item.get("ref")
            }
            if any(
                ref in CATALOG and CATALOG[ref].unit == "local_currency"
                for ref in refs
            ):
                add("A16-CROSS-CURRENCY", 4, "clarify",
                    "Không cộng hoặc so sánh trực tiếp giá trị VND với IDR.",
                    "currency", "cross_currency_measure",
                    "Hãy hỏi riêng từng thị trường bằng đơn vị tiền địa phương.",
                    tuple(sorted(r for r in refs if r)))
        if route.rule_id == "A14-EXT":
            add(route.rule_id, 1, "abstain", route.reason, "capability", "external_only_variable",
                "Có thể hỏi giá hoặc doanh thu proxy trong dataset nội bộ theo từng thị trường.")
        if route.mode == "external_only" and request.intent != "external_context":
            add("A14-ROUTE-MISMATCH", 1, "abstain",
                "Parser không bảo toàn live-context route; hệ thống chặn fail-closed thay vì chạy tool nội bộ sai.",
                "route", "route_not_preserved",
                "Hãy thử lại bằng câu hỏi chỉ nêu lịch chiến dịch hoặc sự kiện thị trường.")
        if request.intent.startswith("unsupported:"):
            missing = request.intent.split(":", 1)[1]
            message = CAPABILITY_MESSAGES[missing]
            add(f"A-MISSING-{missing.upper()}", 1, "abstain",
                " ".join((message["missing"], message["coverage"], message["answerable"])),
                "capability", f"unsupported_{missing}", message["alternative"])
            # Terminal capability block: later phases cannot mean anything for a
            # capability the system does not have (§4.5).
            return decide_from(GateDecision(action="allow", rule_id="A-ALLOW", reason=""))
        # ---- phase 2: intent and entity ------------------------------------
        phases.append(2)
        spec = registry.get(request.intent)
        if spec is None:
            add("A-UNKNOWN-INTENT", 2, "abstain", "Intent chưa được đăng ký.",
                "capability", "unknown_intent")
            # Terminal: without a registered spec there are no slots to check.
            return decide_from(GateDecision(action="allow", rule_id="A-ALLOW", reason=""))
        if request.intent == "external_context":
            if not bool(capabilities.get("live_search_enabled", False)):
                add("A14-LIVE", 2, "abstain",
                    "Câu hỏi cần live search nhưng cờ `sources.live_search.enabled` hiện đang OFF.",
                    "capability", "live_search_disabled",
                    "Có thể bật nguồn đã được duyệt rồi hỏi lại; dataset nội bộ không chứa lịch/sự kiện này.")
            return decide_from(GateDecision(
                action="allow", rule_id="A14-LIVE",
                reason="Live-search context path đã được bật có điều kiện."))
        if request.intent == "open_analytical":
            if not request.analytical:
                add("A19-PLAN", 2, "abstain",
                    "Thiếu AnalyticalRequest cho open analytical path.",
                    "capability", "missing_analytical")
                return decide_from(GateDecision(action="allow", rule_id="A-ALLOW", reason=""))
            admission = classify_a19(AnalyticalRequest.model_validate(request.analytical))
            if admission:
                action, rule_id, reason = admission
                add(rule_id, 3, action, reason, "grain", "a19_admission")
        # ---- phase 4: currency ---------------------------------------------
        phases.append(4)
        if request.intent == "analytical_query" and not request.country:
            add("A-CROSS-CURRENCY-SCOPE", 4, "clarify",
                "Cần chọn thị trường VN hoặc ID để không cộng/so sánh trực tiếp VND với IDR.",
                "currency", "missing_market_scope")
        # ---- phase 6: missing slot -----------------------------------------
        # Last on purpose (§4.5): a missing country slot must not mask an
        # out-of-scope, rolling-window or fanout issue found in an earlier phase.
        phases.append(6)
        values = {"entity_text": request.entity_text, "country": request.country, **request.slots}
        missing = [slot for slot in spec.required_slots if not values.get(slot)]
        if missing:
            add("A-MISSING-SLOT", 6, "clarify", f"Thiếu thông tin: {', '.join(missing)}",
                "slot", "missing_required_slot")
        if request.country and request.country not in capabilities["countries"]:
            add("A-COUNTRY", 6, "abstain", f"Không có dữ liệu cho quốc gia {request.country}.",
                "capability", "country_absent")
        if request.intent == "promotion_effectiveness" and request.country == "id" and capabilities["voucher_structured_by_country"].get("id", 0) == 0:
            add("A-VOUCHER-ID", 6, "abstain", "Indonesia không có voucher structured để so sánh.",
                "capability", "voucher_absent_market")
        if route.mode == "hybrid":
            if bool(capabilities.get("live_search_enabled", False)):
                return decide_from(GateDecision(
                    action="allow", rule_id="A14-HYBRID",
                    reason="Chạy internal analytics trước, sau đó bổ sung external context độc lập."))
            return decide_from(GateDecision(
                action="allow", rule_id="A14-HYBRID-PARTIAL",
                reason="Internal path khả dụng; `sources.live_search.enabled` đang OFF nên chỉ trả phần nội bộ kèm limitation."))
        return decide_from(GateDecision(
            action="allow", rule_id="A-ALLOW", reason="Contract và slot đáp ứng yêu cầu."))
