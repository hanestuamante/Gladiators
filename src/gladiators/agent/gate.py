from __future__ import annotations

from gladiators.contracts import GateDecision, StructuredRequest
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
    def decide(self, request: StructuredRequest, registry: IntentRegistry, capabilities: dict[str, object]) -> GateDecision:
        route = classify_external_need(str(request.slots.get("raw_text", "")))
        if route.rule_id == "A16-CROSS-CURRENCY":
            return GateDecision(
                action="clarify", rule_id=route.rule_id, reason=route.reason,
                answerable_alternative="Hãy hỏi riêng từng thị trường bằng đơn vị tiền địa phương.",
            )
        if len(request.countries) >= 2 and request.analytical:
            refs = {
                item.get("ref") for item in request.analytical.get("requested_measures", ())
                if isinstance(item, dict) and item.get("ref")
            }
            if any(
                ref in CATALOG and CATALOG[ref].unit == "local_currency"
                for ref in refs
            ):
                return GateDecision(
                    action="clarify",
                    rule_id="A16-CROSS-CURRENCY",
                    reason="Không cộng hoặc so sánh trực tiếp giá trị VND với IDR.",
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
            message = CAPABILITY_MESSAGES[missing]
            return GateDecision(
                action="abstain",
                rule_id=f"A-MISSING-{missing.upper()}",
                reason=" ".join((
                    message["missing"], message["coverage"], message["answerable"],
                )),
                answerable_alternative=message["alternative"],
            )
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
