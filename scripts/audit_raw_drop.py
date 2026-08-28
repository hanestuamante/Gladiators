#!/usr/bin/env python3
"""Đối chiếu một đợt raw mới với hợp đồng mà pipeline đang đòi.

    PYTHONPATH=src python scripts/audit_raw_drop.py --snapshot <snapshot_id>

Câu hỏi nó trả lời: *"đợt dữ liệu này có dựng được một bản dataset không, và nếu
được thì mất gì?"* — bằng một bảng ở mức **cột**, không bằng cảm nhận ở mức file.

Vì sao cần: nhìn ở mức file thì đợt 27/08 trông như một bản nâng cấp (nhiều
listing hơn, nhiều ngày hơn). Nhìn ở mức cột thì nó **thiếu tên brand** và
**thiếu hẳn một dataset**, nên dựng dataset từ nó sẽ ra một bản trả lời được ÍT
câu hơn bản đang chạy. Một "nâng cấp" làm hệ trả lời ít đi mà không ai thấy trước
là đúng lớp lỗi kiến trúc này tồn tại để chặn.

**Script chỉ QUAN SÁT.** Nó đề xuất ứng viên đổi tên bằng khớp gần đúng và
**không tự áp** — cùng lý do với sổ bảo trì ở WP-B11: một tên gần giống bị đoán
thành tên khác là lớp lỗi tệ nhất của hệ này, và ở đây nó sẽ đổi tên một cột dữ
liệu.

Chính lần chạy đầu đã chứng minh điều đó. Bốn ứng viên có điểm giống cao mà **sai
nếu áp mù**::

    brand            → brand_id            (0.769)   TÊN ≠ MÃ
    original_category_name → global_category_id (0.65)  TÊN ≠ MÃ
    shop_slug        → shop_logo           (0.778)   slug ≠ URL ảnh
    shop_category_id → shopee_category_id  (0.941)   kệ shop ≠ danh mục sàn

Cái cuối đáng sợ nhất: 0,941 là điểm rất cao, và nó đề xuất đúng phép nhầm mà
``INV-SHELF-NOT-PLATFORM-CATEGORY`` đã tồn tại để cấm. Một phép khớp chuỗi không
biết gì về bất biến; con người thì biết.

Vì vậy ứng viên nào lệch nhau ở hậu tố ``_id`` được gắn cờ ``name_vs_id`` — không
phải để loại nó, mà để người duyệt nhìn đúng chỗ trước tiên.
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gladiators.data.pipeline import DATASETS  # noqa: E402

# Đợt mới đặt tên file theo bảng nguồn, đợt cũ theo dataset của pipeline. Ánh xạ
# này là phần DUY NHẤT đoán ở mức file; mọi thứ còn lại suy ra từ cột thật.
FILE_TO_DATASET = {
    "products": "products",
    "products_timeseries": "products",
    "shop_info": "shop_info",
    "categories": "category_list",
    "product_categories": "product_categories",
}

MIN_SIMILARITY = 0.65

_ID_SUFFIXES = ("_id", "_ids", "id")


def _is_name_vs_id(expected: str, candidate: str) -> bool:
    def looks_like_id(name: str) -> bool:
        return name.endswith(_ID_SUFFIXES)

    return looks_like_id(expected) != looks_like_id(candidate)


def reference_schema(raw_root: Path) -> dict[str, set[str]]:
    """Cột mà pipeline ĐANG đọc, lấy từ chính đợt raw cũ."""
    schema: dict[str, set[str]] = {}
    for dataset, filename in DATASETS.items():
        matches = sorted(raw_root.rglob(f"dataset={dataset}/**/{filename}"))
        if matches:
            schema[dataset] = set(
                pd.read_csv(matches[0], nrows=1, dtype=str).columns,
            )
    return schema


def drop_schema(snapshot: Path) -> dict[str, set[str]]:
    """Cột có trong đợt mới, gom theo dataset của pipeline."""
    schema: dict[str, set[str]] = {}
    extra: dict[str, set[str]] = {}
    empty: list[str] = []
    for path in sorted(snapshot.rglob("*.csv")):
        stem = path.stem.rsplit("_", 1)[0]
        try:
            columns = set(pd.read_csv(path, nrows=1, dtype=str).columns)
        except pd.errors.EmptyDataError:
            # File rỗng là một sự thật về đợt dữ liệu, không phải một sự cố đọc.
            # Đợt 27/08 có public/test_*.csv đúng 2 byte. Nuốt im lặng thì không
            # ai biết nó rỗng; để nó ném thì cả bảng đối chiếu không chạy được.
            empty.append(path.relative_to(snapshot).as_posix())
            continue
        dataset = FILE_TO_DATASET.get(stem)
        if dataset:
            schema.setdefault(dataset, set()).update(columns)
        else:
            extra[stem] = columns
    for name, columns in extra.items():
        schema[f"__extra__:{name}"] = columns
    schema["__empty__"] = set(empty)
    return schema


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def audit(raw_root: Path, snapshot: Path) -> dict:
    reference = reference_schema(raw_root)
    drop = drop_schema(snapshot)
    # Mọi cột có ở BẤT KỲ đâu trong đợt mới: một cột "mất" ở dataset này có thể
    # chỉ là đã chuyển sang bảng khác, và báo nó mất là gửi người đọc đi sai
    # hướng.
    empty_files = sorted(drop.pop("__empty__", set()))
    everywhere: dict[str, list[str]] = {}
    for name, columns in drop.items():
        for column in columns:
            everywhere.setdefault(column, []).append(name.replace("__extra__:", ""))

    datasets: dict[str, dict] = {}
    for dataset, expected in sorted(reference.items()):
        present = drop.get(dataset, set())
        missing = sorted(expected - present)
        moved, renamed, absent = [], [], []
        for column in missing:
            if column in everywhere:
                moved.append({"column": column, "found_in": everywhere[column]})
                continue
            candidates = difflib.get_close_matches(
                column, list(everywhere), n=1, cutoff=MIN_SIMILARITY,
            )
            if candidates:
                candidate = candidates[0]
                renamed.append({
                    "column": column, "candidate": candidate,
                    "found_in": everywhere[candidate],
                    "similarity": round(
                        difflib.SequenceMatcher(None, column, candidate).ratio(), 3,
                    ),
                    # Một bên là mã, bên kia là tên: điểm giống cao nhưng nghĩa
                    # khác hẳn. Đây là lớp nhầm đắt nhất vì nó im lặng — câu trả
                    # lời sẽ in ra một con số ở chỗ lẽ ra là một cái tên.
                    "name_vs_id": _is_name_vs_id(column, candidate),
                })
            else:
                absent.append(column)
        datasets[dataset] = {
            "expected_columns": len(expected),
            "present": len(expected) - len(missing),
            "moved_to_another_table": moved,
            "rename_candidates": renamed,
            "absent_everywhere": absent,
            "satisfiable": not absent and bool(present),
        }

    for dataset in sorted(set(DATASETS) - set(reference)):
        datasets[dataset] = {"satisfiable": False, "absent_everywhere": ["<toàn bộ dataset>"]}
    for dataset, spec in datasets.items():
        if dataset in reference and not drop.get(dataset):
            spec["satisfiable"] = False
            spec["absent_everywhere"] = ["<toàn bộ dataset>"]

    return {
        # Đường dẫn ngoài repo vẫn phải báo cáo được: giả định "mọi thứ nằm dưới
        # ROOT" làm script chết bằng ValueError khi ai đó trỏ vào một thư mục
        # tạm — kể cả chính bộ test của nó.
        "snapshot": _display(snapshot),
        "reference_raw": _display(raw_root),
        "datasets": datasets,
        "empty_files": empty_files,
        "new_tables_pipeline_does_not_know": sorted(
            name.replace("__extra__:", "")
            for name in drop if name.startswith("__extra__:")
        ),
        "verdict": (
            "dựng được dataset"
            if all(spec.get("satisfiable") for spec in datasets.values())
            else "KHÔNG dựng được dataset đầy đủ — xem absent_everywhere"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, help="snapshot_id trong data/raw_snapshots/")
    parser.add_argument("--raw", default="data/raw", help="đợt raw cũ, dùng làm chuẩn")
    parser.add_argument("--out", default="artifacts/raw_drop_audit.json")
    args = parser.parse_args()

    snapshot = ROOT / "data" / "raw_snapshots" / args.snapshot
    report = audit(ROOT / args.raw, snapshot)

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{'dataset':<22}{'cột đủ':>9}{'chuyển bảng':>13}{'ứng viên đổi tên':>19}{'VẮNG HẲN':>10}")
    for dataset, spec in report["datasets"].items():
        print(f"{dataset:<22}"
              f"{spec.get('present', 0)}/{spec.get('expected_columns', 0):<7}"
              f"{len(spec.get('moved_to_another_table', [])):>13}"
              f"{len(spec.get('rename_candidates', [])):>19}"
              f"{len(spec.get('absent_everywhere', [])):>10}")
    suspicious = [
        candidate
        for spec in report["datasets"].values()
        for candidate in (spec.get("rename_candidates") or [])
        if candidate.get("name_vs_id")
    ]
    if suspicious:
        print()
        print("Ứng viên TÊN↔MÃ — điểm giống cao nhưng nghĩa khác hẳn:")
        for candidate in suspicious:
            print(f"   {candidate['column']:<24} → {candidate['candidate']:<24}"
                  f" ({candidate['similarity']})")
    print()
    print("Bảng mới pipeline chưa biết:", ", ".join(report["new_tables_pipeline_does_not_know"]) or "—")
    if report["empty_files"]:
        print("File RỖNG trong đợt:", ", ".join(report["empty_files"]))
    print("KẾT LUẬN:", report["verdict"])
    for dataset, spec in report["datasets"].items():
        for column in spec.get("absent_everywhere", []):
            print(f"   {dataset}: thiếu {column}")
    print(f"\nChi tiết: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
