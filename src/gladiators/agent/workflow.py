from __future__ import annotations

import json
import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from gladiators.analytics import AnalyticsTools
from gladiators.contracts import AgentResponse, Evidence, GateDecision, ResponseClaim, StructuredRequest, ToolCall
from gladiators.data.repository import ArtifactRepository
from gladiators.domain.capability import match, specs_from_macros
from gladiators.domain.intent_registry import default_registry
from gladiators.planner.macros import default_macro_registry
from gladiators.planner.analytical import AnalyticalPlanError, build_analytical_plan, infer_deterministic_template
from gladiators.planner.semantic_parser import AnalyticalRequest, classify_complexity
from gladiators.planner.open_planner import (
    OpenAnalyticalPlanner,
    OpenPlannerError,
    _synthesis_beats_template,
)
from gladiators.planner.shadow import ShadowObserver
from gladiators.planner.synthesizer import synthesize
from gladiators.planner.validator import validate_plan
from gladiators.planner.consensus import ConsensusError, NVersionResolver
from gladiators.planner.risk import EscalationConfig, score_plan
from gladiators.planner.critic import PlanCritic
from .embedding import BGEIndex
from .entity_resolution import EntityResolver, expected_entity_types
from .gate import ContractDrivenGate
from .parser import MultilingualIntentParser, UNSUPPORTED
from .tool_dispatch import ToolContext, dispatch
from .trace import TraceStore
from .verifier import verify_numeric_claims
from .wording import check_wording
from .alignment import (
    check_answer_alignment,
    check_question_alignment,
    check_evidence_alignment,
    check_evidence_scope_alignment,
    check_macro_shape,
    check_plan_alignment,
    plan_refs,
)
from .context import BUDGETS, ContextBundle, guarded_evidence_payload, request_digest


_METRIC_LABELS = {
    "with_voucher": "nhóm có voucher", "without_voucher": "nhóm không voucher",
    "listing_count": "số listing", "mean_monthly_sold_proxy": "lượt bán proxy trung bình",
    "median_monthly_sold_proxy": "lượt bán proxy trung vị",
    "monthly_sold_proxy": "lượt bán proxy",
}


def _metric_label(metric: str) -> str:
    """Business wording for an internal metric name (§4.7 jargon lint).

    Evidence metrics are trace vocabulary; printing them raw put strings like
    ``with_voucher_median_monthly_sold_proxy`` in front of a reader, who cannot
    act on a column name.
    """
    for prefix in ("with_voucher_", "without_voucher_"):
        if metric.startswith(prefix):
            group = _METRIC_LABELS[prefix.rstrip("_")]
            rest = _METRIC_LABELS.get(metric[len(prefix):], metric[len(prefix):])
            return f"{rest} {group}"
    return _METRIC_LABELS.get(metric, metric.replace("_", " "))


def _plan_properties(plan, request: StructuredRequest) -> dict[str, Any]:
    """Structural summary of a plan for the §4.9 plan-oracle layer.

    Deliberately shape only -- refs, aggregation, grouping, scope, output kind.
    No values: an oracle that pinned numbers here would be an answer key, and the
    point of this layer is to catch a plan that reaches a right-looking number
    the wrong way.
    """
    analytical = request.analytical or {}
    time_scope = [str(date) for date in getattr(plan, "time_scope", ()) or ()]
    aggregations = [node.aggregation for node in plan.nodes if node.aggregation]
    group_by = sorted({ref for node in plan.nodes for ref in node.group_by})
    filters = sorted({
        predicate.ref for node in plan.nodes for predicate in node.predicates
    })
    metric_refs = sorted({
        field.semantic_ref for field in plan.requested_output_shape
        if field.semantic_ref and field.semantic_ref.split(".")[0] in {"measure", "derived"}
    })
    return {
        "countries": list(request.countries),
        "date_start": time_scope[0] if time_scope else None,
        "date_end": time_scope[-1] if time_scope else None,
        "metric_refs": metric_refs,
        "aggregation": aggregations[-1] if aggregations else None,
        "group_by": group_by,
        "output_shape_kind": analytical.get("requested_output_shape"),
        "filters": filters,
        "entity_count": len(request.entities),
    }


@dataclass(frozen=True)
class ConfidenceInputs:
    evidence_count: int
    expected_field_count: int
    postconditions_passed: int
    escalation_mode: str
    truncated: bool
    tiers: frozenset[str]
    has_invariants: bool = False
    adjudicated: bool = False


def confidence_label(inputs: ConfidenceInputs) -> str:
    if inputs.tiers - {"btc_dataset"}:
        return "Low"
    if inputs.truncated:
        return "Low"
    if inputs.expected_field_count and inputs.evidence_count < inputs.expected_field_count:
        return "Low"
    if inputs.escalation_mode == "nversion" and inputs.adjudicated:
        return "Medium"
    if inputs.has_invariants and inputs.postconditions_passed == 0:
        return "Medium"
    return "High"


_CONFIDENCE_EXPLANATION = (
    "phản ánh mức đầy đủ và nhất quán của evidence, không phải xác suất đúng."
)


