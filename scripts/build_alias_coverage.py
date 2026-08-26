#!/usr/bin/env python3
"""Alias coverage report — ultimate solution §3.2.

CI fails when an exposed catalogue object cannot be reached from a question:
a measure that exists but has no Vietnamese alias is present on paper and
absent in practice. Collisions are reported rather than resolved -- a surface
binding two refs must return ambiguity, never a winner picked by ref-name order.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gladiators.domain.alias_index import PREFERRED_REF_BY_SURFACE, default_alias_index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/alias_coverage.json")
    parser.add_argument("--check", action="store_true", help="exit 1 on any gap")
    args = parser.parse_args()

    coverage = default_alias_index().coverage()
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "index_hash": coverage["index_hash"],
        "exposed_objects": coverage["exposed_objects"],
        "missing_vietnamese": len(coverage["missing_vietnamese"]),
        "missing_en_or_id": len(coverage["missing_en_or_id"]),
        "collisions": len(coverage["collisions"]),
        # WP-A4.1: một surface mơ hồ mà KHÔNG có ưu tiên thì binder bỏ qua nó —
        # chọn bừa một ref là trả lời một câu hỏi khác trong im lặng. Hai con số
        # dưới đây phải bằng nhau; lệch nghĩa là có surface bị bỏ rơi.
        "preferred_surfaces": len(PREFERRED_REF_BY_SURFACE),
        "collisions_without_preference": sorted(
            set(coverage["collisions"]) - set(PREFERRED_REF_BY_SURFACE)
        ),
    }, ensure_ascii=False, indent=2))

    gaps = coverage["missing_vietnamese"] + coverage["missing_en_or_id"]
    if args.check and gaps:
        for ref in gaps:
            print(f"  MISSING ALIAS  {ref}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
