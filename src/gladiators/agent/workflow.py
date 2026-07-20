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
from .embedding import BGEIndex
from .entity_resolution import EntityResolver
from .gate import ContractDrivenGate
from .parser import MultilingualIntentParser, UNSUPPORTED
from .tool_dispatch import ToolContext, dispatch
from .trace import TraceStore
from .verifier import verify_numeric_claims


class AgentRuntime:
    def __init__(
        self,
        data_dir: str = "data/processed",
        trace_dir: str = "artifacts/traces",
        enable_gate: bool = True,
        enable_verifier: bool = True,
        llm_client: Any | None = None,
        use_llm_parser: bool = False,
        use_llm_generation: bool = False,
    ):
        self.repo = ArtifactRepository(data_dir)
        self.registry = default_registry()
        self.enable_gate, self.enable_verifier = enable_gate, enable_verifier
        self.llm_client = llm_client
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
            return "Các listing gần nhất theo lexical/embedding: " + "; ".join(parts) + ". Điểm chỉ dùng để xếp hạng tương đồng."
        if request.intent == "promotion_effectiveness" and evidence:
            values = "; ".join(f"{e.metric}={e.value:g} {e.unit} [{e.evidence_id}]" for e in evidence)
            return f"So sánh quan sát tại một snapshot: {values}. Đây là tương quan nhóm, không chứng minh khuyến mãi gây ra thay đổi."
        return "Không đủ evidence đã kiểm chứng để trả lời."

    def _generate(self, decision: GateDecision, request: StructuredRequest, evidence: list[Evidence], llm_meta: dict[str, Any]) -> tuple[str, dict]:
        deterministic = self._deterministic_answer(decision, request, evidence)
        if decision.action != "allow" or not (self.use_llm_generation and self.llm_client):
            return deterministic, {"attempts": 0, "fallback": False}
        context = {
            "request": request.model_dump(), "gate": decision.model_dump(),
            "evidence": [e.model_dump(mode="json") for e in evidence],
            "rules": ["Chỉ dùng số trong evidence", "Gắn evidence_id ngay sau claim", "Không khẳng định nhân quả"],
            "deterministic_answer": deterministic,
        }
        errors = []
        for attempt in range(2):
            try:
                answer = self.llm_client.generate(context)
                verdict = verify_numeric_claims(answer, evidence)
                if verdict["passed"]:
                    return answer, {"attempts": attempt + 1, "fallback": False}
                errors.append({"type": "numeric_verification", "unsupported": verdict["unsupported"]})
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
        tools = AnalyticsTools(self.repo, self.resolver, evidence_id)

        # Generic dispatch: đọc tool_plan từ Intent Registry rồi gọi tool theo tên,
        # không còn nhánh if/elif cứng theo từng intent (V2 mục 7.3).
        if decision.action == "allow":
            spec = self.registry.get(request.intent)
            ctx = ToolContext(request=request, tools=tools, resolver=self.resolver)
            dispatch(spec.tool_plan if spec else (), ctx)
            evidence, resolved_key = ctx.evidence, ctx.resolved_listing_key
            calls.extend(ctx.calls)
            if ctx.clarify is not None:
                decision = ctx.clarify
            elif not evidence and self.enable_gate:
                decision = GateDecision(action="abstain", rule_id="A-NO-EVIDENCE", reason="Tool không tạo được evidence đủ điều kiện từ artifact hiện tại.")

        answer, generation_meta = self._generate(decision, request, evidence, llm_meta)
        verification = verify_numeric_claims(answer, evidence) if self.enable_verifier else {"passed": True, "coverage": None, "disabled": True}
        llm_meta["generation"] = generation_meta
        if self.llm_client and hasattr(self.llm_client, "telemetry"):
            llm_meta["telemetry"] = self.llm_client.telemetry()
        response = AgentResponse(trace_id=trace_id, request=request, gate=decision, answer=answer, evidence=evidence, tool_calls=calls, resolved_listing_key=resolved_key, verification=verification, llm=llm_meta, degraded=not verification["passed"])
        self.traces.write(trace_id, {"schema_version": "v1.1", "dataset_version": self.repo.dataset_version, "response": response.model_dump()})
        return response
