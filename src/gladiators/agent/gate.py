from __future__ import annotations

from gladiators.contracts import GateDecision, StructuredRequest
from gladiators.domain.intent_registry import IntentRegistry
from gladiators.planner.semantic_parser import AnalyticalRequest, classify_a19


class ContractDrivenGate:
    def decide(self, request: StructuredRequest, registry: IntentRegistry, capabilities: dict[str, object]) -> GateDecision:
        if request.intent.startswith("unsupported:"):
            missing = request.intent.split(":", 1)[1]
            return GateDecision(action="abstain", rule_id=f"A-MISSING-{missing.upper()}", reason=f"Dữ liệu hiện tại không có capability `{missing}`.", answerable_alternative="Có thể hỏi về proxy lượt bán, giá, voucher quan sát được hoặc sản phẩm tương tự.")
        spec = registry.get(request.intent)
        if spec is None:
            return GateDecision(action="abstain", rule_id="A-UNKNOWN-INTENT", reason="Intent chưa được đăng ký.")
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
        return GateDecision(action="allow", rule_id="A-ALLOW", reason="Contract và slot đáp ứng yêu cầu.")
