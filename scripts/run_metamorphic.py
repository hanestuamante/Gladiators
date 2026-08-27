#!/usr/bin/env python3
"""Kiểm biến hình trên cả một bộ đề — Spec2308 §WP-B7.3.

    PYTHONPATH=src .venv/Scripts/python.exe scripts/run_metamorphic.py \\
      --suite eval/independent/answerable_manual.json --provider offline

Kiểm tính đúng đắn **khi không có đáp án chuẩn**, bằng **quan hệ giữa các câu
hỏi**. Bộ 44 câu đẻ ra hàng trăm phép kiểm mà **không cần ai gán nhãn thêm** —
đó là câu trả lời trực tiếp cho phê bình *"bộ đề của các bạn tự viết"*.

**B7-R1 — không dùng LLM để sinh biến thể.** Nếu bộ sinh biến thể do LLM viết
thì lại phải kiểm chính bộ sinh, và không lớp nào đang làm việc đó.
**B7-R4 — chạy hoàn toàn offline**, 0 chi phí LLM.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval" / "metamorphic"))

from relations import RELATIONS, validate_relations  # noqa: E402

from gladiators.runtime_factory import create_runtime  # noqa: E402


def _numbers(response) -> tuple[float, ...]:
    return tuple(sorted(
        float(item.value) for item in response.evidence
        if isinstance(item.value, (int, float)) and not isinstance(item.value, bool)
    ))


def _by_metric(response) -> dict[str, float]:
    return {
        item.metric: float(item.value) for item in response.evidence
        if isinstance(item.value, (int, float)) and not isinstance(item.value, bool)
    }


def _verdict(kind: str, expectation: str | None, base, variant) -> tuple[str, str]:
    """``pass`` | ``fail`` | ``skip`` kèm lý do.

    B7-R3: ``skip`` đếm RIÊNG, không gộp vào pass. Một quan hệ không áp dụng được
    mà tính là đạt sẽ thổi phồng chỉ số bằng đúng những ca nó không kiểm.
    """
    base_numbers, variant_numbers = _numbers(base), _numbers(variant)

    if kind == "invariant":
        if base.gate.action != variant.gate.action:
            return "fail", f"action {base.gate.action} → {variant.gate.action}"
        if base_numbers != variant_numbers:
            return "fail", f"số {base_numbers} → {variant_numbers}"
        return "pass", ""

    # Hai nhánh dưới đây chỉ có nghĩa khi CẢ HAI câu đều được trả lời. Một bên bị
    # từ chối thì không có gì để so — đó là skip, không phải fail.
    if base.gate.action != "allow" or variant.gate.action != "allow":
        return "skip", "một trong hai câu không được trả lời"
    if not base_numbers or not variant_numbers:
        return "skip", "một trong hai câu không mang số"

    if expectation == "count_not_greater":
        # So theo TỪNG METRIC, không so max của cả tập. Thêm "có voucher" khiến
        # câu rẽ sang một macro khác trả về sáu con số về hiệu quả khuyến mãi;
        # so max của hai tập đó là so hai đại lượng khác nhau, và phép kiểm sẽ
        # báo lỗi ở chỗ hệ thống không hề sai.
        base_metrics, variant_metrics = _by_metric(base), _by_metric(variant)
        shared = set(base_metrics) & set(variant_metrics)
        if not shared:
            return "skip", "hai câu trả về metric khác nhau, không so được"
        grew = {
            metric for metric in shared
            if variant_metrics[metric] > base_metrics[metric]
        }
        if grew:
            return "fail", (
                "thêm điều kiện lọc mà số TĂNG: "
                + ", ".join(
                    f"{metric} {base_metrics[metric]} → {variant_metrics[metric]}"
                    for metric in sorted(grew)
                )
            )
        return "pass", ""
    if expectation == "values_differ":
        if base_numbers == variant_numbers:
            # KHÔNG phải "fail". Spec nói bằng nhau thì "RẤT CÓ THỂ scope bị bỏ
            # qua" — một nghi vấn, không phải một bằng chứng. Dữ liệu này có đúng
            # 10 shop ở MỖI thị trường, nên "Có bao nhiêu shop ở VN/ID?" bằng
            # nhau là ĐÚNG. Chấm nó thành lỗi là dạy người đọc bỏ qua chỉ số.
            return "suspect", f"hai câu khác nhau cho cùng kết quả {base_numbers}"
        return "pass", ""
    return "skip", f"expectation không hiểu được: {expectation}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="eval/independent/answerable_manual.json")
    parser.add_argument("--provider", default="offline")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    validate_relations()
    cases = json.loads((ROOT / args.suite).read_text(encoding="utf-8"))
    if isinstance(cases, dict):
        cases = cases.get("cases", [])
    cases = [case for case in cases if case.get("question")]
    if args.limit:
        cases = cases[: args.limit]

    runtime = create_runtime(args.provider)
    rows: list[dict] = []
    for case in cases:
        question = case["question"]
        base = runtime.run(question)
        for relation in RELATIONS:
            try:
                if relation.relation_id == "MR-3":
                    entity = case.get("entity_text") or ""
                    if not entity or entity not in question:
                        raise ValueError("không có entity nguyên văn để đánh dấu")
                    variant = relation.transform(question, entity)
                else:
                    variant = relation.transform(question)
            except (ValueError, KeyError, IndexError) as exc:
                rows.append({
                    "case": case["id"], "relation": relation.relation_id,
                    "kind": relation.kind, "verdict": "skip",
                    "reason": f"không áp dụng được: {exc}",
                })
                continue
            if variant.strip() == question.strip():
                rows.append({
                    "case": case["id"], "relation": relation.relation_id,
                    "kind": relation.kind, "verdict": "skip",
                    "reason": "biến thể trùng câu gốc",
                })
                continue
            result = runtime.run(variant)
            verdict, reason = _verdict(
                relation.kind, relation.expectation, base, result,
            )
            rows.append({
                "case": case["id"], "relation": relation.relation_id,
                "kind": relation.kind, "verdict": verdict, "reason": reason,
                "question": question, "variant": variant,
            })

    by_relation: dict[str, dict[str, int]] = defaultdict(
        lambda: {"pass": 0, "fail": 0, "skip": 0, "suspect": 0},
    )
    for row in rows:
        by_relation[row["relation"]][row["verdict"]] += 1

    def rate(counts: dict[str, int]) -> float | None:
        # "suspect" nằm ở mẫu số: nó là một phép kiểm ÁP DỤNG ĐƯỢC và chưa qua,
        # chỉ là chưa kết luận được. Bỏ nó khỏi mẫu số sẽ làm tỷ lệ đẹp lên bằng
        # cách giấu đi đúng những ca cần người xem.
        applicable = counts["pass"] + counts["fail"] + counts["suspect"]
        return round(counts["pass"] / applicable, 4) if applicable else None

    totals = {"pass": 0, "fail": 0, "skip": 0, "suspect": 0}
    for counts in by_relation.values():
        for key in totals:
            totals[key] += counts[key]

    report = {
        "suite": args.suite, "provider": args.provider,
        "measured_on": date.today().isoformat(),
        "cases": len(cases), "checks": len(rows),
        "totals": totals,
        # Mẫu số là số phép kiểm ÁP DỤNG ĐƯỢC, không phải tổng số phép kiểm.
        "metamorphic_consistency_rate": rate(totals),
        "by_relation": {
            name: {**counts, "rate": rate(counts)}
            for name, counts in sorted(by_relation.items())
        },
        "failures": [row for row in rows if row["verdict"] == "fail"],
        "suspects": [row for row in rows if row["verdict"] == "suspect"],
    }
    output = args.output or f"eval/reports/{date.today().isoformat()}-metamorphic.json"
    out = ROOT / output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(
        {
            key: value for key, value in report.items()
            if key not in {"failures", "suspects"}
        },
        ensure_ascii=False, indent=2,
    ))
    print(
        f"{len(report['failures'])} vi phạm · "
        f"{len(report['suspects'])} nghi vấn chờ người xem — chi tiết ở {output}",
    )


if __name__ == "__main__":
    main()
