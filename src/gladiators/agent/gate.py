from __future__ import annotations

import os

from gladiators.contracts import GateDecision, GateIssue, IssueDetail, StructuredRequest
from gladiators.domain.intent_registry import IntentRegistry
from gladiators.agent.value_probe import (
    index_is_available,
    missing_values,
    named_but_absent,
)
from gladiators.planner.feasibility import connectivity_blockers
from gladiators.planner.semantic_parser import AnalyticalRequest, classify_a19
from gladiators.external.router import classify_external_need
from gladiators.domain.absent_concepts import (
    check_registry as check_absent_concepts,
    match as absent_match,
)
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
        "Trường phân loại danh mục được hỏi chưa được mở cho truy vấn.",
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


def select_issue(issues: list[GateIssue]) -> GateIssue:
    """The issue that describes the problem, not the one that fired first.

    §4.5.1. Priority is source-call order, so the gate used to report whichever
    rule happened to be written earliest. bgk16 (a product code that is not in
    the data) and bgk14 (a profit column that does not exist) were both told to
    name a market -- an action that cannot help either one. Ranking unfixable
    ahead of fixable changes nothing for a request whose issues are all fixable,
    which is what keeps the boundary and A19 suites stable.
    """
    return min(issues, key=lambda item: (item.fixable, item.priority))


# W22-R3: tập ĐÓNG các ô mà một `clarify` có thể hỏi. CÙNG tập với
# ``scripts/run_accuracy_benchmark.py:SLOT_CUES`` — câu hỏi lại sinh TỪ Ô, không
# phải từ việc chuỗi `reason` tình cờ chứa từ khoá nào, và đó là điều làm
# `clarification_precision` đo được.
CLARIFICATION_SLOTS = frozenset({
    "country", "voucher_definition", "ranking_metric", "entity_disambiguation",
    "definition_threshold", "group_dimension", "metric", "date_scope",
    "observation_window",
})


