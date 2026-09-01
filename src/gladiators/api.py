from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from gladiators.contracts import AgentResponse
from gladiators.insights.api import router as insights_router
from gladiators.runtime_factory import create_runtime
from gladiators.ui import MVP_UI
from gladiators.ui_flow import FLOW_UI


class AskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    # WP-A3. Không truyền session_id ⇒ hành vi cũ TỪNG BIT (A3-R3): bộ nhớ hội
    # thoại là thứ caller phải chọn dùng, không phải thứ bật sẵn cho mọi lời gọi.
    session_id: str | None = Field(default=None, max_length=128)
    reset: bool = False
    # W32 — bật tầng LLM ánh xạ CHỮ cho đúng lời gọi này. Mặc định TẮT, vì đo
    # được nó chỉ đúng ~4/6 và KHÔNG ổn định (lặp cùng input ra hai kết quả).
    # Nó chỉ ĐỀ XUẤT: ref trả về được kiểm lại trên chính danh sách đã gửi, nên
    # một ref bịa không thể tới plan.
    llm_terms: bool = False
    # Bẻ câu bằng LLM. Tách khỏi `llm_terms` vì hai thứ khác nhau: cái kia
    # ánh xạ CHỮ, cái này bẻ CÂU. Bật một cái không kéo theo cái kia.
    llm_plan: bool = False


app = FastAPI(title="Gladiators V2", version="2.0.0-alpha")
runtime = create_runtime()

# §12.4: the insight mart is served read-only from a pinned sidecar bundle. It
# shares this app rather than standing up a second AgentRuntime.
app.include_router(insights_router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def ui() -> str:
    return MVP_UI


@app.get("/flow", response_class=HTMLResponse, include_in_schema=False)
def ui_flow() -> str:
    return FLOW_UI


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok", "dataset_version": runtime.repo.dataset_version,
        "provider": runtime.llm_client.provider if runtime.llm_client else "offline",
        "live_search_enabled": runtime.enable_live_search,
    }


@app.get("/ledger", response_class=HTMLResponse, include_in_schema=False)
def ledger_page() -> str:
    """WP-B11.3 — vòng bảo trì CÓ NGƯỜI DUYỆT, không phải hệ tự học."""
    from gladiators.ui_ledger import render

    return render()


class LedgerDecision(BaseModel):
    surface: str = Field(min_length=1, max_length=200)
    ref: str = Field(min_length=1, max_length=120)
    approved_by: str = Field(default="", max_length=120)
    decision: str = "reject"
    occurrences: int = 0


@app.post("/ledger/decision")
def ledger_decision(body: LedgerDecision) -> dict:
    """Ghi một quyết định. B11-R1: không có nhánh nào tự áp dụng."""
    from gladiators.domain.alias_index import AliasOverlayError
    from gladiators.ui_ledger import accept

    if body.decision != "accept":
        # Từ chối KHÔNG ghi gì: một danh sách "đã từ chối" sẽ được đọc như một
        # danh sách "đã xử lý", và cụm đó phải quay lại bảng ở lần chạy sau.
        return {"applied": False, "decision": body.decision}
    try:
        entry = accept(
            body.surface, body.ref, body.approved_by, occurrences=body.occurrences,
        )
    except AliasOverlayError as exc:
        raise HTTPException(
            status_code=400, detail={"code": "OVERLAY_REJECTED", "reason": str(exc)},
        ) from exc
    return {"applied": True, "entry": entry}


@app.get("/trace/{trace_id}.json")
def trace_json(trace_id: str) -> dict:
    """WP-B9 — cùng một nguồn cho trang, slide và test."""
    from gladiators.ui_trace import TraceNotFound, load_trace, trace_summary

    try:
        return trace_summary(load_trace(trace_id))
    except TraceNotFound:
        # Id sai định dạng và file không tồn tại đều là 404: phân biệt hai thứ đó
        # trong phản hồi là nói cho người gọi biết trace nào CÓ tồn tại.
        raise HTTPException(status_code=404, detail={"code": "TRACE_NOT_FOUND"}) from None


@app.get("/trace/{trace_id}", response_class=HTMLResponse, include_in_schema=False)
def trace_page(trace_id: str) -> str:
    """WP-B9 — "làm sao tôi biết số này không phải bịa?" trả lời bằng màn hình."""
    from gladiators.ui_trace import TraceNotFound, load_trace, render

    try:
        return render(load_trace(trace_id))
    except TraceNotFound:
        raise HTTPException(status_code=404, detail={"code": "TRACE_NOT_FOUND"}) from None


@app.get("/capability-map", response_class=HTMLResponse, include_in_schema=False)
def capability_map_page() -> str:
    """WP-B8 — biết hệ làm được gì TRƯỚC khi bị từ chối."""
    from gladiators.ui_capability import render

    return render()


@app.get("/capability-map.json")
def capability_map_json() -> dict:
    """Cùng một nguồn cho trang, slide và test."""
    from gladiators.ui_capability import capability_map

    return capability_map()


