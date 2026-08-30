#!/usr/bin/env python3
"""Chỉ mục giá trị cho ba chiều — Spec2308 §WP-A4.3, schema v2 ở SolutionSpec2808 §2.3.

Chỉ **ba** dimension, vì chỉ chúng có số giá trị đủ nhỏ và ổn định. Khoá theo
``country`` vì cùng một tên có thể chỉ tồn tại ở một thị trường.

    PYTHONPATH=src python scripts/build_value_index.py

A4-R3: file sinh ra **không commit** vào repo — nằm trong ``artifacts/`` đã được
gitignore. CI dựng lại trước khi chạy eval.

**Phạm vi import (W1.3):** script này không import *tầng ngữ nghĩa* của
``gladiators`` — chỉ mục không được thừa hưởng giả định nào của hệ bị kiểm.
Nhưng nó **phải** dùng chung hai hàm thuần: ``value_probe._fold`` (khoá của chỉ
mục phải fold đúng như lúc tra) và ``compute_dataset_version`` (hai hàm băm khác
nhau là đúng thứ lỗi mà W1.3 sửa — ``27de9bff…`` và ``a821e39d…`` từng cùng chỉ
một bộ dữ liệu mà không chỗ nào kiểm lệch).

**Schema v2 (W1.1):** ``values[ref][country]`` là ``{folded: original}``. Bản v1
chỉ giữ bản đã fold, nên literal ``"bibica"`` đi thẳng vào predicate và
``brand = 'bibica'`` trả 0 dòng trong khi dữ liệu ghi ``Bibica`` — đáp án là 96.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gladiators.agent.value_probe import INDEX_SCHEMA_VERSION, _fold  # noqa: E402
from gladiators.data.dataset_version import compute_dataset_version  # noqa: E402

DATA = ROOT / "data" / "processed"

# Ba chiều, và cột vật lý của chúng. Giữ ở đây thay vì suy từ catalog: phần
# NGỮ NGHĨA vẫn không được import — chỉ mục không thừa hưởng giả định nào của
# hệ bị kiểm.
SOURCES: tuple[tuple[str, str, str], ...] = (
    ("dim.platform_category_name", "category_platform_clean.csv", "display_category_name"),
    ("dim.brand", "products_clean.csv", "brand"),
    ("dim.shop_name", "shop_info_clean.csv", "shop_name"),
)


# CHỆCH KHỎI SPEC CÓ CHỦ ĐÍCH — spec §2.3 nói "hai tên gốc fold về cùng khoá ⇒
# script fail". Chạy trên dataset thật thì luật đó tự phản: "Trang điểm mắt" và
# "Trang điểm mặt" (dấu tiếng Việt là thứ DUY NHẤT phân biệt, mà _fold bỏ dấu)
# đụng nhau ngay lần dựng đầu, nên chỉ mục không bao giờ dựng được — mâu thuẫn
# với chính nghiệm thu §21 của spec. Loại khoá khỏi index cũng sai:
# missing_values sẽ chấm một danh mục CÓ THẬT là A-VALUE-NOT-FOUND.
#
# Giữ đúng TINH THẦN của luật (ambiguity phải lộ lúc dựng; không bao giờ chọn
# thầm): khoá đụng độ vào mục "ambiguous" riêng — TỒN TẠI nhưng KHÔNG BIND được.
# bind_values bỏ qua nó (câu rơi về hành vi gom nhóm như hôm nay), còn
# missing_values/named_but_absent không chấm nó là vắng mặt.


def build(data_dir: Path = DATA) -> dict:
    values: dict[str, dict[str, dict[str, str]]] = {}
    ambiguous: dict[str, dict[str, dict[str, list[str]]]] = {}
    for ref, artifact, column in SOURCES:
        frame = pd.read_csv(data_dir / artifact)
        if column not in frame.columns or "country_code" not in frame.columns:
            continue
        per_country: dict[str, dict[str, str]] = {}
        per_country_ambiguous: dict[str, dict[str, list[str]]] = {}
        for country, group in frame.groupby("country_code"):
            candidates: dict[str, set[str]] = {}
            for raw in group[column].dropna():
                original = str(raw).strip()
                if original:
                    candidates.setdefault(_fold(original), set()).add(original)
            mapping = {
                folded: next(iter(originals))
                for folded, originals in candidates.items() if len(originals) == 1
            }
            collided = {
                folded: sorted(originals)
                for folded, originals in candidates.items() if len(originals) > 1
            }
            per_country[str(country)] = dict(sorted(mapping.items()))
            if collided:
                per_country_ambiguous[str(country)] = dict(sorted(collided.items()))
        values[ref] = per_country
        if per_country_ambiguous:
            ambiguous[ref] = per_country_ambiguous
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "dataset_version": compute_dataset_version(data_dir),
        "values": values,
        "ambiguous": ambiguous,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/value_index.json")
    # Bản dữ liệu nào thì dựng chỉ mục cho bản đó. Ghim cứng ``data/processed``
    # khiến một bản mới không bao giờ chạy được: runtime kiểm dataset_version
    # của chỉ mục khớp repository và fail-closed khi lệch — đúng thiết kế, nhưng
    # chỉ có nghĩa nếu chỉ mục dựng được cho bản đang phục vụ.
    parser.add_argument("--data-dir", default=str(DATA))
    args = parser.parse_args()

    index = build(Path(args.data_dir))
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema_version": index["schema_version"],
        "dataset_version": index["dataset_version"],
        "refs": {ref: {c: len(v) for c, v in per.items()}
                 for ref, per in index["values"].items()},
        # In TO chứ không nuốt: mỗi cặp ở đây là một câu hỏi mà hệ sẽ không lọc
        # được bằng tên, và người vận hành phải biết điều đó từ lúc dựng.
        "ambiguous": index["ambiguous"],
        "output": str(out.relative_to(ROOT)) if out.is_relative_to(ROOT) else str(out),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
