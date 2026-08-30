"""Contract tests — benchmark accuracy v1 giữ đúng hợp đồng TC_formulation §4-§6.

Kiểm CẤU TRÚC và NIÊM PHONG: đủ 100 case đúng phân phối, schema hợp lệ, split
tách file, hash manifest khớp file thật, oracle không import gladiators, không
case nào sao chép suite regression hiện có.
"""
from __future__ import annotations

import ast
import hashlib
import json
import unicodedata
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BENCH = REPO / "eval" / "accuracy" / "v1"

DEV = json.loads((BENCH / "dev.json").read_text(encoding="utf-8"))
HOLDOUT = json.loads((BENCH / "holdout.json").read_text(encoding="utf-8"))
ALL = DEV + HOLDOUT
MANIFEST = json.loads((BENCH / "manifest.json").read_text(encoding="utf-8"))


def test_exactly_100_cases_with_the_declared_distribution():
    assert len(ALL) == 100
    by_class = {}
    for case in ALL:
        by_class[case["answerability"]] = by_class.get(case["answerability"], 0) + 1
    assert by_class == {
        "directly_answerable": 65, "needs_clarification": 15, "unanswerable": 20,
    }


def test_every_case_validates_against_the_schema():
    schema = json.loads((BENCH / "schema.json").read_text(encoding="utf-8"))
    required = set(schema["required"])
    for case in ALL:
        missing = required - set(case)
        assert not missing, f"{case['id']}: thiếu {missing}"
        assert case["answerability"] in (
            "directly_answerable", "needs_clarification", "unanswerable")
        assert case["expected_action"] in ("allow", "clarify", "abstain")
        for fact in case["expected_facts"]:
            for key in ("metric", "value", "value_type", "unit", "country",
                        "date_start", "date_end", "grain", "tolerance"):
                assert key in fact, f"{case['id']}: fact thiếu {key}"
            assert fact["value"] is not None, (
                f"{case['id']}: expected fact không được mang value null"
            )


def test_the_minimum_composition_floors_hold():
    groups = {}
    for case in ALL:
        groups.setdefault(case["paraphrase_group"], []).append(case)
    multi = [g for g, cases in groups.items() if len(cases) >= 2]
    assert len(multi) >= 20, f"cần ≥20 paraphrase group đa thành viên, có {len(multi)}"
    assert sum(1 for c in ALL if c["entity_text"]) >= 10
    assert sum(1 for c in ALL if "ranking" in c["category"]) >= 10
    assert sum(1 for c in ALL if c["category"] == "empty_result") >= 5
    languages = {c["language"] for c in ALL}
    assert {"vi", "vi_no_diacritic", "id", "en"} <= languages


def test_paraphrase_groups_never_straddle_the_split():
    """Hai cách diễn đạt của cùng câu ở hai split là leakage qua paraphrase."""
    split_of_group: dict[str, set] = {}
    for case in ALL:
        split_of_group.setdefault(case["paraphrase_group"], set()).add(case["split"])
    straddling = [g for g, splits in split_of_group.items() if len(splits) > 1]
    assert straddling == []


def test_manifest_hashes_match_the_sealed_files():
    for name, key in (("dev.json", "dev_sha256"), ("holdout.json", "holdout_sha256")):
        actual = hashlib.sha256((BENCH / name).read_bytes()).hexdigest()
        assert actual == MANIFEST[key], (
            f"{name} lệch hash manifest — fixture bị sửa ngoài quy trình "
            "(đổi hợp lệ phải kèm changelog + re-hash)"
        )


def test_the_contamination_status_is_declared_not_hidden():
    """Tác giả đã đọc implementation ⇒ benchmark PHẢI tự khai như vậy."""
    assert MANIFEST["status"] == "provisional_contaminated"
    assert "contamination_note" in MANIFEST and len(MANIFEST["contamination_note"]) > 100
    assert all(c["author_read_source_code_before_seal"] for c in ALL)


def test_the_oracle_imports_no_gladiators_module():
    tree = ast.parse((BENCH / "oracle.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            assert not name.startswith("gladiators"), (
                "oracle phải độc lập — không import gladiators"
            )


def test_every_answerable_case_with_numbers_carries_an_oracle_ref():
    for case in ALL:
        if case["answerability"] == "directly_answerable" and case["expected_facts"]:
            assert case["oracle"] and case["oracle"]["oracle_id"], case["id"]
            assert case["oracle"]["reproduction_ref"].endswith("oracle.py")


def test_unanswerable_cases_declare_a_refusal_reason_class():
    for case in ALL:
        if case["answerability"] == "unanswerable":
            assert case["expected_refusal_reason_class"], case["id"]


def test_clarify_cases_declare_the_missing_slot():
    for case in ALL:
        if case["answerability"] == "needs_clarification":
            assert case["expected_clarification_slots"], case["id"]


def _fold(text: str) -> str:
    lowered = str(text).lower().replace("đ", "d")
    stripped = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in stripped if unicodedata.category(ch) != "Mn")


def test_similarity_collisions_with_regression_suites_are_reported_not_deleted():
    """§4 dòng cuối: kiểm similarity với suite regression, BÁO collision —
    không tự xoá case. Câu trùng gần là hệ quả tất yếu của cùng một dataset
    hữu hạn; manifest ghi danh sách để người đọc trừ hao."""
    regression_questions = set()
    for suite in ("questions", "questions_v2", "questions_counting",
                  "questions_multiturn", "dr2607"):
        path = REPO / "eval" / f"{suite}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        for case in payload:
            for turn in case.get("turns") or [case]:
                if turn.get("question"):
                    regression_questions.add(_fold(turn["question"]).strip("?. "))
    collisions = []
    for case in ALL:
        for turn in case.get("turns") or [case]:
            question = turn.get("question")
            if question and _fold(question).strip("?. ") in regression_questions:
                collisions.append(case["id"])
    declared = set(MANIFEST.get("regression_collisions", []))
    assert set(collisions) == declared, (
        f"collision thực {sorted(set(collisions))} phải được KHAI trong manifest "
        f"(đang khai {sorted(declared)}) — báo cáo, không xoá"
    )
