"""Màn hình sổ vết — Spec2308 §WP-B9.

Trả lời câu *"làm sao tôi biết số này không phải bịa?"* bằng **một màn hình bấm
được**, không bằng lời.

``TraceStore.write`` đã ghi đủ 9 chặng ra ``artifacts/traces/<trace_id>.json`` từ
lâu, kèm redact cho email / API key / bearer token. Trước WP này **không có gì
đọc lại file đó** — một bản ghi không ai đọc là một bản ghi không tồn tại.

**B9-R1 — chỉ đọc, không chạy lại.** Màn hình này đọc quá khứ; chạy lại là một
tính năng khác và sẽ cho số khác, nên nó sẽ trả lời một câu hỏi khác với câu
người dùng đang hỏi.
"""
from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any

TRACE_DIR = Path("artifacts/traces")

# B9-R3: id phải khớp regex, KHÔNG nhận đường dẫn. Ghép chuỗi vào một Path rồi
# tin vào việc nó nằm trong thư mục là cách mọi lỗi path traversal bắt đầu.
TRACE_ID = re.compile(r"^[0-9a-f]{12}$")

STAGES = (
    ("parse", "S1 · phân tích câu"),
    ("route", "S2 · định tuyến"),
    ("entity", "S3 · phân giải thực thể"),
    ("gate", "S4 · cổng kiểm trước"),
    ("plan", "S5 · lập kế hoạch"),
    ("execute", "S6 · thực thi"),
    ("generate", "S7 · sinh câu trả lời"),
    ("verify", "S8 · đối chiếu số"),
    ("gate_out", "S9 · cổng kiểm cuối"),
)


class TraceNotFound(LookupError):
    """Id không hợp lệ hoặc file không tồn tại — cả hai đều là 404, không phải 500."""


