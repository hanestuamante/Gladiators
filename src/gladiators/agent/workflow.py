from __future__ import annotations

import json
import os
import uuid
from typing import Any

from pydantic import ValidationError

from gladiators.analytics import AnalyticsTools
from gladiators.contracts import AgentResponse, Evidence, GateDecision, StructuredRequest, ToolCall
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
                if deterministic.intent.startswith("unsupported:") and parsed.intent != deterministic.intent:
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
        by_metric = {e.metric: e for e in evidence}
        if request.intent == "sales_decline" and evidence:
            delta, days = by_metric["monthly_sold_delta"], by_metric["days_since_previous"]
            return f"Proxy lượt bán thay đổi {delta.value:g} {delta.unit} trong {days.value:g} ngày [{delta.evidence_id}] [{days.evidence_id}]. Đây là chênh lệch snapshot, không phải bằng chứng nhân quả."
        if request.intent == "similar_product" and evidence:
            parts = [f"{e.attrs['product_name']} (điểm {e.value:g}) [{e.evidence_id}]" for e in evidence]
            return "Các listing tương tự gần nhất theo lexical/embedding: " + "; ".join(parts) + ". Điểm chỉ dùng để xếp hạng tương đồng; không khẳng định cùng mẫu hoặc cùng SKU."
        if request.intent == "promotion_effectiveness" and evidence:
            values = "; ".join(f"{e.metric}={e.value:g} {e.unit} [{e.evidence_id}]" for e in evidence)
            return f"So sánh quan sát tại một snapshot: {values}. Đây là tương quan nhóm, không chứng minh khuyến mãi gây ra thay đổi."
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

    def _generate(self, decision: GateDecision, request: StructuredRequest, evidence: list[Evidence], llm_meta: dict[str, Any]) -> tuple[str, dict]:
        deterministic = self._deterministic_answer(decision, request, evidence)
        if decision.action != "allow" or not (self.use_llm_generation and self.llm_client):
            return deterministic, {"attempts": 0, "fallback": False}
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
            ],
            "deterministic_answer": deterministic,
        }
        errors = []
        for attempt in range(2):
            try:
                answer = self.llm_client.generate(context)
                verdict = verify_numeric_claims(answer, evidence)
                wording_violations = check_wording(answer)
                if verdict["passed"] and not wording_violations:
                    return answer, {"attempts": attempt + 1, "fallback": False}
                errors.append({
                    "type": "verification",
                    "unsupported": verdict["unsupported"],
                    "unknown_citations": verdict.get("unknown_citations", []),
                    "wording": wording_violations,
                })
                context["verifier_feedback"] = errors[-1]
            except (ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
                errors.append({"type": type(exc).__name__})
        return deterministic, {"attempts": 2, "fallback": True, "errors": errors}

    def run(self, user_text: str) -> AgentResponse:
        trace_id = uuid.uuid4().hex[:12]
        seq = 0

        def evidence_id() -> str:
            nonlocal seq
            seq += 1
            return f"ev:{trace_id}:{seq:04d}"

        request, llm_meta = self._parse(user_text)
        decision = self.gate.decide(request, self.registry, self.repo.capability_profile()) if self.enable_gate else GateDecision(action="allow", rule_id="ABLATION-NO-GATE", reason="Gate disabled for ablation.")
        evidence: list[Evidence] = []
        calls: list[ToolCall] = []
        resolved_key = None
        planning_meta: dict[str, Any] = {"mode": "none"}
        if decision.rule_id.startswith("A19") or decision.rule_id == "A-ANALYTICAL-AMBIGUITY":
            planning_meta = {"mode": "blocked", "a19_rule": decision.rule_id}
        tools = AnalyticsTools(self.repo, self.resolver, evidence_id)

        # Generic dispatch: đọc tool_plan từ Intent Registry rồi gọi tool theo tên,
        # không còn nhánh if/elif cứng theo từng intent (V2 mục 7.3).
        if decision.action == "allow":
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

        answer, generation_meta = self._generate(decision, request, evidence, llm_meta)
        verification = verify_numeric_claims(answer, evidence) if self.enable_verifier else {"passed": True, "coverage": None, "disabled": True}
        llm_meta["generation"] = generation_meta
        if self.llm_client and hasattr(self.llm_client, "telemetry"):
            llm_meta["telemetry"] = self.llm_client.telemetry()
        response = AgentResponse(trace_id=trace_id, request=request, gate=decision, answer=answer, evidence=evidence, tool_calls=calls, resolved_listing_key=resolved_key, verification=verification, llm=llm_meta, planning=planning_meta, degraded=not verification["passed"])
        self.traces.write(trace_id, {"schema_version": "v1.1", "dataset_version": self.repo.dataset_version, "response": response.model_dump()})
        return response