def _confidence_inputs(
    evidence: list[Evidence], planning_meta: dict[str, Any] | None = None,
) -> ConfidenceInputs:
    attrs = evidence[0].attrs if evidence else {}
    result_count = next(
        (item for item in evidence if item.metric == "result_count" or "result_count" in item.attrs),
        None,
    )
    planning_meta = planning_meta or {}
    nversion = planning_meta.get("nversion") or {}
    return ConfidenceInputs(
        evidence_count=len([item for item in evidence if item.metric != "result_count"]),
        expected_field_count=int(attrs.get("expected_field_count", 0) or 0),
        postconditions_passed=int(attrs.get("postconditions_passed", 0) or 0),
        escalation_mode=str(planning_meta.get("escalation_mode", "single")),
        truncated=bool(result_count and result_count.attrs.get("truncated")),
        tiers=frozenset(item.source_tier for item in evidence),
        has_invariants=bool(attrs.get("has_invariants", False)),
        adjudicated=bool(nversion.get("adjudicated", False)),
    )


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
        llm_parser_scope: str = "always",
    ):
        self.repo = ArtifactRepository(data_dir)
        self.registry = default_registry()
        self.macros = default_macro_registry()
        # §3.5: derived from the macro registry, never a second hand-written list.
        self.capabilities = specs_from_macros(self.macros)
        self.enable_gate, self.enable_verifier = enable_gate, enable_verifier
        self.llm_client = llm_client
        self.enable_critic = os.getenv("GLADIATORS_ENABLE_CRITIC") == "1" if enable_critic is None else enable_critic
        self.enable_nversion = os.getenv("GLADIATORS_ENABLE_NVERSION") == "1" if enable_nversion is None else enable_nversion
        self.plan_critic = PlanCritic(critic_client or llm_client)
        self.open_planner = OpenAnalyticalPlanner(llm_client)
        # Shadow only: observes routing/decomposition, never decides (§6.5).
        self.shadow = ShadowObserver(
            enabled=os.getenv("GLADIATORS_DISABLE_SHADOW") != "1"
        )
        self.nversion = NVersionResolver(
            self.repo, alternate_planner_client or llm_client, adjudicator_client or llm_client,
        )
        self.use_llm_parser, self.use_llm_generation = use_llm_parser, use_llm_generation
        # "always"        — gọi P1 rồi để precedence kéo field về deterministic.
        # "fallback_only" — chỉ gọi P1 khi parser deterministic KHÔNG tìm được
        #                   đường đi (``open_analytical``). Đo được ở BGK-20:
        #                   nhánh deterministic đã quyết 19/20 lần, nên với những
        #                   câu đó lời gọi P1 là 438× thời gian đổi lấy một kết
        #                   cục bị ghi đè ngay sau đó.
        if llm_parser_scope not in {"always", "fallback_only"}:
            raise ValueError(f"llm_parser_scope không hợp lệ: {llm_parser_scope}")
        self.llm_parser_scope = llm_parser_scope
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

    def _capability_serves(self, capability_id: str, request: StructuredRequest) -> bool:
        """Does this capability's contract actually cover the request (§3.5)?

        Unknown capability ids pass through: only a *certified* macro claiming a
        request it cannot serve is the failure mode here.
        """
        spec = next(
            (item for item in self.capabilities if item.capability_id == capability_id),
            None,
        )
        if spec is None:
            return True
        return match(request_digest(request), spec).eligible

    def _parser_found_a_path(self, deterministic: StructuredRequest) -> bool:
        """Parser deterministic có bám được một macro đã chứng nhận không?

        ``open_analytical`` là cách parser nói "không có template nào khớp" —
        đó chính là chỗ đáng trao quyền cho LLM. Ngược lại, một intent có macro
        thật nghĩa là đường đi đã xác định và nhãn của P1 không thêm thông tin.

        ``unsupported:*`` và ``external_context`` cố ý KHÔNG tính là "tìm được
        đường": nhánh unsupported là nơi retry/fallback của provider sống, bỏ
        lời gọi ở đó là bỏ hành vi chứ không chỉ bỏ chi phí.
        """
        intent = deterministic.intent
        if intent == "open_analytical" or intent.startswith("unsupported:"):
            return False
        if intent == "external_context" or deterministic.route_mode in {
            "external_only", "hybrid",
        }:
            return False
        if self.macros.get(intent) is None:
            return False
        # Macro chỉ nhận request thoả contract của nó (§3.5/§3.6). Thiếu slot bắt
        # buộc thì đây không phải "đường đi đã xác định".
        spec = self.registry.get(intent)
        if spec is None:
            return False
        return all(
            getattr(deterministic, slot, None) or deterministic.slots.get(slot)
            for slot in spec.required_slots
        )

    def _parse(self, user_text: str) -> tuple[StructuredRequest, dict[str, Any]]:
        meta = {"provider": "deterministic", "parse_fallback": False, "parse_attempts": 0}
        if not (self.use_llm_parser and self.llm_client):
            return self.parser.parse(user_text, self.registry), meta
        meta.update(provider=self.llm_client.provider, model=self.llm_client.model, prompt_version=self.llm_client.prompt_version)
        errors = []
        for attempt in range(2):
            meta["parse_attempts"] = attempt + 1
            try:
                # F3: the route-safety branch depends only on the deterministic
                # result and overwrites every field the LLM produced, so calling
                # the provider first buys nothing. Parsing deterministically up
                # front lets those requests skip a call whose result is
                # discarded by construction. The adjustment name is still
                # recorded, because the outcome is the same branch as before --
                # only the wasted call is gone.
                #
                # Deliberately not extended to the unsupported branch: that path
                # is where provider failures are retried, and skipping the call
                # there would remove the retry/fallback behaviour rather than
                # just its cost.
                deterministic = self.parser.parse(user_text, self.registry)
                meta["deterministic_intent"] = deterministic.intent
                if self.llm_parser_scope == "fallback_only" and self._parser_found_a_path(
                    deterministic
                ):
                    # Parser đã bám được một macro đã chứng nhận, nên bỏ lời gọi
                    # P1 ở đây.
                    #
                    # ĐÂY KHÔNG PHẢI tối ưu chi phí thuần — đo được bằng fake
                    # client đếm lời gọi: 6/7 câu giữ nguyên kết cục, 1 câu đổi.
                    # Precedence chỉ backfill country/entities khi LLM để TRỐNG;
                    # khi LLM trả country SAI thì giá trị sai đó được giữ. Bỏ
                    # lời gọi ⇒ deterministic giữ country đúng ⇒ kết cục khác.
                    # Khác biệt đó nhiều khả năng có lợi (khớp nhóm fail
                    # A-CROSS-CURRENCY-SCOPE đo được ở deepseek 60×3) nhưng chưa
                    # được chứng minh, nên scope này KHÔNG phải mặc định.
                    meta.update(
                        llm_intent=None, merge_winner="deterministic",
                        merge_reason="deterministic_macro_confident",
                        parse_adjustments=["deterministic_macro_confident"],
                        llm_parse_skipped=True,
                    )
                    return deterministic, meta
                if deterministic.route_mode in {"external_only", "hybrid"}:
                    meta.update(
                        llm_intent=None, merge_winner="deterministic",
                        merge_reason="deterministic_route_safety_precedence",
                        parse_adjustments=["deterministic_route_safety_precedence"],
                    )
                    return deterministic, meta
                parsed = self.llm_client.parse_intent(user_text, self.registry.names())
                meta["llm_intent"] = parsed.intent
                adjustments = []
                if deterministic.route_mode in {"external_only", "hybrid"} and (
                    parsed.intent != deterministic.intent or parsed.route_mode != deterministic.route_mode
                ):
                    parsed = parsed.model_copy(update={
                        "intent": deterministic.intent,
                        "country": deterministic.country,
                        "countries": deterministic.countries,
                        "entities": deterministic.entities,
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
                elif (
                    parsed.intent != deterministic.intent
                    and self.macros.get(parsed.intent) is not None
                    and not self._capability_serves(parsed.intent, deterministic)
                ):
                    # §3.5/§3.6: a macro may only take a request whose semantic
                    # contract it actually satisfies. The label P1 chose is not
                    # evidence of that -- DeepSeek labelled "Có bao nhiêu listing
                    # ở VN?" as dataset_coverage, whose certified shape cannot
                    # produce a scalar count, and the macro duly answered a
                    # different question. The matcher decides on the contract,
                    # so the check is about capability rather than about which
                    # intent names happen to be involved.
                    parsed = parsed.model_copy(update={"intent": deterministic.intent})
                    adjustments.append("capability_contract_precedence")
                elif (
                    parsed.intent != deterministic.intent
                    and deterministic.intent == "open_analytical"
                    and self.registry.get(parsed.intent) is not None
                    and not str(
                        parsed.slots.get("analytical_kind")
                        or deterministic.slots.get("analytical_kind") or ""
                    )
                ):
                    # The deterministic parser saying ``open_analytical`` means it
                    # found no certified template. An LLM label like
                    # ``analytical_query`` claims the opposite -- that a template
                    # path applies -- while naming no template, and that pair is
                    # self-contradictory: it routes to build_analytical_plan("")
                    # and dies as "no analytical template", so the open planner is
                    # never even asked. Measured on the eval corpus, this silently
                    # blocked 22 answerable questions and disguised a routing bug
                    # as a missing capability.
                    parsed = parsed.model_copy(update={"intent": deterministic.intent})
                    adjustments.append("open_analytical_precedence")
                spec = self.registry.get(parsed.intent)
                if spec:
                    updates = {}
                    if "entity_text" not in spec.required_slots and parsed.entity_text is not None:
                        updates["entity_text"] = None; adjustments.append("irrelevant_entity_removed")
                    elif "entity_text" in spec.required_slots and deterministic.entity_text and parsed.entity_text != deterministic.entity_text:
                        updates["entity_text"] = deterministic.entity_text; adjustments.append("entity_from_deterministic_parser")
                    if not parsed.country and deterministic.country:
                        updates["country"] = deterministic.country
                        updates["countries"] = deterministic.countries
                        adjustments.append("country_from_deterministic_parser")
                    if not parsed.entities and deterministic.entities:
                        updates["entities"] = deterministic.entities
                        adjustments.append("entities_from_deterministic_parser")
                    # P1 only classifies the top-level intent. Certified analytical
                    # templates and the open analytical path carry deterministic,
                    # typed payloads that P8 needs; never discard them when P1
                    # agrees with the deterministic route.
                    if parsed.intent == deterministic.intent:
                        merged_slots = {**parsed.slots, **deterministic.slots}
                        if merged_slots != parsed.slots:
                            updates["slots"] = merged_slots
                            adjustments.append("slots_from_deterministic_parser")
                    # The analytical payload is a deterministic semantic parse of
                    # the text -- measures, dimensions, filters, ranking, dates.
                    # None of that depends on which intent label P1 chose, so it
                    # must be carried even when the two parsers disagree. Gating
                    # it on agreement silently dropped the whole semantic layer
                    # whenever the model guessed a different label: "giá thấp
                    # nhất tại VN" answered offline but abstained with A19-PLAN
                    # under a provider, because the synthesizer had no request to
                    # work from.
                    if parsed.analytical is None and deterministic.analytical is not None:
                        updates["analytical"] = deterministic.analytical
                        adjustments.append("analytical_from_deterministic_parser")
                    if updates: parsed = parsed.model_copy(update=updates)
                if adjustments: meta["parse_adjustments"] = adjustments
                # F2: what the two parsers each said and which one the merge
                # kept. Without this the 438x cost of the LLM branch has no
                # record showing whether it ever changed an outcome, and W4 has
                # nothing to decide the arbitration policy from.
                intent_overridden = [
                    name for name in adjustments if name.endswith("precedence")
                    or name == "unsupported_taxonomy_normalized"
                ]
                meta["merge_winner"] = "deterministic" if intent_overridden else "llm"
                meta["merge_reason"] = (
                    intent_overridden[0] if intent_overridden
                    else "llm_intent_kept" if parsed.intent != deterministic.intent
                    else "parsers_agreed"
                )
                if self.registry.get(parsed.intent) is None and not parsed.intent.startswith("unsupported:"):
                    raise ValueError(f"Intent ngoài registry: {parsed.intent}")
                return parsed, meta
            except (ValueError, ValidationError, RuntimeError, KeyError) as exc:
                errors.append(type(exc).__name__)
        meta.update(parse_fallback=True, parse_errors=errors)
        return self.parser.parse(user_text, self.registry), meta

    @staticmethod
    def _deterministic_answer(
        decision: GateDecision,
        request: StructuredRequest,
        evidence: list[Evidence],
        confidence: ConfidenceInputs | None = None,
    ) -> str:
        partial = request.slots.get("partial_unsupported")

        def partial_limitations() -> str:
            if not isinstance(partial, (list, tuple)) or not partial:
                return ""
            from .gate import CAPABILITY_MESSAGES
            limitations = []
            for item in partial:
                if not isinstance(item, dict):
                    continue
                capability = str(item.get("capability", "unknown"))
                message = CAPABILITY_MESSAGES.get(capability)
                reason = (
                    message["missing"]
                    if message
                    else f"Không hỗ trợ phần: {item.get('text', '')}"
                )
                limitations.append(f"- {item.get('text', '')}: {reason}")
            return "\n\nChưa trả lời được\n" + "\n".join(limitations)

        if decision.action == "abstain":
            return (
                f"Không thể trả lời chắc chắn: {decision.reason} "
                f"{decision.answerable_alternative or ''}"
            ).strip() + partial_limitations()
        if decision.action == "clarify":
            return f"Cần làm rõ: {decision.reason}" + partial_limitations()
        if decision.action == "allow" and isinstance(partial, (list, tuple)) and partial:
            base_slots = dict(request.slots)
            base_slots.pop("partial_unsupported", None)
            base_slots.pop("sub_requests", None)
            base = AgentRuntime._deterministic_answer(
                decision, request.model_copy(update={"slots": base_slots}), evidence,
            )
            return base + partial_limitations()
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
        # WP-A7: giải thích quan hệ. Không evidence, nên câu chữ tuyệt đối không
        # được mang chữ số — `relation_prose` đã lọc sẵn (A7-R1).
        explanation = request.slots.get("relation_explanation")
        if request.intent == "schema_relation_explain" and explanation:
            return str(explanation)
        if request.intent == "similar_product" and evidence:
            parts = [f"{e.attrs['product_name']} (điểm {e.value:g}) [{e.evidence_id}]" for e in evidence]
            return "Các listing tương tự gần nhất theo lexical/embedding: " + "; ".join(parts) + ". Điểm chỉ dùng để xếp hạng tương đồng; không khẳng định cùng mẫu hoặc cùng SKU."
        if request.intent == "promotion_effectiveness" and evidence:
            # §4.7 jargon lint: internal metric names ("..._monthly_sold_proxy")
            # are trace vocabulary. A reader needs the group and the quantity,
            # not the column that produced it.
            values = "; ".join(
                f"{_metric_label(e.metric)}={e.value:g} {e.unit} [{e.evidence_id}]"
                for e in evidence
            )
            # §4.11: the count covers every listing, the proxy averages only the
            # ones where sold is measurable. Saying so in words, not digits --
            # the excluded count is trace data, and a bare number in the answer
            # would be read as a claim with no evidence behind it (§3.1).
            excluded = any(
                item.attrs.get("unmeasurable_excluded_count") for item in evidence
            )
            note = (
                " Số listing là toàn bộ nhóm; lượt bán proxy chỉ tính trên phần "
                "listing đo được lượt bán, phần còn lại bị loại khỏi phép trung "
                "bình/trung vị."
                if excluded else ""
            )
            return f"So sánh quan sát tại một snapshot: {values}.{note} Đây là tương quan nhóm, không chứng minh khuyến mãi gây ra thay đổi."
        if request.intent == "voucher_coverage" and evidence:
            values = "; ".join(
                f"{str(e.attrs['country']).upper()}={e.value:g} {e.unit} [{e.evidence_id}]"
                for e in evidence
            )
            return (
                "Mức độ phủ structured voucher tại snapshot mới nhất: "
                f"{values}. Đây là số listing sau khi dedupe, không phải tỷ lệ chuyển đổi."
            )
        if request.intent == "discount_bucket_observation" and evidence:
            count = by_metric["discount_bucket_listing_count"]
            sold = by_metric["discount_bucket_median_monthly_sold_proxy"]
            return (
                f"Nhóm quanh mức giảm được hỏi có {count.value:g} listing "
                f"[{count.evidence_id}] và median monthly-sold proxy {sold.value:g} "
                f"{sold.unit} [{sold.evidence_id}]. Đây là mô tả một snapshot, "
                "không chứng minh giảm giá làm tăng chuyển đổi."
            )
        if request.intent == "dataset_coverage" and evidence:
            start = by_metric["coverage_start_date"]
            end = by_metric["coverage_end_date"]
            count = by_metric["coverage_snapshot_count"]
            return (
                f"Dữ liệu nội bộ chỉ phủ từ {start.value} [{start.evidence_id}] đến "
                f"{end.value} [{end.evidence_id}], gồm {count.value:g} snapshot "
                f"[{count.evidence_id}]. Ngoài khoảng này không có quan sát nội bộ."
            )
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
            confidence_text = (
                f"{confidence_label(confidence or _confidence_inputs(evidence))} — "
                f"{_CONFIDENCE_EXPLANATION}"
            )
            # A grouped result spans several row_index values. by_metric keeps
            # only the last evidence per metric name, so the single-value
            # branches below would render row 10 of 10 as though it were the
            # whole answer -- "Có 120 listing" for a per-shop breakdown, which is
            # one arbitrary shop's count presented as the total. Route multi-row
            # results to the row renderer before any of them can match.
            multi_row = len({
                int(item.attrs.get("row_index", 0)) for item in evidence
                if item.metric != "result_count"
            }) > 1
            if not multi_row and "highest_revenue_proxy_date" in by_metric:
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
            elif not multi_row and "listing_count" in by_metric:
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
            elif not multi_row and "product_name" in by_metric and (
                {"price", "monthly_sold"} & by_metric.keys()
            ):
                product = by_metric["product_name"]
                metric = by_metric.get("price") or by_metric["monthly_sold"]
                # The superlative has to follow the plan's actual sort order.
                # It used to be hard-coded to "cao nhất", so an ascending plan
                # returned the correct minimum under a sentence claiming it was
                # the maximum -- the answer contradicted the question it answered.
                ranking = (request.analytical or {}).get("ranking") or {}
                descending = ranking.get("direction", "desc") != "asc"
                superlative = "cao nhất" if descending else "thấp nhất"
                measure_label = "giá" if metric.metric == "price" else "monthly_sold"
                label = f"{measure_label} {superlative}"
                formatted_value = f"{metric.value:.0f}" if metric.metric == "price" else f"{metric.value:g}"
                result = (
                    f"Listing có {label} là {product.value} [{product.evidence_id}], "
                    f"với giá trị {formatted_value} {metric.unit} [{metric.evidence_id}]."
                )
                method = (
                    "Lọc thị trường và snapshot, loại giá trị không hợp lệ rồi xếp hạng "
                    + ("giảm dần." if descending else "tăng dần.")
                )
                limitation = (
                    "Kết quả ở cấp listing, không phải SKU. monthly_sold là proxy hiển thị với cửa sổ chưa xác nhận."
                    if metric.metric == "monthly_sold" else
                    "Kết quả ở cấp listing; giá sentinel và giá không hợp lệ đã bị loại trước khi xếp hạng."
                )
                scope_evidence = metric
            else:
                result_count = by_metric.get("result_count")
                result_meta = result_count or next(
                    (item for item in evidence if "result_count" in item.attrs), None,
                )
                rows: dict[int, list[Evidence]] = {}
                for item in evidence:
                    if item.metric == "result_count":
                        continue
                    rows.setdefault(int(item.attrs.get("row_index", 0)), []).append(item)
                lines = []
                for items in rows.values():
                    lines.append("- " + "; ".join(
                        # "dimension" is the catalog's placeholder unit for a
                        # grouping key; printing it reads as noise next to a value.
                        f"{item.metric}={item.value}"
                        + (f" {item.unit}" if item.unit and item.unit != "dimension" else "")
                        + f" [{item.evidence_id}]"
                        for item in items
                    ))
                scope_evidence = evidence[0]
                scope = ""
                truncation = ""
                if result_meta is not None:
                    returned = int(result_meta.attrs.get("returned_rows", len(rows)))
                    total = int(
                        result_count.value if result_count is not None
                        else result_meta.attrs.get("result_count", returned)
                    )
                    scope = (
                        f" Hiển thị {returned}/{total} dòng "
                        f"[{result_meta.evidence_id}]."
                    )
                    if result_meta.attrs.get("truncated"):
                        truncation = (
                            f" Chỉ hiển thị tối đa {result_meta.attrs.get('row_limit')} dòng; "
                            "đây không phải toàn bộ tập khớp."
                        )
                return (
                    "Kết quả\n" + "\n".join(lines) + "\n\n"
                    f"Phạm vi\nThị trường {str(scope_evidence.attrs.get('country', 'unknown')).upper()}, "
                    f"snapshot {scope_evidence.attrs.get('observed_date', 'không xác định')}.{scope}\n\n"
                    "Cách tính\nTruy vấn được sinh tự động, kiểm tra ràng buộc rồi chạy ở chế độ chỉ đọc.\n\n"
                    f"Giới hạn\nKết quả chỉ phản ánh các semantic object được catalog expose.{truncation}\n\n"
                    f"Độ tin cậy\n{confidence_text}"
                )
            return (
                f"Kết quả\n{result}\n\n"
                f"Phạm vi\nThị trường {scope_evidence.attrs['country'].upper()}, snapshot {scope_evidence.attrs['observed_date']}.\n\n"
                f"Cách tính\n{method}\n\n"
                f"Giới hạn\n{limitation}\n\n"
                f"Độ tin cậy\n{confidence_text}"
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

    def _generate(
        self, decision: GateDecision, request: StructuredRequest,
        evidence: list[Evidence], llm_meta: dict[str, Any],
        planning_meta: dict[str, Any] | None = None,
    ) -> tuple[str, tuple[ResponseClaim, ...], dict]:
        deterministic = self._deterministic_answer(
            decision, request, evidence, _confidence_inputs(evidence, planning_meta),
        )
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
        evidence_payload, guard_hits = guarded_evidence_payload(evidence)
        context_payload = {
            "request": request.model_dump(), "gate": decision.model_dump(),
            "evidence": evidence_payload,
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
        bundle = ContextBundle(
            stage="generate",
            purpose="P2",
            request_digest=request_digest(request),
            plan_hash=next(
                (str(item.attrs["plan_hash"]) for item in evidence if item.attrs.get("plan_hash")),
                None,
            ),
            payload=context_payload,
            guard_hits=guard_hits,
            prompt_version=str(getattr(self.llm_client, "prompt_version", "deterministic-v1")),
            dataset_version=self.repo.dataset_version,
            budget_tokens=BUDGETS[("generate", "P2")],
        ).with_hash()
        context = bundle.payload
        context_meta = {
            "context": bundle.trace_summary(),
            "context_guard_hits": list(bundle.guard_hits),
        }
        errors = []
        for attempt in range(2):
            try:
                answer = self.llm_client.generate(context)
                answer_claims = self._claims_for_answer(answer, evidence)
                verdict = verify_numeric_claims(
                    answer, evidence, claims=answer_claims, require_claims=True,
                    ignore_texts=decision.quoted_texts,
                )
                wording_violations = check_wording(answer)
                if verdict["passed"] and not wording_violations:
                    return answer, answer_claims, {
                        "attempts": attempt + 1, "fallback": False, **context_meta,
                    }
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
        return deterministic, deterministic_claims, {
            "attempts": 2, "fallback": True, "errors": errors, **context_meta,
        }

    def run(self, user_text: str) -> AgentResponse:
        trace_id = uuid.uuid4().hex[:12]
        seq = 0

        def evidence_id() -> str:
            nonlocal seq
            seq += 1
            return f"ev:{trace_id}:{seq:04d}"

        request, llm_meta = self._parse(user_text)
        digest = request_digest(request)
        capabilities = {
            **self.repo.capability_profile(),
            "live_search_enabled": self.enable_live_search,
        }
        # §4.5.1/D3: resolve an explicitly named identifier before the gate, so
        # "does this exist" can compete with "which market did you mean".
        # Deliberately narrow -- only a code-shaped entity, never a free-text
        # description, because a name that fails to resolve is usually a
        # clarify, not a statement that the product is absent.
        # WP-A10: loại thực thể kỳ vọng, suy từ ref ĐÃ BIND (A10-R2). Dùng nó để
        # không phân giải một câu hỏi về kệ shop thành một listing — đúng thứ
        # INV-SHELF-NOT-PLATFORM-CATEGORY cấm, chỉ ở tầng phân giải.
        entity_types: tuple[str, ...] = ()
        if request.analytical:
            try:
                entity_types = expected_entity_types(
                    AnalyticalRequest.model_validate(request.analytical),
                )
            except Exception:                       # request méo thì bỏ qua, không chặn
                entity_types = ()
        entity_check = None
        if request.entity_text and any(
            str(item.get("kind")) in {"listing_key", "item_id"}
            for item in request.entities if isinstance(item, dict)
        ):
            entity_check = self.resolver.classify(
                request.entity_text, self.resolver.resolve(request.entity_text),
            )
        decision = self.gate.decide(request, self.registry, capabilities, entity_check) if self.enable_gate else GateDecision(action="allow", rule_id="ABLATION-NO-GATE", reason="Gate disabled for ablation.")
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
        # WP-A2: verdict kết nối ref được ghi KỂ CẢ khi cờ tắt — một thành phần
        # không ai đo là một thành phần không ai biết nó đúng hay sai.
        connectivity = dict(getattr(self.gate, "last_connectivity", {}) or {})
        if entity_types:
            planning_seed_entity_types = {
                "expected": list(entity_types),
                # Resolver chỉ giữ kho ứng viên LISTING, nên "lọc ứng viên" ở
                # đây là lọc nhị phân: loại kỳ vọng không phải listing thì không
                # có ứng viên hợp lệ nào để xếp hạng.
                "resolver_pool": "listing",
            }
        else:
            planning_seed_entity_types = None
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
                            plan_bundle = ContextBundle(
                                stage="plan", purpose="P8", request_digest=digest,
                                prompt_version=str(getattr(self.llm_client, "prompt_version", "deterministic-v1")),
                                dataset_version=self.repo.dataset_version,
                                budget_tokens=BUDGETS[("plan", "P8")],
                            )
                            planner_result = self.open_planner.plan(
                                user_text, analytical_request, request.country,
                                context_bundle=plan_bundle,
                            )
                        except OpenPlannerError as exc:
                            raise AnalyticalPlanError(str(exc)) from exc
                        logical_plan = planner_result.plan
                    else:
                        # Certified-kind questions skipped the synthesizer entirely,
                        # so "bao nhiêu listing tại VN ngày 01/07" still compiled to
                        # the listing_count template, which hard-codes 2026-07-03.
                        # Same rule as the open path: synthesise only where the
                        # template is known to be wrong, not merely absent.
                        synthesized = None
                        if request.analytical:
                            candidate = AnalyticalRequest.model_validate(request.analytical)
                            if _synthesis_beats_template(candidate):
                                result = synthesize(candidate, request.country)
                                if result is not None and validate_plan(result.plan).valid:
                                    synthesized = result.plan
                        logical_plan = synthesized or build_analytical_plan(
                            analytical_kind, request.country,
                        )
                        if synthesized is not None:
                            analytical_kind = f"synthesized:{analytical_kind}"
                            # A1: đường quan hệ mà plan đã đi. Một plan hai nan
                            # hoa nhìn từ ngoài giống hệt một plan không join,
                            # nên nó phải hiện trong trace.
                            synthesis_relations = getattr(result, "relations", ())
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
                    relation_edges = tuple(locals().get("synthesis_relations") or ())
                    planning_meta = {
                        "relation_path": {
                            "edges": list(relation_edges),
                            "edge_count": len(relation_edges),
                        },
                        "mode": planner_result.mode if planner_result
                        else "deterministic_synthesis" if str(logical_plan.plan_id).startswith("synth:")
                        else "deterministic_template",
                        "plan_id": logical_plan.plan_id,
                        "ir_version": logical_plan.ir_version, "complexity_level": complexity_level,
                        "risk_score": risk.score, "requested_escalation": risk.requested_mode,
                        "escalation_mode": risk.effective_mode,
                        "risk_factors": [factor.__dict__ for factor in risk.factors],
                        # §4.3: an alias the model used and we resolved is a fact
                        # about the plan, so it is reported rather than hidden.
                        "cardinality_coercions": [
                            {
                                "node_id": node.node_id,
                                "original_cardinality": node.original_cardinality,
                                "normalized_cardinality": node.expected_cardinality,
                                "cardinality_coerced": True,
                            }
                            for node in logical_plan.nodes
                            if node.original_cardinality is not None
                        ],
                    }
                    # §6.5 / §8.11: the topic gate is closed pending reviewer
                    # sign-off, so routing runs in shadow. It records what it
                    # would have selected and changes nothing -- not the plan,
                    # not the gate decision, not the answer. Running it on live
                    # traffic is the point: a component nothing calls is a
                    # component nobody is measuring.
                    planning_meta["shadow"] = self.shadow.observe(
                        user_text,
                        AnalyticalRequest.model_validate(request.analytical)
                        if request.analytical else None,
                        digest,
                        dataset_version=self.repo.dataset_version,
                        plan_refs=tuple(plan_refs(logical_plan)),
                    )
                    if planner_result:
                        planning_meta.update(
                            planner_attempts=planner_result.attempts,
                            validator_feedback=list(planner_result.feedback),
                            catalog_slice_size=len(planner_result.catalog_refs),
                        )
                        if planner_result.context:
                            planning_meta.setdefault("contexts", {})["plan"] = planner_result.context
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
                            critic_bundle = ContextBundle(
                                stage="critic", purpose="P9", request_digest=digest,
                                plan_refs=plan_refs(logical_plan),
                                plan_hash=hashlib.sha256(
                                    logical_plan.model_dump_json().encode("utf-8")
                                ).hexdigest()[:16],
                                prompt_version=str(getattr(
                                    self.plan_critic.llm_client,
                                    "prompt_version",
                                    "deterministic-v1",
                                )),
                                dataset_version=self.repo.dataset_version,
                                budget_tokens=BUDGETS[("critic", "P9")],
                            )
                            critique = self.plan_critic.review(
                                user_text, logical_plan, context_bundle=critic_bundle,
                            )
                        except RuntimeError as exc:
                            raise AnalyticalPlanError(str(exc)) from exc
                        planning_meta["critic"] = {
                            "provider": getattr(self.plan_critic.llm_client, "provider", "unavailable"),
                            "issues": [issue.model_dump() for issue in critique.issues],
                        }
                        if critique.context:
                            planning_meta.setdefault("contexts", {})["critic"] = critique.context
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
            elif request.intent == "schema_relation_explain":
                # WP-A7: intent này đọc registry quan hệ, không chạy macro và cố
                # ý KHÔNG sinh Evidence — nó không tuyên bố con số nào về dữ liệu.
                tool_plan = spec.tool_plan if spec else ()
                planning_meta = {"mode": "schema_explain"}
            elif macro is None:
                decision = GateDecision(action="abstain", rule_id="A19-PLAN", reason="Intent chưa có certified macro hợp lệ.")
                tool_plan = ()
            else:
                macro_alignment = check_macro_shape(digest, macro.certified_shape)
                if (
                    macro.name in {"sales_decline", "similar_product"}
                    and len(digest.entity_refs) > 1
                ):
                    from .alignment import AlignmentIssue, AlignmentVerdict
                    macro_alignment = AlignmentVerdict(False, (AlignmentIssue(
                        "entity_unbound",
                        "Macro hiện chỉ bind một entity; câu hỏi nêu nhiều entity.",
                        digest.entity_refs,
                        (),
                    ),))
                if macro_alignment.aligned:
                    tool_plan = macro.tool_plan
                    planning_meta = {
                        "mode": "certified_macro", "macro": macro.name,
                        "macro_version": macro.version, "ir_version": macro.plan_template.ir_version,
                        "plan_hash": macro.plan_hash,
                        "alignment": macro_alignment.as_dict(),
                    }
                else:
                    decision = GateDecision(
                        action="clarify",
                        rule_id=macro_alignment.rule_id or "A22-ALIGN-QUALIFIER",
                        reason="; ".join(item.detail for item in macro_alignment.issues),
                        answerable_alternative=(
                            "Hệ thống có thể so sánh nhóm có structured voucher với "
                            "nhóm không trong cùng thị trường và một snapshot."
                        ),
                    )
                    tool_plan = ()
                    planning_meta = {
                        "mode": "blocked",
                        "macro": macro.name,
                        "alignment": macro_alignment.as_dict(),
                    }
            if decision.action == "allow" and logical_plan is not None:
                alignment = check_plan_alignment(digest, logical_plan)
                planning_meta["semantic_refs"] = list(plan_refs(logical_plan))
                # §4.9 layer 2: the plan oracle compares structure, not prose, so
                # the structure has to be readable from the trace. ALLOW+VERIFIED
                # is not a pass if the plan itself was the wrong shape.
                planning_meta["plan_properties"] = _plan_properties(
                    logical_plan, request,
                )
                planning_meta["alignment"] = alignment.as_dict()
                if not alignment.aligned:
                    decision = GateDecision(
                        action="clarify",
                        rule_id=alignment.rule_id or "A22-ALIGN-MEASURE",
                        reason="; ".join(item.detail for item in alignment.issues),
                        answerable_alternative=(
                            "Hãy xác nhận metric, phạm vi và dạng kết quả cần trả; "
                            "hệ thống không tự thay bằng một metric khác."
                        ),
                    )
                    tool_plan = ()
            ctx = ToolContext(request=request, tools=tools, resolver=self.resolver, logical_plan=logical_plan)
            dispatch(tool_plan, ctx)
            evidence, resolved_key = ctx.evidence, ctx.resolved_listing_key
            calls.extend(ctx.calls)
            partial = request.slots.get("partial_unsupported")
            if decision.action == "allow" and evidence and isinstance(partial, (list, tuple)) and partial:
                evidence = [
                    item.model_copy(update={"attrs": {**item.attrs, "sub_id": "sr1"}})
                    for item in evidence
                ]
                decision = GateDecision(
                    action="allow",
                    rule_id="A22-ALIGN-SUBREQUEST",
                    reason="Đã trả phần có evidence; phần ngoài dữ liệu được nêu riêng.",
                )
            if ctx.clarify is not None:
                decision = ctx.clarify
            elif decision.action == "allow" and evidence and any(
                item.attrs.get("rank_tie_at_cut") for item in evidence
            ):
                # The rank cut landed inside a run of equal values, so the rows
                # returned are one arbitrary pick among several that tie. Naming
                # one of them "the highest" answers a question the user did not
                # ask -- the same reason §4.2 forbids breaking an entity tie by
                # picking the best seller, and the same reason the feasibility
                # analyzer refuses an ambiguous grain rather than choosing one.
                evidence = []
                decision = GateDecision(
                    action="abstain",
                    rule_id="A22-ALIGN-RANK-TIE",
                    reason="Nhiều nhóm cùng đạt giá trị cao nhất nên không xếp hạng được; "
                           "chọn một nhóm trong số đó sẽ là một câu trả lời tuỳ tiện.",
                    answerable_alternative="Hãy hỏi danh sách các nhóm đạt mức cao nhất, "
                                           "hoặc thêm tiêu chí phụ để phân định.",
                )
            elif decision.action == "allow" and (
                logical_plan is not None or macro is not None
            ) and evidence:
                # Macros were exempt from evidence alignment entirely, which let
                # sales_decline answer a trailing 1-day leg for a multi-day
                # question (V2 §4.4).  They get the scope/date coverage checks
                # only: the ref-level measure check does not apply, because a
                # macro may legitimately answer measure.monthly_sold with
                # derived.monthly_sold_delta.
                evidence_alignment = (
                    check_evidence_alignment(digest, evidence)
                    if logical_plan is not None
                    else check_evidence_scope_alignment(digest, evidence)
                )
                planning_meta["evidence_alignment"] = evidence_alignment.as_dict()
                if not evidence_alignment.aligned:
                    evidence = []
                    decision = GateDecision(
                        action="clarify",
                        rule_id=evidence_alignment.rule_id or "A22-ALIGN-MEASURE",
                        reason="; ".join(item.detail for item in evidence_alignment.issues),
                        answerable_alternative="Hãy thu hẹp metric và output cần nhận.",
                    )
            elif macro and evidence and not macro.accepts_evidence([item.metric for item in evidence]):
                evidence = []
                decision = GateDecision(
                    action="abstain", rule_id="A-MACRO-EVIDENCE-CONTRACT",
                    reason="Evidence do macro tạo ra không khớp certified evidence contract.",
                )
            elif (
                decision.action == "allow" and not evidence and self.enable_gate
                # A7-R2: giải thích lược đồ không có evidence THEO THIẾT KẾ. Đòi
                # evidence ở đây là đòi bằng chứng cho một câu không nói về số.
                and request.intent != "schema_relation_explain"
            ):
                decision = GateDecision(action="abstain", rule_id="A-NO-EVIDENCE", reason="Dữ liệu hiện có không đủ điều kiện để trả lời câu hỏi này.")

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

        answer, claims, generation_meta = self._generate(
            decision, request, evidence, llm_meta, planning_meta,
        )
        verification = verify_numeric_claims(
            answer, evidence, claims=claims,
            require_claims=decision.action == "allow" and bool(evidence),
            ignore_texts=decision.quoted_texts,
        ) if self.enable_verifier else {"passed": True, "coverage": None, "disabled": True}
        answer_alignment = (
            check_answer_alignment(digest, evidence, claims, answer)
            if request.intent in {"analytical_query", "open_analytical"}
            else check_answer_alignment(
                digest.model_copy(update={"requested_measures": ()}),
                evidence, claims, answer,
            )
        )
        verification["alignment"] = answer_alignment.as_dict()
        # B2/B3: constraints the question carries. Checked here because this is
        # the one point where the digest, the final evidence and the answer text
        # are all in hand. bgk13 asked *why* listings fell over 01/07→03/07;
        # they rose, and it was answered with a count -- allowed, verified,
        # "Độ tin cậy: High", because every layer was asking a different question.
        question_alignment = check_question_alignment(digest, answer, evidence)
        verification["question_alignment"] = question_alignment.as_dict()
        final_verification_failed = bool(
            self.enable_verifier
            and decision.action == "allow"
            and (
                not verification["passed"]
                or not answer_alignment.aligned
                or not question_alignment.aligned
            )
        )
        if final_verification_failed:
            planning_meta["final_verification_failure"] = verification
            if not question_alignment.aligned:
                # Naming the real problem matters here: told only that
                # verification failed, a user would rephrase and get the same
                # refusal, because the obstacle is the question's premise.
                decision = GateDecision(
                    action="clarify",
                    rule_id=question_alignment.rule_id or "A22-ALIGN-PREMISE",
                    reason="; ".join(item.detail for item in question_alignment.issues),
                    answerable_alternative=(
                        "Hệ thống có thể trình bày mức thay đổi quan sát được giữa hai "
                        "snapshot và các chỉ số biến động cùng lúc, nhưng không kết luận "
                        "nguyên nhân."
                    ),
                )
            else:
                decision = GateDecision(
                    action="abstain", rule_id="A-VERIFICATION-FINAL",
                    reason="Câu trả lời deterministic cuối không qua evidence/claim verification; hệ thống từ chối fail-closed.",
                    answerable_alternative="Hãy thu hẹp câu hỏi, ví dụ nêu rõ thị trường, ngày hoặc sản phẩm cụ thể.",
                )
            answer = self._deterministic_answer(decision, request, [])
            evidence, claims = [], ()
            verification = verify_numeric_claims(
                answer, [], claims=(), require_claims=False,
                ignore_texts=decision.quoted_texts,
            )
        llm_meta["generation"] = generation_meta
        if generation_meta.get("context_guard_hits"):
            llm_meta["context_guard_hits"] = generation_meta["context_guard_hits"]
        if self.llm_client and hasattr(self.llm_client, "telemetry"):
            llm_meta["telemetry"] = self.llm_client.telemetry()
        context_meta = generation_meta.get("context")
        response_context = dict(planning_meta.get("contexts", {}))
        if context_meta:
            response_context["generate"] = context_meta
        # Verdict shadow phải sống sót qua MỌI nhánh: planning_meta bị gán đè ở
        # nhánh macro và nhánh analytical, nên gộp ở đây, ngay trước khi dựng
        # response. Một thành phần chạy shadow mà verdict biến mất thì nó không
        # còn được đo.
        if connectivity:
            planning_meta.setdefault("connectivity", connectivity)
        if planning_seed_entity_types:
            planning_meta.setdefault("entity_type_constraint", planning_seed_entity_types)
        response = AgentResponse(trace_id=trace_id, request=request, gate=decision, answer=answer, evidence=evidence, claims=claims, tool_calls=calls, resolved_listing_key=resolved_key, verification=verification, llm=llm_meta, planning=planning_meta, context=response_context, degraded=final_verification_failed or not verification["passed"])
        self.traces.write(trace_id, {"schema_version": "v1.1", "dataset_version": self.repo.dataset_version, "response": response.model_dump()})
        return response
