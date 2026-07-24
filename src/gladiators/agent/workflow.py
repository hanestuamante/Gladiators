from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

from pydantic import ValidationError

from gladiators.analytics import AnalyticsTools
from gladiators.contracts import AgentResponse, Evidence, GateDecision, ResponseClaim, StructuredRequest, ToolCall
from gladiators.data.repository import ArtifactRepository
from gladiators.domain.intent_registry import default_registry
from gladiators.planner.macros import default_macro_registry
from gladiators.planner.analytical import AnalyticalPlanError, build_analytical_plan, infer_deterministic_template
from gladiators.planner.semantic_parser import AnalyticalRequest, classify_complexity
from gladiators.planner.open_planner import OpenAnalyticalPlanner, OpenPlannerError
from gladiators.planner.consensus import ConsensusError, NVersionResolver
from gladiators.planner.risk import EscalationConfig, score_plan
from gladiators.planner.critic import PlanCritic
from .embedding import BGEIndex
from .entity_resolution import EntityResolver
from .gate import ContractDrivenGate
from .parser import MultilingualIntentParser, UNSUPPORTED
from .tool_dispatch import ToolContext, dispatch
from .trace import TraceStore
from .verifier import verify_numeric_claims
from .wording import check_wording


class AgentRuntime:
    def __init__(
        self,
        data_dir: str = "data/processed",
        trace_dir: str = "artifacts/traces",
        enable_gate: bool = True,
        enable_verifier: bool = True,
        llm_client: Any | None = None,
        critic_client: Any | None = None,
        use_llm_parser: bool = False,
        use_llm_generation: bool = False,
        enable_critic: bool | None = None,
        enable_nversion: bool | None = None,
        alternate_planner_client: Any | None = None,
        adjudicator_client: Any | None = None,
        external_pipeline: Any | None = None,
        enable_live_search: bool | None = None,
        enable_voucher_profile: bool | None = None,
    ):
        self.repo = ArtifactRepository(data_dir)
        self.registry = default_registry()
        self.macros = default_macro_registry()
        self.enable_gate, self.enable_verifier = enable_gate, enable_verifier
        self.llm_client = llm_client
        self.enable_critic = os.getenv("GLADIATORS_ENABLE_CRITIC") == "1" if enable_critic is None else enable_critic
        self.enable_nversion = os.getenv("GLADIATORS_ENABLE_NVERSION") == "1" if enable_nversion is None else enable_nversion
        self.plan_critic = PlanCritic(critic_client or llm_client)
        self.open_planner = OpenAnalyticalPlanner(llm_client)
        self.nversion = NVersionResolver(
            self.repo, alternate_planner_client or llm_client, adjudicator_client or llm_client,
        )
        self.use_llm_parser, self.use_llm_generation = use_llm_parser, use_llm_generation
        self.external_pipeline = external_pipeline
        requested_live = os.getenv("GLADIATORS_ENABLE_LIVE_SEARCH") == "1" if enable_live_search is None else enable_live_search
        # A flag without a wired, bounded pipeline is not a capability.
        self.enable_live_search = bool(requested_live and external_pipeline is not None)
        # T-11 (V2 §2.8): định nghĩa voucher_profile_rank_v1 đã có trong metric
        # registry nhưng weights chờ DR1/Lead ký; mặc định OFF → A19-METRIC clarify.
        self.enable_voucher_profile = (
            os.getenv("GLADIATORS_ENABLE_VOUCHER_PROFILE") == "1"
            if enable_voucher_profile is None else enable_voucher_profile
        )
        self.parser, self.gate = MultilingualIntentParser(), ContractDrivenGate()
        dense = BGEIndex() if os.getenv("GLADIATORS_ENABLE_BGE") == "1" else None
        self.resolver = EntityResolver(self.repo.products, embeddings=dense)
        self.traces = TraceStore(trace_dir)

    def _parse(self, user_text: str) -> tuple[StructuredRequest, dict[str, Any]]:
        meta = {"provider": "deterministic", "parse_fallback": False, "parse_attempts": 0}
        if not (self.use_llm_parser and self.llm_client):
            return self.parser.parse(user_text, self.registry), meta
        meta.update(provider=self.llm_client.provider, model=self.llm_client.model, prompt_version=self.llm_client.prompt_version)
        errors = []
        for attempt in range(2):
            meta["parse_attempts"] = attempt + 1
            try:
                parsed = self.llm_client.parse_intent(user_text, self.registry.names())
                deterministic = self.parser.parse(user_text, self.registry)
                adjustments = []
                if deterministic.route_mode in {"external_only", "hybrid"} and (
                    parsed.intent != deterministic.intent or parsed.route_mode != deterministic.route_mode
                ):
                    parsed = parsed.model_copy(update={
                        "intent": deterministic.intent,
                        "country": deterministic.country,
                        "slots": deterministic.slots,
                        "analytical": deterministic.analytical,
                        "route_mode": deterministic.route_mode,
                        "external_purpose": deterministic.external_purpose,
                        "requested_variables": deterministic.requested_variables,
                    })
                    adjustments.append("deterministic_route_safety_precedence")
                elif deterministic.intent.startswith("unsupported:") and parsed.intent != deterministic.intent:
                    parsed = parsed.model_copy(update={"intent": deterministic.intent}); adjustments.append("unsupported_safety_precedence")
                elif parsed.intent.startswith("unsupported:") and (parsed.intent.split(":", 1)[1] not in UNSUPPORTED or self.registry.get(deterministic.intent) is not None):
                    parsed = parsed.model_copy(update={"intent": deterministic.intent}); adjustments.append("unsupported_taxonomy_normalized")
                spec = self.registry.get(parsed.intent)
                if spec:
                    updates = {}
                    if "entity_text" not in spec.required_slots and parsed.entity_text is not None:
                        updates["entity_text"] = None; adjustments.append("irrelevant_entity_removed")
                    elif "entity_text" in spec.required_slots and deterministic.entity_text and parsed.entity_text != deterministic.entity_text:
                        updates["entity_text"] = deterministic.entity_text; adjustments.append("entity_from_deterministic_parser")
                    if not parsed.country and deterministic.country:
                        updates["country"] = deterministic.country; adjustments.append("country_from_deterministic_parser")
                    # P1 only classifies the top-level intent. Certified analytical
                    # templates and the open analytical path carry deterministic,
                    # typed payloads that P8 needs; never discard them when P1
                    # agrees with the deterministic route.
                    if parsed.intent == deterministic.intent:
                        merged_slots = {**parsed.slots, **deterministic.slots}
                        if merged_slots != parsed.slots:
                            updates["slots"] = merged_slots
                            adjustments.append("slots_from_deterministic_parser")
                        if parsed.analytical is None and deterministic.analytical is not None:
                            updates["analytical"] = deterministic.analytical
                            adjustments.append("analytical_from_deterministic_parser")
                    if updates: parsed = parsed.model_copy(update=updates)
                if adjustments: meta["parse_adjustments"] = adjustments
                if self.registry.get(parsed.intent) is None and not parsed.intent.startswith("unsupported:"):
                    raise ValueError(f"Intent ngoài registry: {parsed.intent}")
                return parsed, meta
            except (ValueError, ValidationError, RuntimeError, KeyError) as exc:
                errors.append(type(exc).__name__)
        meta.update(parse_fallback=True, parse_errors=errors)
        return self.parser.parse(user_text, self.registry), meta

    @staticmethod
    def _deterministic_answer(decision: GateDecision, request: StructuredRequest, evidence: list[Evidence]) -> str:
        if decision.action == "abstain":
            return f"Không thể trả lời chắc chắn: {decision.reason} {decision.answerable_alternative or ''}".strip()
        if decision.action == "clarify":
            return f"Cần làm rõ: {decision.reason}"
        if request.route_mode == "hybrid":
            internal = [item for item in evidence if item.source_tier == "btc_dataset"]
            external = [item for item in evidence if item.source_tier != "btc_dataset"]
            internal_request = request.model_copy(update={
                "route_mode": "internal_only", "external_purpose": None,
            })
            internal_answer = AgentRuntime._deterministic_answer(decision, internal_request, internal)
            if external:
                external_request = request.model_copy(update={
                    "intent": "external_context", "route_mode": "external_only",
                })
                external_answer = AgentRuntime._deterministic_answer(decision, external_request, external)
                return (
                    "PHẦN NỘI BỘ\n" + internal_answer + "\n\n"
                    "BỐI CẢNH NGOÀI — KHÔNG PHẢI BẰNG CHỨNG NHÂN QUẢ\n" + external_answer
                )
            reason = str(request.slots.get(
                "external_ladder_reason",
                "sources.live_search.enabled đang OFF hoặc không có external evidence hợp lệ",
            ))
            return (
                "PHẦN NỘI BỘ\n" + internal_answer + "\n\n"
                "BỐI CẢNH NGOÀI\nTạm thiếu: " + reason + ". Phần nội bộ ở trên vẫn giữ nguyên."
            )
        by_metric = {e.metric: e for e in evidence}
        if request.intent == "external_context" and evidence:
            lines = []
            sources = []
            for item in evidence:
                provenance = item.provenance
                assert provenance is not None
                retrieved = provenance.retrieved_at.isoformat()
                lines.append(
                    f"- Bối cảnh web trực tiếp (context_only): {item.value} "
                    f"[{item.evidence_id}] [nguồn: {provenance.source_id}, lấy {retrieved}]."
                )
                sources.append(
                    f"- External: {provenance.source_id} — {provenance.source_locator.value}; "
                    f"lấy {retrieved}; mapping: {provenance.mapping_status}; "
                    f"content_hash: {provenance.content_hash}; license: {provenance.license} "
                    f"[{item.evidence_id}]"
                )
            return (
                "Kết quả\n" + "\n".join(lines) + "\n\n"
                "Phạm vi\nNguồn web chỉ bổ sung bối cảnh cho câu hỏi; không thay đổi fact trong dataset BTC.\n\n"
                "Giới hạn\nCác ánh xạ đều needs_review — chưa xác nhận cùng sản phẩm/thực thể; "
                "không dùng để suy ra nhân quả, giá trị nội bộ hoặc so sánh xuyên tier.\n\n"
                "Độ tin cậy\nLow — context_only, phụ thuộc nội dung nguồn tại thời điểm truy xuất.\n\n"
                "Nguồn\n" + "\n".join(sources)
            )
        if request.intent == "sales_decline" and evidence:
            delta, days = by_metric["monthly_sold_delta"], by_metric["days_since_previous"]
            return f"Proxy lượt bán thay đổi {delta.value:g} {delta.unit} trong {days.value:g} ngày [{delta.evidence_id}] [{days.evidence_id}]. Đây là chênh lệch snapshot, không phải bằng chứng nhân quả."
        if request.intent == "similar_product" and evidence:
            parts = [f"{e.attrs['product_name']} (điểm {e.value:g}) [{e.evidence_id}]" for e in evidence]
            return "Các listing tương tự gần nhất theo lexical/embedding: " + "; ".join(parts) + ". Điểm chỉ dùng để xếp hạng tương đồng; không khẳng định cùng mẫu hoặc cùng SKU."
        if request.intent == "promotion_effectiveness" and evidence:
            values = "; ".join(f"{e.metric}={e.value:g} {e.unit} [{e.evidence_id}]" for e in evidence)
            return f"So sánh quan sát tại một snapshot: {values}. Đây là tương quan nhóm, không chứng minh khuyến mãi gây ra thay đổi."
        if request.intent == "voucher_profile_rank" and evidence:
            shop = by_metric["top_voucher_profile_shop_name"]
            score = by_metric["voucher_profile_score"]
            rate = by_metric["voucher_rate"]
            ratio = by_metric["median_discount_ratio"]
            gap = by_metric["descriptive_gap_median_sold"]
            count = by_metric["ranked_shop_count"]
            return (
                f"Hồ sơ voucher theo các thành phần điểm mô tả (voucher_profile_rank_v1): "
                f"shop dẫn đầu là {shop.value} [{shop.evidence_id}] với điểm tổng hợp {score.value:g} [{score.evidence_id}] "
                f"trên {count.value:g} shop đủ điều kiện [{count.evidence_id}]. "
                f"Thành phần: tỷ lệ listing có structured voucher {rate.value:g} [{rate.evidence_id}]; "
                f"median voucher_discount/price {ratio.value:g} [{ratio.evidence_id}]; "
                f"chênh lệch mô tả median sold proxy giữa nhóm có/không voucher trong cùng shop "
                f"{gap.value:g} {gap.unit} [{gap.evidence_id}]. "
                f"Giới hạn: ranking mô tả theo định nghĩa voucher_profile_rank_v1, không đo hiệu quả nhân quả; "
                f"hai nhóm listing khác cơ cấu ngành hàng/giá; dữ liệu tại một snapshot, proxy ước tính."
            )
        if request.intent in {"analytical_query", "open_analytical"} and evidence:
            if "highest_revenue_proxy_date" in by_metric:
                date_evidence = by_metric["highest_revenue_proxy_date"]
                revenue = by_metric["estimated_recent_revenue"]
                result = (
                    f"Ngày có doanh thu proxy ước tính cao nhất là {date_evidence.value} "
                    f"[{date_evidence.evidence_id}], với tổng {revenue.value:.0f} {revenue.unit} "
                    f"[{revenue.evidence_id}]."
                )
                method = "Cộng price × monthly_sold của các listing hợp lệ trong từng snapshot, sau đó xếp hạng giảm dần."
                limitation = (
                    "Đây là doanh thu proxy ước tính tại snapshot, không phải doanh thu thực phát sinh riêng trong ngày. "
                    "monthly_sold là số hiển thị có cửa sổ chưa được xác nhận."
                )
                scope_evidence = revenue
            elif "listing_count" in by_metric:
                count = by_metric["listing_count"]
                if "shop_name" in by_metric:
                    shop = by_metric["shop_name"]
                    result = (
                        f"Shop có nhiều listing nhất là {shop.value} [{shop.evidence_id}], "
                        f"với {count.value:g} listing [{count.evidence_id}]."
                    )
                    method = (
                        "Lọc thị trường và snapshot, join Shop bằng country_code + shop_id, "
                        "đếm distinct product_listing_key theo shop rồi xếp hạng giảm dần."
                    )
                    limitation = "shop_info là latest/static enrichment; kết quả đếm ở cấp listing, không phải SKU."
                else:
                    result = f"Có {count.value:g} listing [{count.evidence_id}] trong phạm vi đã chọn."
                    method = "Lọc đúng thị trường và snapshot, sau đó đếm distinct product_listing_key."
                    limitation = "Đây là số listing, không phải số SKU và không phải số dòng snapshot."
                scope_evidence = count
            elif "product_name" in by_metric and ({"price", "monthly_sold"} & by_metric.keys()):
                product = by_metric["product_name"]
                metric = by_metric.get("price") or by_metric["monthly_sold"]
                label = "giá cao nhất" if metric.metric == "price" else "monthly_sold cao nhất"
                formatted_value = f"{metric.value:.0f}" if metric.metric == "price" else f"{metric.value:g}"
                result = (
                    f"Listing có {label} là {product.value} [{product.evidence_id}], "
                    f"với giá trị {formatted_value} {metric.unit} [{metric.evidence_id}]."
                )
                method = "Lọc thị trường và snapshot mới nhất, loại giá trị không hợp lệ rồi xếp hạng giảm dần."
                limitation = (
                    "Kết quả ở cấp listing, không phải SKU. monthly_sold là proxy hiển thị với cửa sổ chưa xác nhận."
                    if metric.metric == "monthly_sold" else
                    "Kết quả ở cấp listing; giá sentinel và giá không hợp lệ đã bị loại trước khi xếp hạng."
                )
                scope_evidence = metric
            else:
                rows: dict[int, list[Evidence]] = {}
                for item in evidence:
                    rows.setdefault(int(item.attrs.get("row_index", 0)), []).append(item)
                lines = []
                for items in rows.values():
                    lines.append("- " + "; ".join(
                        f"{item.metric}={item.value} {item.unit or ''} [{item.evidence_id}]".strip()
                        for item in items
                    ))
                scope_evidence = evidence[0]
                return (
                    "Kết quả\n" + "\n".join(lines) + "\n\n"
                    f"Phạm vi\nThị trường {str(scope_evidence.attrs.get('country', 'unknown')).upper()}, "
                    f"snapshot {scope_evidence.attrs.get('observed_date', 'không xác định')}.\n\n"
                    "Cách tính\nLogicalQueryPlan đã qua deterministic validator và compiler read-only.\n\n"
                    "Giới hạn\nKết quả chỉ phản ánh các semantic object được catalog expose.\n\n"
                    "Độ tin cậy\nMedium — phản ánh mức đầy đủ và nhất quán của evidence, không phải xác suất đúng."
                )
            return (
                f"Kết quả\n{result}\n\n"
                f"Phạm vi\nThị trường {scope_evidence.attrs['country'].upper()}, snapshot {scope_evidence.attrs['observed_date']}.\n\n"
                f"Cách tính\n{method}\n\n"
                f"Giới hạn\n{limitation}\n\n"
                "Độ tin cậy\nMedium — phản ánh mức đầy đủ và nhất quán của evidence, không phải xác suất đúng."
            )
        return "Không đủ evidence đã kiểm chứng để trả lời."

    @staticmethod
    def _claims_for_answer(answer: str, evidence: list[Evidence]) -> tuple[ResponseClaim, ...]:
        segments = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", answer) if part.strip()]
        claims: list[ResponseClaim] = []
        for item in evidence:
            segment = next((part for part in segments if f"[{item.evidence_id}]" in part), None)
            if segment is None:
                continue
            unit = item.unit
            if isinstance(item.value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", item.value):
                claim_type = "date"
            elif item.source_tier != "btc_dataset":
                claim_type = "context"
            elif unit in {"VND", "IDR", "USD"}:
                claim_type = "money"
            elif unit in {"%", "percent", "percentage_point"}:
                claim_type = "percent"
            elif isinstance(item.value, (int, float)) and not isinstance(item.value, bool):
                claim_type = "count"
            else:
                claim_type = "text"
            claims.append(ResponseClaim(
                claim_id=f"cl:{len(claims) + 1:04d}", text=segment,
                claim_type=claim_type, value=item.value if item.value is not None else "null",
                unit=unit, evidence_id=item.evidence_id, evidence_path="value",
            ))
        return tuple(claims)

    def _generate(self, decision: GateDecision, request: StructuredRequest, evidence: list[Evidence], llm_meta: dict[str, Any]) -> tuple[str, tuple[ResponseClaim, ...], dict]:
        deterministic = self._deterministic_answer(decision, request, evidence)
        deterministic_claims = self._claims_for_answer(deterministic, evidence)
        if decision.action != "allow" or not (self.use_llm_generation and self.llm_client):
            return deterministic, deterministic_claims, {"attempts": 0, "fallback": False}
        # Caveats từ metric registry là phần bắt buộc của payload (V2 mục 5.1),
        # không phải tùy chọn của generator — đưa thẳng vào context.
        from gladiators.domain.metrics import METRICS
        caveats = sorted({
            caveat for item in evidence
            if (spec := METRICS.get(item.metric)) is not None for caveat in spec.caveats
        })
        context = {
            "request": request.model_dump(), "gate": decision.model_dump(),
            "evidence": [e.model_dump(mode="json") for e in evidence],
            "caveats": caveats,
            "rules": [
                "Chỉ dùng số trong evidence", "Gắn evidence_id ngay sau claim",
                "Không khẳng định nhân quả (cấm 'gây ra/làm tăng/làm giảm/tác động')",
                "Không dự báo/forecast", "Doanh thu proxy luôn kèm chữ 'ước tính'",
                "Kết quả ở cấp listing, không phải SKU; cấm 'cùng mẫu/cùng SKU'",
                "Giữ nguyên các caveat trong trường caveats khi diễn giải",
                "Nếu có hai tier, trình bày thành các section/claim riêng; cấm tính toán hoặc suy ra nhân quả xuyên tier",
            ],
            "deterministic_answer": deterministic,
        }
        errors = []
        for attempt in range(2):
            try:
                answer = self.llm_client.generate(context)
                answer_claims = self._claims_for_answer(answer, evidence)
                verdict = verify_numeric_claims(
                    answer, evidence, claims=answer_claims, require_claims=True,
                )
                wording_violations = check_wording(answer)
                if verdict["passed"] and not wording_violations:
                    return answer, answer_claims, {"attempts": attempt + 1, "fallback": False}
                errors.append({
                    "type": "verification",
                    "unsupported": verdict["unsupported"],
                    "unknown_citations": verdict.get("unknown_citations", []),
                    "tier_mixing": verdict.get("tier_mixing", []),
                    "provenance_gaps": verdict.get("provenance_gaps", []),
                    "source_label_gaps": verdict.get("source_label_gaps", []),
                    "claim_binding_gaps": verdict.get("claim_binding_gaps", []),
                    "wording": wording_violations,
                })
                context["verifier_feedback"] = errors[-1]
            except (ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
                errors.append({"type": type(exc).__name__})
        return deterministic, deterministic_claims, {"attempts": 2, "fallback": True, "errors": errors}

    def run(self, user_text: str) -> AgentResponse:
        trace_id = uuid.uuid4().hex[:12]
        seq = 0

        def evidence_id() -> str:
            nonlocal seq
            seq += 1
            return f"ev:{trace_id}:{seq:04d}"

        request, llm_meta = self._parse(user_text)
        capabilities = {
            **self.repo.capability_profile(),
            "live_search_enabled": self.enable_live_search,
        }
        decision = self.gate.decide(request, self.registry, capabilities) if self.enable_gate else GateDecision(action="allow", rule_id="ABLATION-NO-GATE", reason="Gate disabled for ablation.")
        if (
            decision.action == "allow" and request.intent == "voucher_profile_rank"
            and not self.enable_voucher_profile
        ):
            # T-11: weights của voucher_profile_rank_v1 chưa được DR1/Lead phê duyệt
            # → clarify theo đúng nhánh A19-METRIC của V2 §2.8, không bịa metric.
            decision = GateDecision(
                action="clarify", rule_id="A19-METRIC",
                reason=(
                    "'hiệu quả voucher' chưa có định nghĩa metric được duyệt để phục vụ. "
                    "Hệ thống có thể trả descriptive multi-signal ranking theo voucher_profile_rank_v1 "
                    "(tỷ lệ listing có structured voucher; median voucher_discount/price; "
                    "chênh lệch mô tả sold proxy giữa nhóm có/không voucher trong cùng shop) "
                    "sau khi định nghĩa được phê duyệt — không đo hiệu quả nhân quả."
                ),
            )
        evidence: list[Evidence] = []
        calls: list[ToolCall] = []
        resolved_key = None
        planning_meta: dict[str, Any] = {"mode": "none"}
        if decision.rule_id.startswith("A19") or decision.rule_id == "A-ANALYTICAL-AMBIGUITY":
            planning_meta = {"mode": "blocked", "a19_rule": decision.rule_id}
        tools = AnalyticsTools(self.repo, self.resolver, evidence_id)

        def execute_external() -> tuple[list[Evidence], ToolCall, dict[str, Any], str | None]:
            purpose = request.external_purpose or str(request.slots.get("external_purpose", "market_event"))
            market = request.country or "global"
            try:
                outcome = self.external_pipeline.run(
                    user_text, purpose=purpose, market=market,
                    evidence_id=evidence_id, dataset_version=self.repo.dataset_version,
                )
                external_evidence = list(outcome.evidence)
                call = ToolCall(
                    name="live_search_context",
                    args={
                        "purpose": purpose, "market": market,
                        "plan_id": outcome.plan_id, "cache_hits": outcome.cache_hits,
                        "provider_calls": outcome.provider_calls,
                        "quarantined_count": outcome.quarantined_count,
                        "excluded_count": outcome.excluded_count,
                        "prefiltered_count": outcome.prefiltered_count,
                    },
                    status="ok" if external_evidence else "empty",
                    evidence_ids=[item.evidence_id for item in external_evidence],
                    error=outcome.ladder_reason if not external_evidence else None,
                )
                meta = {
                    "plan_id": outcome.plan_id,
                    "execution_mode": getattr(self.external_pipeline, "mode", "unknown"),
                    "failed_queries": list(outcome.failed_queries),
                }
                return external_evidence, call, meta, outcome.ladder_reason
            except Exception as exc:
                return [], ToolCall(
                    name="live_search_context", args={"purpose": purpose, "market": market},
                    status="error", error=f"{type(exc).__name__}: external pipeline failed closed",
                ), {"outcome": "blocked"}, f"Nguồn ngoài không khả dụng ({type(exc).__name__})"

        if decision.action == "allow" and request.intent == "external_context":
            evidence, call, external_meta, external_reason = execute_external()
            calls.append(call)
            planning_meta = {"mode": "external_context", **external_meta}
            if not evidence:
                decision = GateDecision(
                    action="abstain", rule_id="A15-EXTERNAL-UNUSABLE",
                    reason=external_reason or "Không có external evidence qua admission.",
                    answerable_alternative="Hãy thử lại khi cache/nguồn ngoài khả dụng; dataset nội bộ không chứa bối cảnh này.",
                )

        # Generic dispatch: đọc tool_plan từ Intent Registry rồi gọi tool theo tên,
        # không còn nhánh if/elif cứng theo từng intent (V2 mục 7.3).
        if decision.action == "allow" and request.intent != "external_context":
            spec = self.registry.get(request.intent)
            macro = self.macros.get(spec.macro_name) if spec and spec.macro_name else None
            logical_plan = None
            if request.intent in {"analytical_query", "open_analytical"}:
                try:
                    analytical_kind = request.slots.get("analytical_kind", "")
                    planner_result = None
                    if request.intent == "open_analytical":
                        analytical_request = AnalyticalRequest.model_validate(request.analytical)
                        try:
                            planner_result = self.open_planner.plan(user_text, analytical_request, request.country)
                        except OpenPlannerError as exc:
                            raise AnalyticalPlanError(str(exc)) from exc
                        logical_plan = planner_result.plan
                    else:
                        logical_plan = build_analytical_plan(analytical_kind, request.country)
                    complexity_level = (
                        classify_complexity(analytical_request)
                        if request.intent == "open_analytical"
                        else "L3" if analytical_kind == "top_shop_by_listing_count" else "L2"
                    )
                    risk = score_plan(
                        logical_plan, complexity_level=complexity_level,
                        config=EscalationConfig(
                            enable_critic=self.enable_critic, enable_nversion=self.enable_nversion,
                        ),
                    )
                    planning_meta = {
                        "mode": planner_result.mode if planner_result else "deterministic_template",
                        "plan_id": logical_plan.plan_id,
                        "ir_version": logical_plan.ir_version, "complexity_level": complexity_level,
                        "risk_score": risk.score, "requested_escalation": risk.requested_mode,
                        "escalation_mode": risk.effective_mode,
                        "risk_factors": [factor.__dict__ for factor in risk.factors],
                    }
                    if planner_result:
                        planning_meta.update(
                            planner_attempts=planner_result.attempts,
                            validator_feedback=list(planner_result.feedback),
                            catalog_slice_size=len(planner_result.catalog_refs),
                        )
                    if not risk.allowed:
                        raise AnalyticalPlanError(risk.reason)
                    if risk.effective_mode == "nversion":
                        if request.intent != "open_analytical":
                            raise AnalyticalPlanError("N-version chỉ nhận AnalyticalRequest thuộc open analytical path.")
                        try:
                            consensus = self.nversion.resolve(
                                user_text, analytical_request, request.country, logical_plan,
                            )
                        except ConsensusError as exc:
                            raise AnalyticalPlanError(str(exc)) from exc
                        logical_plan = consensus.plan
                        planning_meta["nversion"] = {
                            "selected": consensus.selected,
                            "plan_disagreement": consensus.plan_disagreement,
                            "result_disagreement": consensus.result_disagreement,
                            "adjudicated": consensus.adjudicated,
                            "alternate_attempts": consensus.alternate_attempts,
                            "reason": consensus.reason,
                        }
                    elif risk.effective_mode == "critic":
                        try:
                            critique = self.plan_critic.review(user_text, logical_plan)
                        except RuntimeError as exc:
                            raise AnalyticalPlanError(str(exc)) from exc
                        planning_meta["critic"] = {
                            "provider": getattr(self.plan_critic.llm_client, "provider", "unavailable"),
                            "issues": [issue.model_dump() for issue in critique.issues],
                        }
                        if critique.dropped:
                            # Issue LLM báo nhưng máy chứng minh được là sai (cq03) —
                            # ghi trace, không cho phép chặn plan đúng.
                            planning_meta["critic"]["dropped"] = [
                                issue.model_dump() for issue in critique.dropped
                            ]
                        if critique.issues:
                            details = "; ".join(f"{issue.code}: {issue.message}" for issue in critique.issues)
                            raise AnalyticalPlanError(f"Plan Critic từ chối plan: {details}")
                    tool_plan = spec.tool_plan
                except AnalyticalPlanError as exc:
                    decision = GateDecision(action="abstain", rule_id="A19-PLAN", reason=str(exc))
                    if planning_meta.get("mode") == "none":
                        planning_meta["mode"] = "blocked"
                    planning_meta.update(
                        outcome="blocked", a19_rule="A19-PLAN", reason=str(exc),
                    )
                    tool_plan = ()
            elif macro is None:
                decision = GateDecision(action="abstain", rule_id="A19-PLAN", reason="Intent chưa có certified macro hợp lệ.")
                tool_plan = ()
            else:
                tool_plan = macro.tool_plan
                planning_meta = {
                    "mode": "certified_macro", "macro": macro.name,
                    "macro_version": macro.version, "ir_version": macro.plan_template.ir_version,
                    "plan_hash": macro.plan_hash,
                }
            ctx = ToolContext(request=request, tools=tools, resolver=self.resolver, logical_plan=logical_plan)
            dispatch(tool_plan, ctx)
            evidence, resolved_key = ctx.evidence, ctx.resolved_listing_key
            calls.extend(ctx.calls)
            if ctx.clarify is not None:
                decision = ctx.clarify
            elif macro and evidence and not macro.accepts_evidence([item.metric for item in evidence]):
                evidence = []
                decision = GateDecision(
                    action="abstain", rule_id="A-MACRO-EVIDENCE-CONTRACT",
                    reason="Evidence do macro tạo ra không khớp certified evidence contract.",
                )
            elif decision.action == "allow" and not evidence and self.enable_gate:
                decision = GateDecision(action="abstain", rule_id="A-NO-EVIDENCE", reason="Tool không tạo được evidence đủ điều kiện từ artifact hiện tại.")

        # Hybrid always preserves the completed internal path. External failure
        # becomes an explicit limitation rather than an all-or-nothing abstain.
        if decision.action == "allow" and request.route_mode == "hybrid" and evidence:
            internal_planning = dict(planning_meta)
            if self.enable_live_search and self.external_pipeline is not None:
                external_evidence, call, external_meta, external_reason = execute_external()
                calls.append(call)
                evidence.extend(external_evidence)
                planning_meta = {
                    "mode": "hybrid", "internal": internal_planning,
                    "external": external_meta,
                }
                if not external_evidence:
                    request.slots["external_ladder_reason"] = external_reason or "Không có external evidence qua admission"
                    decision = GateDecision(
                        action="allow", rule_id="A15-INTERNAL-PARTIAL",
                        reason="Internal analytics hoàn tất; external context không khả dụng và được hạ thành limitation.",
                    )
            else:
                request.slots["external_ladder_reason"] = "`sources.live_search.enabled` đang OFF"
                planning_meta = {
                    "mode": "hybrid", "internal": internal_planning,
                    "external": {"outcome": "disabled", "rule_id": "A14-LIVE"},
                }

        answer, claims, generation_meta = self._generate(decision, request, evidence, llm_meta)
        verification = verify_numeric_claims(
            answer, evidence, claims=claims,
            require_claims=decision.action == "allow" and bool(evidence),
        ) if self.enable_verifier else {"passed": True, "coverage": None, "disabled": True}
        final_verification_failed = bool(self.enable_verifier and decision.action == "allow" and not verification["passed"])
        if final_verification_failed:
            planning_meta["final_verification_failure"] = verification
            decision = GateDecision(
                action="abstain", rule_id="A-VERIFICATION-FINAL",
                reason="Câu trả lời deterministic cuối không qua evidence/claim verification; hệ thống từ chối fail-closed.",
                answerable_alternative="Hãy thu hẹp câu hỏi hoặc kiểm tra lại artifact/evidence contract.",
            )
            answer = self._deterministic_answer(decision, request, [])
            evidence, claims = [], ()
            verification = verify_numeric_claims(answer, [], claims=(), require_claims=False)
        llm_meta["generation"] = generation_meta
        if self.llm_client and hasattr(self.llm_client, "telemetry"):
            llm_meta["telemetry"] = self.llm_client.telemetry()
        response = AgentResponse(trace_id=trace_id, request=request, gate=decision, answer=answer, evidence=evidence, claims=claims, tool_calls=calls, resolved_listing_key=resolved_key, verification=verification, llm=llm_meta, planning=planning_meta, degraded=final_verification_failed or not verification["passed"])
        self.traces.write(trace_id, {"schema_version": "v1.1", "dataset_version": self.repo.dataset_version, "response": response.model_dump()})
        return response