def _asks_for_money(request) -> bool:
    """Câu hỏi có đụng tới một measure đơn vị TIỀN không?"""
    from gladiators.domain.catalog import CATALOG

    refs = {
        item.get("ref")
        for item in (request.analytical or {}).get("requested_measures", ())
        if isinstance(item, dict) and item.get("ref")
    }
    return any(
        ref in CATALOG and CATALOG[ref].unit == "local_currency" for ref in refs
    )


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

    def decide(
        self, request: StructuredRequest, registry: IntentRegistry,
        capabilities: dict[str, object],
        entity_check: object | None = None,
        uncollected: frozenset[str] | tuple[str, ...] = (),
    ) -> GateDecision:
        self.last_connectivity: dict[str, object] = {}
        self.last_value_probe: dict[str, object] = {}
        issues: list[GateIssue] = []
        # Issues that only matter if the request is refused for some other
        # reason; see the partial_unsupported block below.
        deferred: list[GateIssue] = []
        phases: list[int] = []

        uncollected_artifacts = frozenset(uncollected or ())

        def add(
            rule_id: str, phase: int, action: str, reason: str,
            category: str, code: str, alternative: str | None = None,
            refs: tuple[str, ...] = (), fixable: bool = True,
            clarification_slot: str | None = None,
        ) -> None:
            issues.append(GateIssue(
                rule_id=rule_id, phase=phase, priority=len(issues) + 1,
                action=action, reason=reason, answerable_alternative=alternative,
                detail=IssueDetail(category=category, code=code, semantic_refs=refs),
                fixable=fixable, clarification_slot=clarification_slot,
            ))

        def decide_from(fallback: GateDecision) -> GateDecision:
            """Select the highest-priority issue, or fall through to ``fallback``."""
            if not issues:
                return fallback.model_copy(update={
                    "issues": (), "selected_issue_id": None,
                    "evaluated_phases": tuple(sorted(set(phases))),
                })
            pool = issues + deferred
            chosen = select_issue(pool)
            return GateDecision(
                action="abstain" if chosen.action == "block" else chosen.action,
                rule_id=chosen.rule_id, reason=chosen.reason,
                answerable_alternative=chosen.answerable_alternative,
                issues=tuple(pool), selected_issue_id=chosen.rule_id,
                evaluated_phases=tuple(sorted(set(phases))),
                clarification_slot=chosen.clarification_slot,
            )

        # ---- phase 1: capability / out-of-scope / route --------------------
        phases.append(1)
        # D3: an identifier the dataset does not contain is a fact about the
        # data. The existence check used to live in tool_dispatch, which only
        # runs once the gate has already said allow, so a question that was also
        # missing a country never reached it and was told to name a market
        # instead -- advice that cannot make the code exist (bgk16).
        if entity_check is not None and getattr(entity_check, "state", "") in {
            "not_found", "invalid_extraction",
        }:
            add("A-ENTITY-NOT-FOUND", 1, "abstain",
                "Không tìm thấy listing nào khớp mã hoặc tên trong dữ liệu hiện có.",
                "entity", "entity_absent",
                "Hãy kiểm tra lại mã sản phẩm hoặc nêu tên đầy đủ hơn.",
                fixable=False)
        # D2: a clause the system cannot serve must reach the final decision. It
        # used to be split into partial_unsupported and only printed when the
        # *other* clause answered; when neither could, the decision described a
        # different problem entirely (bgk14 asked for profit and was told the
        # country slot was missing).
        # Only a *competitor*, never a blocker on its own: when the supported
        # clause can still be answered, the unsupported part stays a limitation
        # appended to the answer, which is the existing compound-request
        # contract. It is promoted into the decision only when something else
        # already refuses, so it can displace a fixable reason that describes
        # the wrong problem.
        for item in request.slots.get("partial_unsupported", ()) or ():
            if not isinstance(item, dict):
                continue
            missing = str(item.get("capability", ""))
            message = CAPABILITY_MESSAGES.get(missing)
            # External/reference variables are not a missing column; they are a
            # routing decision with its own A14-* chain and its own live-search
            # flag. Letting the generic capability issue displace it would
            # replace a precise reason with a vaguer one.
            if not message or missing in {"external", "reference"}:
                continue
            deferred.append(GateIssue(
                rule_id=f"A-MISSING-{missing.upper()}", phase=1, priority=1_000,
                action="abstain",
                reason=" ".join((message["missing"], message["coverage"], message["answerable"])),
                answerable_alternative=message["alternative"],
                detail=IssueDetail(category="capability", code=f"unsupported_{missing}"),
                fixable=False,
            ))
        # ── W22 (Spec3008 §9.2) — lý do từ chối CHỌN TỪ LEDGER ──────────────
        #
        # Trước W22 một câu hỏi về NPS thiếu country nhận lời khuyên "hãy chọn
        # thị trường" — một hành động KHÔNG THỂ làm cột NPS tồn tại. Lý do do
        # THỨ TỰ LUẬT quyết định, không do thứ đã chặn.
        unbound = tuple(
            (str(kind), str(text))
            for kind, text in (
                (request.analytical or {}).get("unbound_spans") or ()
            )
        )
        # Ghép các span dư LIỀN KỀ trước khi tra: "nhân viên" tới đây thành hai
        # token rời, và một registry khớp cụm mà chỉ được đưa từng từ thì không
        # bao giờ khớp cụm nào.
        texts = [text for _, text in unbound]
        for size in range(len(texts), 1, -1):
            hit = None
            for start in range(len(texts) - size + 1):
                window = " ".join(texts[start:start + size])
                if absent_match(window) is not None:
                    hit = (unbound[start][0], window)
                    break
            if hit is not None:
                unbound = (hit,) + tuple(
                    item for item in unbound if item[1] not in hit[1].split()
                )
                break
        for kind, span_text in unbound:
            concept = absent_match(span_text)
            if concept is not None:
                message = CAPABILITY_MESSAGES.get(concept.capability_key or "")
                add(
                    f"A-MISSING-{(concept.capability_key or concept.concept_id).upper()}",
                    1, "abstain",
                    " ".join((message["missing"], message["coverage"],
                              message["answerable"])) if message else concept.reason,
                    "capability", concept.refusal_class,
                    message["alternative"] if message else None,
                    fixable=False,
                )
                continue
            if kind in {"date_like", "proper_name"}:
                continue          # W20 và W19 đã có lối riêng cho hai loại này
            # ĐO ĐƯỢC, không suy đoán: bật `A-UNBOUND-CONSTRAINT` cho cả
            # `unknown_concept` và `quantity_phrase` đẩy `over_refusal_rate` từ
            # 0.344 lên 0.594 trên bộ dev — đúng bẫy Spec3008 §21.11 ("đừng để
            # nó thành cổng chặn mọi thứ"), và nghiệm thu W22 khai điều kiện
            # "over_refusal_rate KHÔNG ĐƯỢC TĂNG" chính vì rủi ro này.
            #
            # `unknown_concept` là ĐÁY của phân loại phần dư: mọi từ nội dung
            # chưa có alias rơi vào đó, gồm cả những từ hệ thừa sức bỏ qua. Chỉ
            # `grain_term` là tín hiệu ĐỦ HẸP — nó nêu một grain mà dataset khai
            # rõ là không có.
            if kind == "grain_term":
                add("A-UNBOUND-CONSTRAINT", 1, "clarify",
                    f'Chưa hiểu cụm "{span_text}" trong câu hỏi; '
                    "hãy diễn đạt lại phần đó hoặc nêu chỉ số cụ thể.",
                    "slot", "unbound_constraint",
                    clarification_slot=(
                        "definition_threshold" if kind == "quantity_phrase"
                        else "group_dimension" if kind == "grain_term" else "metric"
                    ))

        # ── W20 §7.3 — HAI luật, không phải một ────────────────────────────
        # "ngoài cửa sổ" và "trong kỳ nhưng không có đợt thu" cần hai lời khuyên
        # khác nhau: cái đầu không có đợt thu nào ở gần, cái sau thì các ngày
        # LÂN CẬN có dữ liệu. KHÔNG chữ số trong message (W20-R2).
        _dates = (request.analytical or {}).get("date_request") or {}
        if _dates.get("out_of_window"):
            add("A-SNAPSHOT-SCOPE", 3, "abstain",
                "Dữ liệu nội bộ chỉ quan sát trong một cửa sổ ngắn; ngày được "
                "hỏi nằm ngoài cửa sổ đó nên không có quan sát nào để trả lời. "
                "Có thể hỏi lại trong phạm vi các đợt thu đã có.",
                "scope", "date_out_of_range", fixable=False)
        elif _dates.get("missing_snapshot"):
            add("A-SNAPSHOT-GAP", 3, "abstain",
                "Ngày được hỏi nằm trong kỳ thu thập nhưng không có đợt thu nào "
                "rơi đúng vào ngày đó, nên không có quan sát để trả lời. Các "
                "ngày liền kề có dữ liệu.",
                "scope", "date_out_of_range", fixable=False)

        # ── W31 §18.2 — "chưa thu" KHÁC "không bao giờ có" ─────────────────
        # `A-MISSING-ADS` nói *sàn không cấp dữ liệu quảng cáo*;
        # `A-ARTIFACT-NOT-COLLECTED` nói *lần thu này chưa lấy*. Lời khuyên khác
        # nhau: một cái là "đừng hỏi nữa", cái kia là "thu thêm thì hỏi được".
        # Kiểm ở GATE vì gate biết ref nào được yêu cầu và bản dữ liệu nào đang
        # phục vụ — nó không cần plan. Guard ở compiler GIỮ NGUYÊN làm phòng
        # tuyến thứ hai (nó bắt cả plan do LLM sinh).
        if uncollected_artifacts:
            from gladiators.domain.catalog import CATALOG

            wanted = {
                item.get("ref")
                for key in ("requested_measures", "requested_dimensions")
                for item in (request.analytical or {}).get(key, ())
                if isinstance(item, dict) and item.get("ref")
            }
            blocked = sorted({
                ref for ref in wanted
                if ref in CATALOG and CATALOG[ref].physical and all(
                    column.split(".csv")[0] + ".csv" in uncollected_artifacts
                    for column in CATALOG[ref].physical
                )
            })
            if blocked:
                add("A-ARTIFACT-NOT-COLLECTED", 1, "abstain",
                    "Chỉ số này có trong mô hình dữ liệu nhưng chưa được thu ở "
                    "bản dữ liệu đang phục vụ, nên không có quan sát nào để trả "
                    "lời.",
                    "capability", "not_collected", fixable=False)

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
        if request.intent == "unsupported:column_not_collected":
            # W8.2: registry ngữ nghĩa quan sát nói cột này KHÔNG ĐƯỢC THU THẬP
            # — khác hẳn "dataset không có khái niệm này". Lý do phải nêu đúng
            # phân biệt đó, không chữ số (CLAUDE.md §3.1).
            add("A-DATA-ABSENT", 1, "abstain",
                "Cột dữ liệu tương ứng không được thu thập trong dataset này, "
                "nên không quan sát được thứ câu hỏi cần — đây là quyết định đã "
                "được chủ dữ liệu xác nhận, không phải một khái niệm dataset "
                "thiếu.",
                "capability", "column_not_collected",
                "Hãy hỏi một chỉ số mà dataset có thu thập, ví dụ giá, đánh giá "
                "hoặc lượt bán.",
                fixable=False)
            return decide_from(GateDecision(action="allow", rule_id="A-ALLOW", reason=""))
        if request.intent.startswith("unsupported:"):
            missing = request.intent.split(":", 1)[1]
            message = CAPABILITY_MESSAGES[missing]
            add(f"A-MISSING-{missing.upper()}", 1, "abstain",
                " ".join((message["missing"], message["coverage"], message["answerable"])),
                "capability", f"unsupported_{missing}", message["alternative"],
                fixable=missing in {"external", "reference"})
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
        # W1 (SolutionSpec2808 §2.11): vòng P chạy cho CẢ analytical_query lẫn
        # open_analytical. Trước đây nó nằm trong nhánh open_analytical, nên
        # "brand Bibika" (sai chính tả) đi đường certified template được ALLOW
        # với bảng tất cả brand — đúng phép nới "không tìm thấy thì trả tất cả"
        # mà A4-R5 cấm. Lỗ này có từ trước W1; bảng test W1 đòi bịt.
        if request.intent in {"open_analytical", "analytical_query"} and request.analytical:
            analytical_request = AnalyticalRequest.model_validate(request.analytical)
            # WP-A5.1 vòng P: bản song sinh của A-ENTITY-NOT-FOUND cho GIÁ TRỊ
            # chiều. Hỏi về một thương hiệu không có trong dữ liệu phải bị chặn
            # SỚM, thay vì lập cả kế hoạch rồi hỏng ở tầng khác với một lý do mô
            # tả sai vấn đề.
            named_absent = named_but_absent(
                analytical_request.normalized_question, request.country,
                frozenset(
                    item.ref for item in analytical_request.requested_dimensions
                    if item.ref
                ),
                raw_question=str(request.slots.get("raw_text") or ""),
            )
            probed = tuple(missing_values(analytical_request)) + named_absent
            # Ghi verdict KỂ CẢ khi rỗng: một vòng lặp không bao giờ bắn trông
            # giống hệt một vòng lặp bắn mà vô ích, và chỉ telemetry phân biệt
            # được hai thứ đó.
            self.last_value_probe = {
                "missing": [list(pair) for pair in probed],
                "index_available": index_is_available(),
            }
            for value_ref, literal in probed:
                add("A-VALUE-NOT-FOUND", 3, "abstain",
                    f"Giá trị được nêu cho {value_ref.split('.')[-1]} không có "
                    "trong dữ liệu của thị trường này.",
                    "entity", "value_not_found", refs=(value_ref,),
                    # Không thông tin nào người dùng thêm vào sẽ tạo ra giá trị đó.
                    fixable=False)
        if request.intent == "analytical_query" and request.analytical:
            # W8.3: alias collision không có quyết định ưu tiên phải fail-closed
            # trên CẢ đường certified template — nếu chỉ chặn ở open_analytical,
            # "bao nhiêu listing CÓ VOUCHER" rơi về template listing_count và
            # trả 668: điều kiện mơ hồ bị bỏ trong im lặng, đúng phép nới
            # A4-R5 cấm (668 là toàn thị trường, không phải nhóm có voucher).
            # CHỈ đọc ambiguity CÓ KIỂU (alias collision) — chuỗi "Thiếu
            # country" trong field ambiguities cũ được bộ nhớ hội thoại lấp ở
            # lượt sau, và chặn nó ở đây làm hỏng chính WP-A3 (đo được:
            # "Có bao nhiêu listing?" lượt hai với country đã nhớ bị clarify).
            collisions = tuple(
                (request.analytical or {}).get("semantic_ambiguities") or ()
            )
            if collisions:
                text = "; ".join(
                    f'Cụm "{item.get("surface")}" có nhiều nghĩa; hãy nêu rõ.'
                    if isinstance(item, dict) else str(item)
                    for item in collisions
                )
                add("A-ANALYTICAL-AMBIGUITY", 2, "clarify", text,
                    "grain", "semantic_ambiguity")
        if request.intent == "open_analytical":
            if not request.analytical:
                add("A19-PLAN", 2, "abstain",
                    "Thiếu AnalyticalRequest cho open analytical path.",
                    "capability", "missing_analytical")
                return decide_from(GateDecision(action="allow", rule_id="A-ALLOW", reason=""))
            analytical_request = AnalyticalRequest.model_validate(request.analytical)
            admission = classify_a19(analytical_request)
            if admission:
                action, rule_id, reason = admission
                add(rule_id, 3, action, reason, "grain", "a19_admission")
            # WP-A2: ref không nối được với nhau bằng quan hệ đã chứng nhận thì
            # gate phải nói ĐÚNG lý do đó, thay vì để câu đi tiếp rồi hỏng ở
            # planner với A19-PLAN — một lời từ chối mô tả sai bản chất khiến
            # người dùng diễn đạt lại và nhận đúng lời từ chối đó.
            #
            # Mặc định SHADOW (A2-R1): tính blocker, ghi verdict, không đổi
            # quyết định cho tới khi đo được 0 thay đổi kết cục.
            if request.intent == "open_analytical":
                blockers = connectivity_blockers(analytical_request)
                self.last_connectivity = {
                    "blockers": list(blockers),
                    "shadow": os.getenv("GLADIATORS_ENABLE_CONNECTIVITY_GATE") != "1",
                }
                if blockers and os.getenv("GLADIATORS_ENABLE_CONNECTIVITY_GATE") == "1":
                    add("A-REFS-DISCONNECTED", 3, "abstain",
                        "Những chỉ số được hỏi không nối được với nhau bằng quan hệ "
                        "nào đã được chứng nhận, nên không có kế hoạch truy vấn hợp lệ.",
                        "fanout", "refs_disconnected",
                        refs=tuple(
                            item.split(":", 1)[1] for item in blockers
                            if item.startswith("disconnected:")
                        ),
                        # Không thông tin nào người dùng cung cấp thêm sẽ tạo ra
                        # một quan hệ trong registry.
                        fixable=False)
        # ---- phase 4: currency ---------------------------------------------
        phases.append(4)
        if request.intent == "analytical_query" and not request.country:
            # §9.3 — luật này từng bắn cho MỌI câu không có country, kể cả câu
            # đếm thuần không đụng tới tiền. Nên một câu hỏi về NPS nhận được
            # "hãy chọn thị trường để không cộng VND với IDR" — một lý do nói về
            # một vấn đề KHÔNG TỒN TẠI trong câu. Cả hai vẫn `clarify` và vẫn
            # chạm cue `country`, nên `clarification_precision` không đổi; đổi
            # là NHÓM LÝ DO, tức `refusal_reason_accuracy`.
            if _asks_for_money(request):
                add("A16-CROSS-CURRENCY", 4, "clarify",
                    "Cần chọn thị trường VN hoặc ID để không cộng/so sánh trực "
                    "tiếp VND với IDR.",
                    "currency", "cross_currency",
                    clarification_slot="country")
            else:
                add("A-MISSING-SLOT", 4, "clarify",
                    "Câu hỏi chưa nêu thị trường; hãy chọn VN hoặc ID.",
                    "slot", "missing_scope", clarification_slot="country")
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


# W22-R1: registry khái niệm vắng mặt fail ở IMPORT. Gọi ở đây vì nó cần
# `CAPABILITY_MESSAGES` của chính module này — gõ sai một khoá phải nổ lúc nạp,
# không đợi tới lúc một câu hỏi chạm vào.
check_absent_concepts()