@app.get("/capabilities")
def capabilities() -> dict:
    return {
        "intents": runtime.registry.names(),
        "certified_macros": runtime.macros.names(),
        "analytical_templates": (
            "highest_revenue_day", "listing_count",
            "highest_price_listing", "highest_monthly_sold_listing", "top_shop_by_listing_count",
            "price_change_by_date",
        ),
        "planner": {"ir_version": "1.0", "critic_enabled": runtime.enable_critic, "nversion_enabled": runtime.enable_nversion},
        "external": {
            "live_search_enabled": runtime.enable_live_search,
            "max_admission": "context_only",
            "cross_tier_conversion": False,
        },
        "data": runtime.repo.capability_profile(),
        "unsupported_policy": "clarify_or_abstain",
    }


@app.post("/session/{session_id}/reset")
def reset_session(session_id: str) -> dict[str, bool]:
    """Huỷ ngữ cảnh đang mang theo — A3 luật 2: bộ nhớ phải huỷ được.

    Trả ``cleared`` kể cả khi không có phiên nào để xoá: người dùng bấm "bỏ ngữ
    cảnh" cần biết kết quả là "không còn ngữ cảnh", không cần biết trước đó có
    hay không.
    """
    runtime.conversations.reset(session_id)
    return {"cleared": True}


@app.post("/ask", response_model=AgentResponse)
def ask(request: AskRequest) -> AgentResponse:
    if request.reset and request.session_id:
        runtime.conversations.reset(request.session_id)
    # Bật quanh MỘT lời gọi rồi trả lại nguyên trạng. Registry là biến module,
    # nên đây là trạng thái dùng chung: đúng cho một demo một người, KHÔNG đúng
    # cho nhiều người hỏi song song. Ghi rõ ở đây thay vì để người sau tự phát
    # hiện bằng một câu trả lời lẫn cờ của người khác.
    from gladiators.planner.semantic_parser import register_term_proposer

    previous = None
    if request.llm_terms and runtime.llm_client is not None:
        from gladiators.planner import semantic_parser as _sp

        previous = _sp._TERM_PROPOSER
        register_term_proposer(runtime.llm_client)
    try:
        if request.llm_plan and runtime.llm_client is not None:
            # Câu con chạy với cờ bẻ câu TẮT — `run_split` gọi thẳng
            # `runtime.run`, không quay lại đây, nên không có đệ quy.
            from gladiators.planner.question_split import run_split

            split = run_split(runtime, request.text, runtime.llm_client)
            if split.steps or split.failed:
                # CON SỐ CỦA BƯỚC GỘP PHẢI QUA VERIFIER.
                #
                # Bẻ câu rồi trả một chuỗi chữ là bỏ mất lớp kiểm cuối: mỗi số
                # hạng có evidence, còn cái TỔNG thì không — nó sinh ra sau khi
                # mọi bước đã qua verifier, nên không lớp nào chống lưng cho nó
                # và một phép cộng sai đi thẳng ra ngoài.
                #
                # `run_split` nay dựng `Evidence` cho con số đó, với
                # `parent_evidence_ids` trỏ về evidence từng bước. Chạy verifier
                # ở đây khép kín vòng: mọi số trong `conclusion` phải khớp một
                # evidence, y như đường thường.
                from gladiators.agent.verifier import verify_numeric_claims

                verification = verify_numeric_claims(
                    split.conclusion or split.declined or "",
                    list(split.evidence),
                    # Câu hỏi con được IN LẠI nguyên văn trong lời kể của
                    # `list`/`compare`, và chúng mang ngày tháng ("21/07").
                    # Đó là chữ NGƯỜI DÙNG gõ, không phải một claim về dữ liệu —
                    # đúng nghĩa `ignore_texts`. Không loại thì verifier chấm
                    # "21" và "07" là số bịa và mọi lượt kể lại đều đỏ.
                    ignore_texts=tuple(s.question for s in split.steps),
                ) if (split.conclusion or split.declined) else {"passed": True}
                return JSONResponse({
                    "mode": "llm_plan",
                    "question": request.text,
                    "combine": split.combine,
                    "conclusion": split.conclusion,
                    "declined": split.declined,
                    "failed": split.failed,
                    "verification": {
                        "passed": bool(verification.get("passed")),
                        "unsupported": verification.get("unsupported", []),
                    },
                    "evidence": [
                        {"evidence_id": item.evidence_id, "metric": item.metric,
                         "value": item.value, "unit": item.unit,
                         "parents": list(item.parent_evidence_ids)}
                        for item in split.evidence
                    ],
                    "telemetry": split.as_attrs(),
                    "steps": [
                        {"question": step.question, "action": step.action,
                         "rule_id": step.rule_id, "value": step.value,
                         "unit": step.unit, "evidence_id": step.evidence_id,
                         "answer": step.answer}
                        for step in split.steps
                    ],
                })
            # Không bẻ được, hoặc model nói "câu đã đủ đơn giản": đi tiếp đường
            # thường thay vì trả về một lời từ chối mà đường thường không có.
        return runtime.run(request.text, session_id=request.session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "AGENT_RUNTIME_ERROR", "type": type(exc).__name__}) from exc
    finally:
        if request.llm_terms and runtime.llm_client is not None:
            register_term_proposer(previous)
