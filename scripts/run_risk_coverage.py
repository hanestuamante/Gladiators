#!/usr/bin/env python3
"""Đường cong rủi ro–độ phủ và AURC — Spec2308 §WP-B4.

    PYTHONPATH=src .venv/Scripts/python.exe scripts/run_risk_coverage.py \\
      --suite eval/independent/answerable_manual.json --provider offline

Hệ này là một bộ **dự đoán có chọn lọc**: nó được phép nói "không biết". Chấm nó
bằng một điểm vận hành duy nhất là bỏ mất toàn bộ câu chuyện — câu trả lời cho
*"sao các bạn an toàn quá vậy?"* phải là *"đây là các điểm khác chúng em đo
được, và đây là lý do chọn điểm này"*.

Bốn điểm dưới đây đều là tổ hợp **cờ đã có sẵn**, không phải chế độ mới (B4-R3):
sinh một điểm vận hành mới chỉ để đường cong đẹp hơn là vẽ một hệ thống không
tồn tại.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from gladiators.agent.workflow import AgentRuntime
from gladiators.evalkit.metrics import compute_selective_metrics
from gladiators.runtime_factory import create_runtime

ROOT = Path(__file__).resolve().parents[1]

# B4-R1: L3 KHÔNG BAO GIỜ là cấu hình phát hành. Nó có mặt để đường cong có một
# điểm ở đầu "độ phủ cao, rủi ro cao", tức để thấy được cái giá của việc tắt
# verifier — không phải để đề xuất tắt nó.
OPERATING_POINTS: tuple[dict[str, object], ...] = (
    # L0 là điểm ĐANG PHÁT HÀNH; ba điểm còn lại là ablation của chính nó. Spec
    # viết L1/L2 là "+A13" / "+A5" như thể chúng cộng thêm vào L0, nhưng mặc định
    # hiện tại ĐÃ có cả hai — nên đo theo chiều cộng sẽ ra ba bản sao của cùng
    # một điểm. Đo theo chiều TRỪ cho ra đúng con số spec muốn: từng tính năng
    # đóng góp bao nhiêu độ phủ.
    {"id": "L0", "label": "mặc định hiện tại", "release": True, "flags": {}},
    {"id": "L1", "label": "− A13 trả lời từng phần", "release": False,
     "flags": {"enable_partial_answer": False}},
    {"id": "L2", "label": "− A13 − A5 ba vòng lặp", "release": False,
     "flags": {"enable_partial_answer": False, "enable_cheap_loops": False}},
    # B4-R1: L3 KHÔNG BAO GIỜ là cấu hình phát hành. Nó có mặt để thấy CÁI GIÁ
    # của việc bỏ hai lớp kiểm — không phải để đề xuất bỏ chúng.
    {"id": "L3", "label": "− gate − verifier (chỉ để vẽ đường cong)", "release": False,
     "flags": {"enable_verifier": False, "enable_gate": False}},
)


def _answerable(case: dict) -> bool | None:
    """Nhãn "dữ liệu có trả lời được không", tri-state.

    ``None`` nghĩa là KHÔNG CHẤM ĐƯỢC, khác hẳn ``False``. Suy nhãn từ
    ``expected_action`` làm ``over_refusal_rate`` luôn bằng 0 theo định nghĩa
    (§B1.2), nên chỉ bộ đề có nhãn ``answerable`` thật mới vẽ được đường cong này.
    """
    value = case.get("answerable")
    return None if value is None else bool(value)


def _correct(response, case: dict) -> bool:
    expected = case.get("expected_value") or {}
    if not expected:
        return True
    values = {
        float(item.value) for item in response.evidence
        if isinstance(item.value, (int, float)) and not isinstance(item.value, bool)
    }
    return any(
        any(abs(value - float(target)) < 0.5 for value in values)
        for target in expected.values() if target is not None
    )


def measure(cases: list[dict], runtime: AgentRuntime) -> dict[str, object]:
    wrong = 0
    labelled = 0
    answerable_ids: set[str] = set()
    unanswerable_ids: set[str] = set()
    answered_ids: set[str] = set()
    refused_ids: set[str] = set()
    correct_ids: set[str] = set()
    for case in cases:
        label = _answerable(case)
        if label is None:
            continue
        labelled += 1
        (answerable_ids if label else unanswerable_ids).add(case["id"])
        response = runtime.run(case["question"])
        if response.gate.action == "allow":
            answered_ids.add(case["id"])
            if _correct(response, case):
                correct_ids.add(case["id"])
            else:
                wrong += 1
        else:
            refused_ids.add(case["id"])

    # W9.1: MỘT hàm chung với run_evaluation. Khoá "coverage" cũ của script
    # này là answered/labelled — nay mang tên thật answer_rate_all; risk trên
    # mẫu số rỗng trả None, không phải 0.0.
    metrics = compute_selective_metrics(
        answerable=answerable_ids, unanswerable=unanswerable_ids,
        answered=answered_ids, refused=refused_ids, correct=correct_ids,
    )
    rounded = {
        key: (round(value, 4) if isinstance(value, float) else value)
        for key, value in metrics.items()
    }
    return {
        "labelled_cases": labelled,
        **rounded,
        # Một chu kỳ tương thích: khoá cũ "coverage" của script NÀY nghĩa là
        # answered/labelled.
        "coverage": rounded["answer_rate_all"],
        "answered": len(answered_ids), "wrong": wrong,
    }


def aurc(points: list[tuple[float, float]]) -> float | None:
    """Diện tích dưới đường cong rủi ro–độ phủ, quy tắc hình thang.

    Thấp hơn là tốt hơn: nó đo lượng rủi ro phải chịu để mua thêm độ phủ. Một
    điểm duy nhất không cho ra diện tích nào — cần ít nhất hai.
    """
    usable = sorted((c, r) for c, r in points if c is not None and r is not None)
    if len(usable) < 2:
        return None
    area = 0.0
    for (c0, r0), (c1, r1) in zip(usable, usable[1:]):
        area += (c1 - c0) * (r0 + r1) / 2
    span = usable[-1][0] - usable[0][0]
    return round(area / span, 4) if span else None


def svg(rows: list[dict], aurc_value: float | None) -> str:
    """SVG nội tuyến, nhúng thẳng vào slide — không phụ thuộc thư viện vẽ."""
    width, height, pad = 460, 300, 46
    def px(coverage: float) -> float:
        return pad + coverage * (width - 2 * pad)
    def py(risk: float) -> float:
        return height - pad - risk * (height - 2 * pad)

    usable = [row for row in rows if row["coverage"] is not None]
    path = " ".join(
        f"{'M' if index == 0 else 'L'}{px(row['coverage']):.1f},{py(row['risk']):.1f}"
        for index, row in enumerate(sorted(usable, key=lambda item: item["coverage"]))
    )
    dots = "".join(
        f'<circle cx="{px(row["coverage"]):.1f}" cy="{py(row["risk"]):.1f}" r="5" '
        f'fill="{"#1a7f37" if row["release"] else "#b42318"}"/>'
        f'<text x="{px(row["coverage"]):.1f}" y="{py(row["risk"]) - 11:.1f}" '
        f'font-size="11" text-anchor="middle">{row["id"]}</text>'
        for row in usable
    )
    caption = "" if aurc_value is None else f"AURC = {aurc_value}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="system-ui,sans-serif">'
        f'<rect width="{width}" height="{height}" fill="#fff"/>'
        f'<line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}" stroke="#333"/>'
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height - pad}" stroke="#333"/>'
        f'<text x="{width / 2}" y="{height - 12}" font-size="12" text-anchor="middle">'
        f'Độ phủ (coverage) →</text>'
        f'<text x="14" y="{height / 2}" font-size="12" text-anchor="middle" '
        f'transform="rotate(-90 14 {height / 2})">Rủi ro (risk) →</text>'
        f'<path d="{path}" fill="none" stroke="#666" stroke-dasharray="4 3"/>'
        f'{dots}'
        f'<text x="{width - pad}" y="{pad - 22}" font-size="11" text-anchor="end">{caption}</text>'
        # B4-R1 ghi thẳng trên biểu đồ: đọc biểu đồ mà không đọc chú thích vẫn
        # phải biết điểm đỏ không phải cấu hình phát hành.
        f'<text x="{width - pad}" y="{pad - 8}" font-size="11" text-anchor="end" '
        f'fill="#b42318">đỏ = KHÔNG phải cấu hình phát hành</text>'
        f'</svg>'
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="eval/independent/answerable_manual.json")
    parser.add_argument("--provider", default="offline")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    cases = json.loads((ROOT / args.suite).read_text(encoding="utf-8"))
    if isinstance(cases, dict):
        cases = cases.get("cases", [])

    rows: list[dict] = []
    for point in OPERATING_POINTS:
        base = create_runtime(args.provider)
        flags = dict(point["flags"])
        runtime = AgentRuntime(
            llm_client=base.llm_client,
            enable_gate=bool(flags.get("enable_gate", True)),
            enable_verifier=bool(flags.get("enable_verifier", True)),
            enable_partial_answer=bool(flags.get("enable_partial_answer", True)),
            enable_cheap_loops=bool(flags.get("enable_cheap_loops", True)),
        )
        result = measure(cases, runtime)
        rows.append({
            "id": point["id"], "label": point["label"],
            "release": point["release"], **result,
        })

    area = aurc([(row["coverage"], row["risk"]) for row in rows])
    report = {
        "suite": args.suite, "provider": args.provider,
        "measured_on": date.today().isoformat(),
        "schema_version": "risk-coverage-report.v2",
        "points": rows, "aurc": area,
        "release_point": "L0",
        "note": (
            "L3 tắt verifier và CHỈ để vẽ đường cong — không bao giờ là cấu hình "
            "phát hành (B4-R1). Mọi điểm dùng cùng một bộ đề và cùng một oracle "
            "(B4-R2)."
        ),
        "svg": svg(rows, area),
    }
    output = args.output or f"eval/reports/{date.today().isoformat()}-risk-coverage.json"
    out = ROOT / output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out.with_suffix(".svg")).write_text(report["svg"] + "\n", encoding="utf-8")
    print(json.dumps(
        {key: value for key, value in report.items() if key != "svg"},
        ensure_ascii=False, indent=2,
    ))


if __name__ == "__main__":
    main()
