"""Build the executable DR 26/07 regression suite from the checked-in source doc.

The prose document is the source of truth for question text.  Expected routing
metadata below is deliberately conservative: data denotations that still need a
human/provider oracle are labelled instead of being invented.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# The generator validates labels against the live intent registry, so it needs
# the package importable even when run without PYTHONPATH set.
sys.path.insert(0, str(ROOT / "src"))

# The Windows console defaults to cp1252 and cannot encode Vietnamese; without
# this the generator does its work and then dies on its own progress message.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SOURCE = ROOT / "docs" / "qa" / "DR TASK 1407.md"
OUTPUT = ROOT / "eval" / "dr2607.json"

_HEADING = re.compile(r"^## .*\bTestcase\s+(\d+):", re.IGNORECASE)
_QUESTION = re.compile(r"Câu hỏi:\**\s*(.+)$", re.IGNORECASE)


def _question_text(line: str) -> str:
    match = _QUESTION.search(line)
    if not match:
        raise ValueError(f"Không đọc được dòng câu hỏi: {line!r}")
    value = match.group(1).strip()
    quote_positions = [
        index for index, char in enumerate(value) if char in {'"', "“", "”"}
    ]
    if len(quote_positions) >= 2:
        value = value[quote_positions[0] + 1 : quote_positions[-1]]
    return value.strip().strip("*").strip()


# TC-specific safety contracts extracted from the 26/07 analysis/spec.  Empty
# allowed_rule_ids means the testcase is primarily an executable stability and
# entity/semantic-binding case, not that any route is acceptable.
CONTRACTS: dict[int, dict[str, object]] = {
    1: {"complexity_level": "L2", "answerability_class": "C1", "status": "provider_required"},
    2: {"complexity_level": "L2", "answerability_class": "C1", "status": "provider_required"},
    3: {"complexity_level": "L2", "answerability_class": "C1"},
    4: {"complexity_level": "L3", "answerability_class": "C1"},
    5: {"complexity_level": "L2", "answerability_class": "C1"},
    6: {
        "complexity_level": "L4",
        "answerability_class": "C4",
        "expected_action": "abstain",
        "allowed_rule_ids": ["A-MISSING-FORECAST", "A19-OP"],
    },
    7: {
        "complexity_level": "L2",
        "answerability_class": "C1",
        "expected_action": "clarify",
    },
    8: {
        "complexity_level": "L3",
        "answerability_class": "C1+C4",
        "expected_action": "clarify",
        "allowed_rule_ids": ["A-AMBIGUOUS"],
    },
    9: {"complexity_level": "L3", "answerability_class": "C1"},
    10: {"complexity_level": "L2", "answerability_class": "C1"},
    11: {"complexity_level": "L1", "answerability_class": "C1"},
    12: {"complexity_level": "L2", "answerability_class": "C1"},
    13: {
        "complexity_level": "L3",
        "answerability_class": "C2",
        "expected_action": "clarify",
        "allowed_rule_ids": ["A16-CROSS-CURRENCY"],
    },
    14: {"complexity_level": "L3", "answerability_class": "C1+C4"},
    15: {"complexity_level": "L3", "answerability_class": "C1"},
    16: {
        "complexity_level": "L2",
        "answerability_class": "C1",
        "expected_action": "clarify",
    },
    17: {"complexity_level": "L3", "answerability_class": "C1"},
    18: {
        "complexity_level": "L1",
        "answerability_class": "C4",
        "expected_action": "abstain",
        "allowed_rule_ids": ["A-MISSING-SKU"],
    },
    19: {
        "complexity_level": "L2",
        "answerability_class": "C1",
        "status": "needs_human_policy_oracle",
    },
    20: {
        "complexity_level": "L1",
        "answerability_class": "C1",
        "expected_action": "abstain",
        "allowed_rule_ids": ["A-ENTITY-NOT-FOUND"],
        "forbidden_rule_ids": ["A19-CAT"],
    },
    21: {
        "complexity_level": "L3",
        "answerability_class": "C1",
        "expected_action": "clarify",
        "allowed_rule_ids": ["A22-ALIGN-QUALIFIER"],
    },
    22: {
        "complexity_level": "L3",
        "answerability_class": "C1",
        "expected_action": "clarify",
        "allowed_rule_ids": ["A22-ALIGN-QUALIFIER"],
    },
    23: {
        "complexity_level": "L3",
        "answerability_class": "C1+C4",
        "expected_action": "allow",
        "allowed_rule_ids": ["A22-ALIGN-SUBREQUEST"],
    },
    24: {
        "complexity_level": "L3",
        "answerability_class": "C1",
        "expected_action": "clarify",
        "allowed_rule_ids": ["A22-ALIGN-QUALIFIER"],
    },
    25: {
        "complexity_level": "L3",
        "answerability_class": "C1+C4",
        "expected_action": "allow",
        "allowed_rule_ids": ["A22-ALIGN-SUBREQUEST"],
    },
    26: {"complexity_level": "L3", "answerability_class": "C1"},
    27: {"complexity_level": "L1", "answerability_class": "C1"},
    28: {
        "complexity_level": "L2",
        "answerability_class": "C4",
        "expected_action": "abstain",
        "allowed_rule_ids": ["A-MISSING-PROFIT"],
    },
    29: {
        "complexity_level": "L3",
        "answerability_class": "C2",
        "expected_action": "clarify",
        # W26/W28-B: trước đây câu này bị chặn vì `mean` không được chứng nhận
        # cho discount_percent — một lý do nói về BẢNG catalog. Nay phép trung
        # bình hợp lệ (snapshot_stock), nên trở ngại còn lại là trở ngại THẬT:
        # câu hỏi so hai thị trường trong khi plan chỉ phủ một, và alignment nói
        # đúng điều đó. Hai bảo đảm giữ nguyên: không `A-ALLOW`, và không trộn
        # VND với IDR.
        "allowed_rule_ids": [
            "A16-CROSS-CURRENCY", "A22-ALIGN-MEASURE", "A22-ALIGN-COUNTRY",
        ],
        "forbidden_rule_ids": ["A-ALLOW"],
        "forbidden_analytical_kind": "listing_count",
        "expected_semantic_refs": ["measure.voucher_discount", "dim.country"],
    },
    30: {
        "complexity_level": "L2",
        "answerability_class": "C1",
        "expected_action": "clarify",
        "allowed_rule_ids": ["A22-ALIGN-QUALIFIER"],
    },
    31: {
        "complexity_level": "L4",
        "answerability_class": "C1+C4",
        "expected_action": "allow",
        "allowed_rule_ids": ["A22-ALIGN-SUBREQUEST"],
    },
    32: {
        "complexity_level": "L2",
        "answerability_class": "C4",
        "expected_action": "abstain",
        "allowed_rule_ids": ["A-MISSING-ADS"],
    },
    33: {
        "complexity_level": "L2",
        "answerability_class": "C4",
        "expected_action": "abstain",
        "allowed_rule_ids": ["A-MISSING-SKU"],
    },
    34: {
        "complexity_level": "L2",
        "answerability_class": "C1",
        # Corrected 29/07. The DR premise (item 24710759163 missing its 02/07
        # snapshot) is false: the listing has all three dates and two eligible
        # transitions. The real defect is date-window narrowing — the runtime
        # answers the trailing 1-day leg for a question spanning 01/07->03/07,
        # inverting the sign. expected_action stays None because the correct
        # answer shape is P1 scope; the red contract lives in
        # tests/test_p0_regression_lock.py.
        "status": "executable_red_date_window_narrowing",
        "oracle_ref": "eval/independent/p0_probe_expected.json#p0_tc34_window",
    },
    35: {"complexity_level": "L2", "answerability_class": "C1+C3"},
    36: {
        "complexity_level": "L3",
        "answerability_class": "C2",
        "expected_action": "clarify",
        "allowed_rule_ids": ["A16-CROSS-CURRENCY"],
    },
    37: {
        "complexity_level": "L1",
        "answerability_class": "C4",
        "expected_action": "abstain",
        "allowed_rule_ids": ["A-MISSING-INVENTORY"],
    },
    38: {
        "complexity_level": "L2",
        "answerability_class": "C1",
        "status": "provider_required",
    },
    39: {
        "complexity_level": "L3",
        "answerability_class": "C1",
        "expected_action": "clarify",
        # W26 (Spec3008 §13): câu này yêu cầu TƯỜNG MINH cộng `monthly_sold`
        # qua ba đợt thu. Trước W26 hệ để template trả lời rồi mới bị alignment
        # chặn (`A22-ALIGN-*`) — tức chặn SAU khi một con số đã tồn tại. Nay
        # tính chất "proxy của một cửa sổ chưa xác nhận" nằm trong catalog, nên
        # phép cộng bị từ chối NGAY ở khâu lập kế hoạch với lý do nói về đại
        # lượng ("cộng qua các đợt thu sẽ tính trùng cùng một lượt bán") thay vì
        # về sự lệch giữa câu hỏi và câu trả lời.
        #
        # Hai bảo đảm của ca này KHÔNG đổi: không bao giờ `A-ALLOW`, và không
        # bao giờ thay bằng `listing_count`. `expected_action` vẫn là `clarify`
        # vì vẫn còn một câu hỏi kế bên trả lời được (trung vị).
        "allowed_rule_ids": ["A22-ALIGN-MEASURE", "A19-AGGREGATION"],
        "forbidden_rule_ids": ["A-ALLOW"],
        "forbidden_analytical_kind": "listing_count",
        "expected_semantic_refs": ["measure.monthly_sold", "entity.listing"],
    },
    40: {
        "complexity_level": "L3",
        "answerability_class": "C1",
        "status": "provider_required",
    },
}


_INTENT = re.compile(r"Intent mong đợi:\**\s*`?([a-z_]+)`?")


def _expected_intents() -> tuple[dict[int, str], dict[int, str]]:
    """Read "Intent mong đợi" per testcase, keeping only real intents.

    The labels are parsed from the source document rather than restated here:
    a second copy drifts from the document the moment QA edits it, and the drift
    is invisible.

    A label is kept only when the registry actually has that intent. The
    document contains ``entity_resolution``, which names a mechanism rather than
    an intent -- scoring a parser against a label it can never emit would report
    a permanent failure that no fix could clear. Rejected labels are returned
    separately so they are reported, not silently dropped.
    """
    from gladiators.domain.intent_registry import default_registry

    known = set(default_registry().names())
    kept: dict[int, str] = {}
    rejected: dict[int, str] = {}
    current: int | None = None
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        heading = _HEADING.match(line)
        if heading:
            current = int(heading.group(1))
            continue
        found = _INTENT.search(line)
        if current is not None and found and current not in kept and current not in rejected:
            label = found.group(1)
            (kept if label in known else rejected)[current] = label
    return kept, rejected


def build() -> list[dict[str, object]]:
    cases: dict[int, str] = {}
    current: int | None = None
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        heading = _HEADING.match(line)
        if heading:
            current = int(heading.group(1))
            continue
        if current is not None and "Câu hỏi:" in line:
            if current in cases:
                raise ValueError(f"TC{current:02d} có nhiều hơn một câu hỏi")
            cases[current] = _question_text(line)

    intents, rejected_intents = _expected_intents()

    expected_ids = set(range(1, 41))
    if set(cases) != expected_ids or set(CONTRACTS) != expected_ids:
        raise ValueError(
            f"Suite phải đủ TC01–TC40; questions={sorted(cases)}, "
            f"contracts={sorted(CONTRACTS)}"
        )

    if rejected_intents:
        # Loud, not silent: a label the registry does not know means either the
        # document or the taxonomy moved, and both need a human to reconcile.
        for number, label in sorted(rejected_intents.items()):
            print(f"  [bỏ nhãn] TC{number:02d}: '{label}' không có trong intent registry")

    suite = []
    for number in sorted(cases):
        contract = {
            "legacy_expected_intent": intents.get(number),
            "expected_action": None,
            "allowed_rule_ids": [],
            "forbidden_rule_ids": [],
            "forbidden_analytical_kind": None,
            "expected_semantic_refs": [],
            "oracle_ref": None,
            "status": "executable",
            **CONTRACTS[number],
        }
        suite.append(
            {
                "id": f"tc{number:02d}",
                "source": "docs/qa/DR TASK 1407.md",
                "question": cases[number],
                **contract,
            }
        )
    return suite


def main() -> None:
    OUTPUT.write_text(
        json.dumps(build(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(build())} cases to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
