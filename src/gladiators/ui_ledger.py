"""Màn hình duyệt sổ bảo trì — Spec2308 §WP-B11.3.

**Đây không phải "hệ tự học"** (B11-R4). Nó là một *vòng bảo trì có người duyệt*:
máy quan sát và xếp hạng, **người** quyết định, và mỗi quyết định để lại một dòng
có tác giả và thời điểm.

Chấp nhận một đề xuất **không** sửa ``catalog.py``. Nó ghi một mục vào
``domain/alias_overlay.json`` — file có trong repo, có review, có tác giả.
Overlay chỉ ánh xạ **một cách gọi mới** tới **một ref đã có**; nó không thể tạo
ra một metric mới, một định nghĩa mới hay một quan hệ mới.
"""
from __future__ import annotations

import json
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

from gladiators.domain.alias_index import ALIAS_OVERLAY_PATH, AliasOverlayError
from gladiators.domain.catalog import CATALOG

LEDGER_REPORT = Path("artifacts/ledger/report.json")


def load_report(path: Path | None = None) -> dict[str, Any]:
    target = path or LEDGER_REPORT
    if not target.exists():
        return {"refusals": 0, "clusters": [], "by_rule": {}}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"refusals": 0, "clusters": [], "by_rule": {}}


def accept(
    surface: str, ref: str, approved_by: str, *,
    occurrences: int = 0, path: Path | None = None,
) -> dict[str, Any]:
    """Ghi một mục overlay đã có người ký.

    B11-R1: ``approved_by`` rỗng ⇒ từ chối. Không có mặc định, không có
    ``"system"``, không có ``"auto"`` — một cái tên máy tự điền vào ô người duyệt
    làm cả vòng duyệt này thành trang trí.
    """
    approved_by = str(approved_by or "").strip()
    if not approved_by:
        raise AliasOverlayError("thiếu approved_by: overlay phải có người ký")
    if ref not in CATALOG:
        raise AliasOverlayError(f"ref không tồn tại trong catalog: {ref}")
    surface = str(surface or "").strip()
    if not surface:
        raise AliasOverlayError("thiếu surface")

    target = path or ALIAS_OVERLAY_PATH
    entries = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    entry = {
        "surface": surface, "ref": ref,
        "approved_by": approved_by,
        "approved_at": date.today().isoformat(),
        "occurrences": int(occurrences),
    }
    # Cùng surface duyệt lại ⇒ THAY, không thêm dòng thứ hai: hai mục cùng surface
    # trỏ hai ref khác nhau là một mâu thuẫn không ai giải quyết được lúc chạy.
    entries = [item for item in entries if item.get("surface") != surface]
    entries.append(entry)
    target.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return entry


def render(report: dict[str, Any] | None = None) -> str:
    data = report if report is not None else load_report()
    overlay = (
        json.loads(ALIAS_OVERLAY_PATH.read_text(encoding="utf-8"))
        if ALIAS_OVERLAY_PATH.exists() else []
    )

    rows = "".join(
        "<tr>"
        f"<td class='num'>{entry['occurrences']}</td>"
        f"<td><code>{escape(str(entry['rule_id']))}</code></td>"
        f"<td>{escape(str(entry['surface']))}</td>"
        f"<td><small>{escape(str(entry.get('example_question') or ''))}</small></td>"
        + (
            "<td>"
            f"<code>{escape(str(entry['suggestion']['ref']))}</code> "
            f"<small>({entry['suggestion']['similarity']})</small><br>"
            f"<input id='by-{index}' placeholder='tên người duyệt'>"
            f" <button onclick=\"decide({index},'accept')\">Chấp nhận</button>"
            f" <button onclick=\"decide({index},'reject')\">Từ chối</button>"
            f"<div id='out-{index}' class='out'></div>"
            "</td>"
            if entry.get("suggestion") else
            "<td><small>không có đề xuất — cần người xem</small></td>"
        )
        + "</tr>"
        for index, entry in enumerate(data.get("clusters", [])[:20])
    ) or "<tr><td colspan='5'><i>Sổ trống. Chạy một suite eval để sinh dữ liệu.</i></td></tr>"

    overlay_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('surface')))}</td>"
        f"<td><code>{escape(str(item.get('ref')))}</code></td>"
        f"<td>{escape(str(item.get('approved_by')))}</td>"
        f"<td>{escape(str(item.get('approved_at')))}</td>"
        "</tr>"
        for item in overlay
    ) or "<tr><td colspan='4'><i>Chưa có mục nào được duyệt.</i></td></tr>"

    return f"""<!doctype html><meta charset="utf-8">
<title>Sổ bảo trì có người duyệt</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:24px;max-width:1100px;line-height:1.5}}
 h1{{font-size:20px}} h2{{font-size:15px;margin-top:28px}}
 table{{border-collapse:collapse;width:100%;font-size:13px}}
 td,th{{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}}
 .num{{text-align:right}} input{{font-size:12px;padding:2px 4px}}
 .out{{font-size:12px;color:#555;margin-top:4px}}
 .box{{background:#f6f8fa;border-left:4px solid #666;padding:8px 12px;font-size:13px}}
</style>
<h1>Sổ bảo trì có người duyệt</h1>
<div class="box">
Máy <b>quan sát</b> và xếp hạng; <b>người</b> quyết định. Chấp nhận một đề xuất
<b>không</b> sửa catalog — nó ghi một mục vào <code>domain/alias_overlay.json</code>
kèm tác giả và thời điểm. Overlay chỉ ánh xạ <b>một cách gọi mới</b> tới
<b>một ref đã có</b>: nó không thể tạo ra một metric, một định nghĩa hay một quan
hệ mới.
</div>
<p><b>{data.get('refusals', 0)}</b> lần từ chối đã ghi ·
<b>{len(data.get('clusters', []))}</b> cụm.</p>

<h2>Chữ hệ chưa hiểu, xếp theo số lần gặp</h2>
<table><tr><th>Lần</th><th>Mã luật</th><th>Chữ / vấn đề</th><th>Ví dụ</th><th>Đề xuất</th></tr>
{rows}</table>

<script>
const CLUSTERS = {json.dumps([
    {"surface": entry["surface"], "ref": (entry.get("suggestion") or {}).get("ref"),
     "occurrences": entry["occurrences"]}
    for entry in data.get("clusters", [])[:20]
], ensure_ascii=False)};
async function decide(index, decision) {{
  const body = {{...CLUSTERS[index], decision,
                 approved_by: document.getElementById('by-'+index).value}};
  const res = await fetch('/ledger/decision', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(body),
  }});
  const data = await res.json();
  document.getElementById('out-'+index).textContent =
    res.ok ? (data.applied ? 'đã ghi vào overlay' : 'đã bỏ qua')
           : (data.detail && data.detail.reason) || 'từ chối';
}}
</script>

<h2>Đã duyệt</h2>
<table><tr><th>Cách gọi</th><th>Ref</th><th>Người duyệt</th><th>Thời điểm</th></tr>
{overlay_rows}</table>
"""
