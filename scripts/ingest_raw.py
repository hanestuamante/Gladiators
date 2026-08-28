#!/usr/bin/env python3
"""Nhận một đợt dữ liệu thô vào kho bất biến, kèm mốc thời gian.

    PYTHONPATH=src python scripts/ingest_raw.py --source raw_extra_data --label "extra data 27/08"
    PYTHONPATH=src python scripts/ingest_raw.py --list

Kho nằm ở ``data/raw_snapshots/<ingested_at>/``. Ba tính chất, và cả ba đều là lý
do nó tồn tại:

* **Bất biến.** Đợt đã nhận thì không sửa. Muốn sửa thì nhận một đợt mới. Đây là
  "persistent immutable staging area" của Functional Data Engineering: raw rơi
  vào một lần và ở đó mãi, nên mọi bản dữ liệu về sau **dựng lại được từ đầu**.
* **Có mốc.** ``INGESTION.json`` ghi nhận lúc nào, từ đâu, và hash từng file. Một
  đợt raw không biết lấy về lúc nào là một đợt không đối chiếu được với bất cứ
  thứ gì.
* **Giữ nguyên bố cục nguồn.** Không đổi tên, không dẹp thư mục, không hợp nhất.
  Sắp xếp lại lúc nhận là trộn một quyết định *diễn giải* vào một bước lẽ ra chỉ
  *sao chép* — và khi diễn giải đó sai thì không còn bản gốc để quay về.

``data/raw/`` cũ **không bị đụng**: pipeline hiện tại vẫn đọc đúng chỗ nó vẫn đọc.
Gộp hai bố cục ngay lúc này là đổi hai thứ cùng lúc, và khi có gì hỏng thì không
biết vì cái nào.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SNAPSHOT_DIRNAME = "raw_snapshots"
WATERMARK_NAME = "INGESTION.json"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inventory(root: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        found[relative] = {"bytes": path.stat().st_size, "sha256": _digest(path)}
    return found


def ingest(source: Path, data_root: Path, *, label: str = "",
           ingested_at: str | None = None) -> dict:
    stamp = ingested_at or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = data_root / SNAPSHOT_DIRNAME / stamp
    if target.exists():
        raise FileExistsError(f"đợt {stamp} đã tồn tại — kho là bất biến")

    staging = target.with_name(f".{stamp}.partial")
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(source, staging)

    inventory = _inventory(staging)
    watermark = {
        "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshot_id": stamp,
        "source": str(source),
        "label": label,
        "file_count": len(inventory),
        "total_bytes": sum(item["bytes"] for item in inventory.values()),
        "files": inventory,
    }
    (staging / WATERMARK_NAME).write_text(
        json.dumps(watermark, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    # Đổi tên nguyên tử: không ai đọc được một đợt đang chép dở.
    staging.rename(target)
    return watermark


def verify(snapshot: Path) -> tuple[str, ...]:
    """File đã lệch so với lúc nhận. Rỗng nghĩa là đợt này còn nguyên."""
    path = snapshot / WATERMARK_NAME
    if not path.exists():
        raise FileNotFoundError(f"không có {WATERMARK_NAME} trong {snapshot}")
    declared = json.loads(path.read_text(encoding="utf-8")).get("files") or {}
    drifted = []
    for relative, meta in declared.items():
        target = snapshot / relative
        if not target.exists() or _digest(target) != meta["sha256"]:
            drifted.append(relative)
    return tuple(sorted(drifted))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="", help="thư mục raw vừa nhận được")
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--label", default="")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--verify", default="", help="snapshot_id cần kiểm nguyên vẹn")
    args = parser.parse_args()

    data_root = ROOT / args.data_root
    snapshots = data_root / SNAPSHOT_DIRNAME

    if args.list:
        if not snapshots.is_dir():
            print("(chưa có đợt nào)")
            return 0
        for path in sorted(snapshots.iterdir()):
            if not path.is_dir() or path.name.startswith("."):
                continue
            mark = json.loads((path / WATERMARK_NAME).read_text(encoding="utf-8"))
            print(f"{mark['snapshot_id']}  {mark['ingested_at']}  "
                  f"{mark['file_count']} file  {mark['total_bytes']:,} B  {mark['label']}")
        return 0

    if args.verify:
        drifted = verify(snapshots / args.verify)
        print(json.dumps({
            "snapshot_id": args.verify, "intact": not drifted, "drifted": list(drifted),
        }, ensure_ascii=False, indent=2))
        return 1 if drifted else 0

    if not args.source:
        parser.error("cần --source, --list hoặc --verify")
    watermark = ingest(ROOT / args.source, data_root, label=args.label)
    print(json.dumps(
        {key: value for key, value in watermark.items() if key != "files"},
        ensure_ascii=False, indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