def load_trace(trace_id: str) -> dict[str, Any]:
    if not TRACE_ID.match(trace_id or ""):
        raise TraceNotFound(trace_id)
    path = TRACE_DIR / f"{trace_id}.json"
    # Kiểm lại sau khi ghép: regex đã loại ".." rồi, nhưng một phép kiểm thứ hai
    # ở đây rẻ và nó bắt được cả trường hợp TRACE_DIR bị đổi thành đường dẫn lạ.
    if not path.is_file() or path.parent.resolve() != TRACE_DIR.resolve():
        raise TraceNotFound(trace_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TraceNotFound(trace_id) from exc


def _numbers_without_claims(response: dict[str, Any]) -> list[float]:
    """Số mà VERIFIER đã chấm là không có evidence, đọc từ bản ghi.

    Đọc lại verdict đã lưu chứ KHÔNG quét lại (B9-R1). Bản quét viết tay đầu
    tiên của màn hình này báo [3.0, 1.0, 2026.0] cho một câu trả lời hoàn toàn
    hợp lệ — nó không biết verifier đã che ngày ISO và token citation trước khi
    quét. Một màn hình cảnh báo sai là một màn hình dạy người đọc bỏ qua cảnh
    báo, và nó tệ hơn không có cảnh báo nào.
    """
    verification = response.get("verification") or {}
    return [
        float(value) for value in verification.get("unsupported") or ()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]


def trace_summary(trace: dict[str, Any]) -> dict[str, Any]:
    """Ba khối mà §B9 bắt buộc, ở dạng dữ liệu — dùng chung cho trang và test."""
    response = trace.get("response") or trace
    gate = response.get("gate") or {}
    planning = response.get("planning") or {}
    evidence_by_id = {
        item.get("evidence_id"): item for item in response.get("evidence") or []
    }
    claims = [
        {
            "text": claim.get("text"),
            "value": claim.get("value"),
            "unit": claim.get("unit"),
            "evidence_id": claim.get("evidence_id"),
            "evidence_path": claim.get("evidence_path"),
            "source": (
                (evidence_by_id.get(claim.get("evidence_id")) or {})
                .get("source_locator") or {}
            ).get("value"),
            "source_path": (
                evidence_by_id.get(claim.get("evidence_id")) or {}
            ).get("source_path"),
            "dataset_version": (
                evidence_by_id.get(claim.get("evidence_id")) or {}
            ).get("dataset_version"),
        }
        for claim in response.get("claims") or []
    ]
    timing = planning.get("timing") or {}
    evaluated = tuple(gate.get("evaluated_phases") or ())
    return {
        "trace_id": response.get("trace_id"),
        "question": (response.get("request") or {}).get("raw_text")
        or ((response.get("request") or {}).get("slots") or {}).get("raw_text"),
        "answer": response.get("answer"),
        "claims": claims,
        "unbacked_numbers": _numbers_without_claims(response),
        "gate": {
            "action": gate.get("action"),
            "rule_id": gate.get("rule_id"),
            "reason": gate.get("reason"),
            # MỌI issue, không chỉ issue thắng: issue thua giải thích vì sao lời
            # từ chối này chứ không phải một lời từ chối khác.
            "issues": gate.get("issues") or [],
            "selected_issue_id": gate.get("selected_issue_id"),
            "evaluated_phases": list(evaluated),
        },
        "budget": {
            "timing_ms": timing,
            "llm_calls_critical": planning.get("llm_calls_critical"),
            "plan_cache_hit": (planning.get("plan_cache") or {}).get("hit"),
            "within_budget": (planning.get("budget") or {}).get("within"),
            "llm_telemetry": (response.get("llm") or {}).get("telemetry"),
        },
        "stages": [
            {
                "key": key, "label": label, "ms": timing.get(key),
                # Chặng KHÔNG chạy khác chặng chạy hết 0ms. Gộp hai thứ đó
                # làm một chặng bị bỏ qua trông như một chặng nhanh.
                "ran": timing.get(key) is not None,
            }
            for key, label in STAGES
        ],
    }


def render(trace: dict[str, Any]) -> str:
    data = trace_summary(trace)
    gate = data["gate"]

    claim_rows = "".join(
        "<tr>"
        f"<td>{escape(str(claim['text'] or ''))}</td>"
        f"<td class='num'>{escape(str(claim['value']))} {escape(str(claim['unit'] or ''))}</td>"
        f"<td><code>{escape(str(claim['evidence_id'] or ''))}</code></td>"
        f"<td><code>{escape(str(claim['source'] or '—'))}</code>"
        f"<br><small>{escape(str(claim['source_path'] or ''))}</small></td>"
        f"<td><small>{escape(str(claim['dataset_version'] or ''))}</small></td>"
        "</tr>"
        for claim in data["claims"]
    ) or "<tr><td colspan='5'><i>Câu trả lời này không tuyên bố con số nào.</i></td></tr>"

    warning = (
        "<p class='warn'>⚠ Số không nối được tới evidence: "
        + ", ".join(str(number) for number in data["unbacked_numbers"])
        + "</p>"
    ) if data["unbacked_numbers"] else ""

    issue_rows = "".join(
        "<tr>"
        f"<td><code>{escape(str(issue.get('rule_id') or issue.get('issue_id') or ''))}</code></td>"
        f"<td>{escape(str(issue.get('reason') or issue.get('detail') or ''))}</td>"
        f"<td>{'khắc phục được' if issue.get('fixable', True) else 'KHÔNG khắc phục được'}</td>"
        "</tr>"
        for issue in gate["issues"]
    ) or "<tr><td colspan='3'><i>Không có issue nào được ghi.</i></td></tr>"

    stage_cells = "".join(
        f"<div class='stage {'on' if stage['ran'] else 'off'}'>"
        f"<b>{escape(stage['label'])}</b><br>"
        f"<small>{stage['ms'] if stage['ran'] else '—'}{' ms' if stage['ran'] else ''}</small>"
        "</div>"
        for stage in data["stages"]
    )

    budget = data["budget"]
    return f"""<!doctype html><meta charset="utf-8">
<title>Sổ vết {escape(str(data['trace_id']))}</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:24px;max-width:1000px;line-height:1.5}}
 h1{{font-size:20px}} h2{{font-size:15px;margin-top:28px}}
 table{{border-collapse:collapse;width:100%;font-size:13px}}
 td,th{{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}}
 .num{{text-align:right;font-variant-numeric:tabular-nums}}
 .warn{{background:#fff4f4;border-left:4px solid #b42318;padding:8px 12px}}
 .flow{{display:flex;gap:6px;flex-wrap:wrap}}
 .stage{{border:1px solid #ddd;border-radius:6px;padding:6px 8px;font-size:12px;min-width:104px}}
 .stage.off{{opacity:.4}}
 .answer{{white-space:pre-wrap;background:#fafafa;border:1px solid #eee;padding:12px}}
 code{{font-size:12px}}
</style>
<h1>Sổ vết <code>{escape(str(data['trace_id']))}</code></h1>
<p><b>Câu hỏi:</b> {escape(str(data['question'] or '—'))}</p>
<p><small>Màn hình này <b>chỉ đọc</b> bản ghi đã lưu. Nó không chạy lại câu hỏi —
chạy lại sẽ cho một con số khác và trả lời một câu hỏi khác.</small></p>

<h2>1 · Mỗi con số nối về đâu</h2>
{warning}
<table><tr><th>Tuyên bố</th><th>Giá trị</th><th>Evidence</th><th>Nguồn</th><th>Phiên bản dữ liệu</th></tr>
{claim_rows}</table>
<div class="answer">{escape(str(data['answer'] or ''))}</div>

<h2>2 · Chặng dừng và lý do</h2>
<p><b>Hành động:</b> {escape(str(gate['action']))} · <b>Mã luật:</b>
<code>{escape(str(gate['rule_id']))}</code></p>
<p>{escape(str(gate['reason'] or ''))}</p>
<p><small>Phase đã chạy: {escape(str(gate['evaluated_phases']))} — phase không có
trong danh sách này là phase <b>không chạy</b>, không phải phase đã qua.</small></p>
<table><tr><th>Mã</th><th>Lý do</th><th>Người dùng sửa được?</th></tr>{issue_rows}</table>

<h2>3 · Ngân sách</h2>
<div class="flow">{stage_cells}</div>
<p><small>Tổng: {budget['timing_ms'].get('total', '—')} ms ·
Lời gọi LLM tuần tự: {budget['llm_calls_critical']} ·
Cache kế hoạch: {budget['plan_cache_hit']} ·
Trong ngân sách: {budget['within_budget']}</small></p>
"""
