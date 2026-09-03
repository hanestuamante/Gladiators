"""Sổ bảo trì có người duyệt — Spec2308 §WP-B11.

**Không gọi đây là "hệ tự học"** (B11-R4). Gọi đúng tên: *vòng bảo trì có người
duyệt*. Một giám khảo có kinh nghiệm sẽ hỏi ngay *"tự học thì ai kiểm?"*, và câu
trả lời phải nằm sẵn trong thiết kế chứ không nằm trong phần ứng khẩu.

Ranh giới, làm nửa này và không làm nửa kia:

* **Làm — vòng QUAN SÁT**: ghi mọi lần từ chối kèm mã luật và đoạn chữ không
  khớp, gom cụm, xếp hạng, đưa cho người duyệt.
* **Không làm — vòng TỰ SỬA**: máy tự thêm từ đồng nghĩa vào catalog, tự sinh
  định nghĩa nghiệp vụ, tự mở rộng quan hệ, hay áp dụng mà không ai ký.

Lý do giữ ranh giới đó: **một định nghĩa nghiệp vụ do máy sinh mà không ai ký là
đúng thứ kiến trúc này tồn tại để chặn.**
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_PATH = Path("artifacts/ledger/refusals.jsonl")


def unmatched_surfaces(request: Any) -> tuple[str, ...]:
    """Cụm còn lại sau khi ``AliasIndex.find_in`` đã tiêu thụ hết phần nó nhận ra.

    Chỉ tính được sau WP-A4: trước đó có nhiều bộ khớp alias song song và không
    bộ nào biết phần dư THẬT SỰ là gì — mỗi bộ chỉ biết phần dư của riêng nó.
    """
    analytical = getattr(request, "analytical", None) or {}
    surfaces: list[str] = []
    for key in ("requested_measures", "requested_dimensions"):
        for item in analytical.get(key) or ():
            data = item if isinstance(item, dict) else getattr(item, "__dict__", {})
            if data.get("ref"):
                continue
            surface = str(data.get("surface_text") or "").strip()
            if surface:
                surfaces.append(surface)
    return tuple(dict.fromkeys(surfaces))


# Chỉ những mã luật THẬT SỰ nói về ô còn thiếu. Suy "thiếu country" từ việc
# request.country rỗng là sai: với câu vượt năng lực dataset, parser dừng sớm nên
# country rỗng dù câu có ghi rõ "tại VN" — và sổ bảo trì sẽ đẩy người duyệt đi
# tìm 28 ca thiếu thị trường không hề tồn tại.
_SLOT_RULES = frozenset({
    "A-CROSS-CURRENCY-SCOPE", "A-MISSING-SLOT", "A-AMBIGUOUS",
})


def missing_slots(request: Any, decision: Any) -> tuple[str, ...]:
    """Ô mà lời từ chối này THẬT SỰ nói là còn thiếu."""
    found: list[str] = []
    for issue in getattr(decision, "issues", ()) or ():
        for slot in getattr(issue, "missing_slots", ()) or ():
            found.append(str(slot))
    rule = str(getattr(decision, "rule_id", "") or "")
    if not found and rule in _SLOT_RULES and not getattr(request, "country", None):
        found.append("country")
    return tuple(dict.fromkeys(found))


def record_refusal(
    request: Any, decision: Any, trace_id: str, *,
    path: Path | None = None, redact=None,
) -> dict[str, Any] | None:
    """Ghi một dòng JSONL cho một lần từ chối. Trả dòng đã ghi, hoặc ``None``.

    B11-R3: toàn bộ dòng đi qua ``redact`` trước khi chạm đĩa. Sổ này ghi câu hỏi
    người dùng gõ, nên nó là bản sao thứ hai của dữ liệu người dùng — và một bản
    sao nằm ngoài cơ chế redact là một bản sao không ai redact.
    """
    if getattr(decision, "action", None) == "allow":
        return None
    analytical = getattr(request, "analytical", None) or {}
    row = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trace_id": trace_id,
        "rule_id": getattr(decision, "rule_id", None),
        "action": getattr(decision, "action", None),
        "normalized_question": str(analytical.get("normalized_question") or ""),
        # Câu GỐC cũng phải có mặt: với câu vượt năng lực dataset, parser dừng
        # trước khi sinh analytical, nên normalized_question rỗng và người duyệt
        # nhìn vào một dòng không nói gì.
        "raw_question": str((getattr(request, "slots", {}) or {}).get("raw_text") or ""),
        "unmatched_surfaces": list(unmatched_surfaces(request)),
        "missing_slots": list(missing_slots(request, decision)),
        "intent": getattr(request, "intent", None),
        "country": getattr(request, "country", None),
    }
    if redact is not None:
        # TraceStore.redact nhận CHÍNH cấu trúc, không nhận chuỗi JSON: nó duyệt
        # dict/list theo tên khoá. Đưa chuỗi vào sẽ đi nhánh "không phải dict"
        # và trả lại nguyên vẹn — redact không chạy mà cũng không báo lỗi.
        row = redact(row)
    target = path or LEDGER_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def read_ledger(path: Path | None = None) -> list[dict[str, Any]]:
    """Đọc sổ. Dòng hỏng được BỎ QUA chứ không làm hỏng cả báo cáo.

    Một file JSONL ghi nối tiếp có thể bị cắt giữa dòng khi tiến trình chết; để
    một dòng cụt giết cả báo cáo là biến một sự cố ghi thành một sự cố đọc.
    """
    target = path or LEDGER_PATH
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows
