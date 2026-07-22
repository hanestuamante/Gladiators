from __future__ import annotations

from gladiators.contracts import GateDecision, StructuredRequest
from gladiators.domain.intent_registry import IntentRegistry
from gladiators.planner.semantic_parser import AnalyticalRequest, classify_a19
from gladiators.external.router import classify_external_need


class ContractDrivenGate:
    def decide(self, request: StructuredRequest, registry: IntentRegistry, capabilities: dict[str, object]) -> GateDecision:
        route = classify_external_need(str(request.slots.get("raw_text", "")))
        if route.rule_id == "A16-CROSS-CURRENCY":
            return GateDecision(
                action="clarify", rule_id=route.rule_id, reason=route.reason,
                answerable_alternative="Hãy hỏi riêng từng thị trường bằng đơn vị tiền địa phương.",
            )
        if route.rule_id == "A14-EXT":
            return GateDecision(
                action="abstain", rule_id=route.rule_id, reason=route.reason,
                answerable_alternative="Có thể hỏi giá hoặc doanh thu proxy trong dataset nội bộ theo từng thị trường.",
            )
        if route.mode == "external_only" and request.intent != "external_context":
            return GateDecision(
                action="abstain", rule_id="A14-ROUTE-MISMATCH",
                reason="Parser không bảo toàn live-context route; hệ thống chặn fail-closed thay vì chạy tool nội bộ sai.",
                answerable_alternative="Hãy thử lại bằng câu hỏi chỉ nêu lịch chiến dịch hoặc sự kiện thị trường.",
            )
        if request.intent.startswith("unsupported:"):
            missing = request.intent.split(":", 1)[1]
            return GateDecision(action="abstain", rule_id=f"A-MISSING-{missing.upper()}", reason=f"Dữ liệu hiện tại không có capability `{missing}`.", answerable_alternative="Có thể hỏi về proxy lượt bán, giá, voucher quan sát được hoặc sản phẩm tương tự.")
        spec = registry.get(request.intent)
        if spec is None:
            return GateDecision(action="abstain", rule_id="A-UNKNOWN-INTENT", reason="Intent chưa được đăng ký.")
        if request.intent == "external_context":
            if not bool(capabilities.get("live_search_enabled", False)):
                return GateDecision(
                    action="abstain", rule_id="A14-LIVE",
                    reason="Câu hỏi cần live search nhưng cờ `sources.live_search.enabled` hiện đang OFF.",
                    answerable_alternative="Có thể bật nguồn đã được duyệt rồi hỏi lại; dataset nội bộ không chứa lịch/sự kiện này.",
                )
            return GateDecision(action="allow", rule_id="A14-LIVE", reason="Live-search context path đã được bật có điều kiện.")
        if request.intent == "open_analytical":
            if not request.analytical:
                return GateDecision(action="abstain", rule_id="A19-PLAN", reason="Thiếu AnalyticalRequest cho open analytical path.")
            admission = classify_a19(AnalyticalRequest.model_validate(request.analytical))
            if admission:
                action, rule_id, reason = admission
                return GateDecision(action=action, rule_id=rule_id, reason=reason)
        if request.intent == "analytical_query" and not request.country:
            return GateDecision(
                action="clarify", rule_id="A-CROSS-CURRENCY-SCOPE",
                reason="Cần chọn thị trường VN hoặc ID để không cộng/so sánh trực tiếp VND với IDR.",
            )
        values = {"entity_text": request.entity_text, "country": request.country, **request.slots}
        missing = [slot for slot in spec.required_slots if not values.get(slot)]
        if missing:
            return GateDecision(action="clarify", rule_id="A-MISSING-SLOT", reason=f"Thiếu thông tin: {', '.join(missing)}")
        if request.country and request.country not in capabilities["countries"]:
            return GateDecision(action="abstain", rule_id="A-COUNTRY", reason=f"Không có dữ liệu cho quốc gia {request.country}.")
        if request.intent == "promotion_effectiveness" and request.country == "id" and capabilities["voucher_structured_by_country"].get("id", 0) == 0:
            return GateDecision(action="abstain", rule_id="A-VOUCHER-ID", reason="Indonesia không có voucher structured để so sánh.")
        if route.mode == "hybrid":
            if bool(capabilities.get("live_search_enabled", False)):
                return GateDecision(action="allow", rule_id="A14-HYBRID", reason="Chạy internal analytics trước, sau đó bổ sung external context độc lập.")
            return GateDecision(
                action="allow", rule_id="A14-HYBRID-PARTIAL",
                reason="Internal path khả dụng; `sources.live_search.enabled` đang OFF nên chỉ trả phần nội bộ kèm limitation.",
            )
        return GateDecision(action="allow", rule_id="A-ALLOW", reason="Contract và slot đáp ứng yêu cầu.")
