"""Build the executable DR 26/07 regression suite from the checked-in source doc.

The prose document is the source of truth for question text.  Expected routing
metadata below is deliberately conservative: data denotations that still need a
human/provider oracle are labelled instead of being invented.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "DR TASK 1407.md"
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
        "allowed_rule_ids": ["A16-CROSS-CURRENCY", "A22-ALIGN-MEASURE"],
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
        "status": "invalid_fixture_premise",
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
        "allowed_rule_ids": ["A22-ALIGN-MEASURE"],
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

    expected_ids = set(range(1, 41))
    if set(cases) != expected_ids or set(CONTRACTS) != expected_ids:
        raise ValueError(
            f"Suite phải đủ TC01–TC40; questions={sorted(cases)}, "
            f"contracts={sorted(CONTRACTS)}"
        )

    suite = []
    for number in sorted(cases):
        contract = {
            "legacy_expected_intent": None,
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
                "source": "docs/DR TASK 1407.md",
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
