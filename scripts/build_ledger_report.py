#!/usr/bin/env python3
"""Gom cụm và xếp hạng sổ từ chối — Spec2308 §WP-B11.2.

    PYTHONPATH=src .venv/Scripts/python.exe scripts/build_ledger_report.py

Đây là nửa **QUAN SÁT** của vòng bảo trì. Nửa **tự sửa** cố ý không tồn tại: mỗi
cụm ở đây chỉ là một **đề xuất cho người duyệt**, và không gì trong file này ghi
vào ``catalog.py``.

Đề xuất ref ứng viên bằng khớp gần đúng với alias hiện có. Khớp gần đúng ở đây
**an toàn vì nó không tự áp**: nó chỉ xếp thứ tự công việc cho người duyệt. Cũng
chính phép khớp đó nếu chạy tự động sẽ là đúng lớp lỗi tệ nhất của hệ này — một
tên gần giống bị đoán thành tên khác.
"""
from __future__ import annotations

import argparse
import difflib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Dưới ngưỡng này thì "gợi ý" chỉ là nhiễu, và một danh sách gợi ý toàn nhiễu sẽ
# dạy người duyệt bấm Từ chối theo phản xạ.
MIN_SIMILARITY = 0.6


def suggest_ref(surface: str, index) -> dict[str, object] | None:
    """Ref ứng viên gần nhất, kèm điểm giống — hoặc ``None``.

    Trả ``None`` khi không đủ giống. Một gợi ý yếu vẫn là một gợi ý, và người
    duyệt sẽ đọc nó như một kết luận.
    """
    surfaces = {entry.normalized_surface: entry.ref for entry in index.entries}
    matches = difflib.get_close_matches(
        surface, list(surfaces), n=1, cutoff=MIN_SIMILARITY,
    )
    if not matches:
        return None
    best = matches[0]
    return {
        "ref": surfaces[best],
        "nearest_known_surface": best,
        "similarity": round(
            difflib.SequenceMatcher(None, surface, best).ratio(), 3,
        ),
    }


def build(rows: list[dict]) -> dict:
    from gladiators.domain.alias_index import AliasIndex

    index = AliasIndex()
    by_rule = Counter(str(row.get("rule_id") or "?") for row in rows)
    clusters: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        rule = str(row.get("rule_id") or "?")
        surfaces = row.get("unmatched_surfaces") or []
        if not surfaces:
            # Không có cụm chữ lạ ⇒ vấn đề KHÔNG nằm ở từ vựng. Gộp nó chung
            # bảng với các cụm từ vựng sẽ đề xuất thêm alias cho một câu chỉ
            # thiếu tên thị trường.
            slots = row.get("missing_slots") or []
            if slots:
                for slot in slots:
                    clusters[(rule, f"<thiếu ô: {slot}>")].append(row)
            else:
                # Không cụm chữ lạ, không ô thiếu ⇒ vấn đề là NĂNG LỰC dataset.
                # Gom theo mã luật: đó là thứ duy nhất phân biệt được các ca này,
                # và bịa ra một ô thiếu ở đây là gửi người duyệt đi sai hướng.
                clusters[(rule, "<năng lực dataset>")].append(row)
            continue
        for surface in surfaces:
            clusters[(rule, str(surface))].append(row)

    ranked = []
    for (rule, surface), hits in clusters.items():
        entry = {
            "rule_id": rule, "surface": surface, "occurrences": len(hits),
            "example_question": (
                hits[0].get("raw_question") or hits[0].get("normalized_question")
            ),
            "example_trace_id": hits[0].get("trace_id"),
            "suggestion": (
                None if surface.startswith("<")
                else suggest_ref(surface, index)
            ),
        }
        ranked.append(entry)
    ranked.sort(key=lambda item: (-item["occurrences"], item["surface"]))
    return {
        "refusals": len(rows),
        "by_rule": dict(by_rule.most_common()),
        "clusters": ranked,
        "note": (
            "Đây là nửa QUAN SÁT của vòng bảo trì có người duyệt. Mỗi cụm là một "
            "ĐỀ XUẤT; không gì trong file này ghi vào catalog. Chấp nhận một đề "
            "xuất ghi một mục vào domain/alias_overlay.json kèm người duyệt và "
            "thời điểm — overlay chỉ ánh xạ một cách gọi mới tới một ref ĐÃ CÓ."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", default="artifacts/ledger/refusals.jsonl")
    parser.add_argument("--output", default="artifacts/ledger/report.json")
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()

    from gladiators.agent.ledger import read_ledger

    rows = read_ledger(ROOT / args.ledger)
    report = build(rows)
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{report['refusals']} lần từ chối · {len(report['clusters'])} cụm")
    print(f"{'lần':>5}  {'mã luật':<26} chữ hệ chưa hiểu → đề xuất")
    for entry in report["clusters"][: args.top]:
        suggestion = entry["suggestion"]
        arrow = f" → {suggestion['ref']} ({suggestion['similarity']})" if suggestion else ""
        print(f"{entry['occurrences']:>5}  {entry['rule_id']:<26} {entry['surface']}{arrow}")


if __name__ == "__main__":
    main()
