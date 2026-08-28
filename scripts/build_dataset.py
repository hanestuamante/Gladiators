#!/usr/bin/env python3
"""Dựng một bản dữ liệu, đặt tên cho nó, và (tuỳ chọn) trỏ hệ vào nó.

    PYTHONPATH=src python scripts/build_dataset.py --verify-against data/processed
    PYTHONPATH=src python scripts/build_dataset.py --publish
    PYTHONPATH=src python scripts/build_dataset.py --publish --activate

Đây là notebook ``notebooks/pipeline/data_pipeline.ipynb`` ở dạng chạy được không
cần người bấm. Logic làm sạch **không đổi một dòng** — nó nằm nguyên trong
``gladiators.data.pipeline``, và notebook giờ gọi cùng một hàm đó, nên không có
bản thứ hai để trôi.

Ba thứ nó thêm so với "Run All":

* **Tái lập kiểm được** — ``--verify-against`` dựng lại rồi so **schema và giá
  trị** với một thư mục đã có. Không có bước này thì "notebook vẫn chạy đúng" là
  một niềm tin, không phải một phép đo.
* **Đặt tên** — ``--publish`` chép kết quả vào ``data/versions/<version_id>/``
  kèm manifest. Có tên thì mới có thứ để CI gọi, để so, để rollback về.
* **Nạp nóng** — ``--activate`` đổi con trỏ ``data/CURRENT``. Server đọc con trỏ
  lúc dựng repository, nên đổi bản không cần dựng lại tiến trình.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gladiators.data.pipeline import run_pipeline  # noqa: E402
from gladiators.data.versions import (  # noqa: E402
    VERSIONED_ARTIFACTS,
    compute_version_id,
    list_versions,
    publish,
    switch,
)


def build(raw_dir: Path, out_dir: Path) -> dict:
    """Chạy pipeline rồi sinh luôn coverage manifest.

    ``semantic_coverage_manifest.json`` mô tả 219 header VẬT LÝ của chính bản dữ
    liệu này, nên nó thuộc về bản — không phải một file dùng chung nằm ngoài.
    Thiếu nó, ``validate_artifacts`` từ chối bản vừa publish, và một bản không
    phục vụ được thì đặt tên cho nó cũng vô nghĩa.
    """
    from gladiators.data.coverage import write_manifest

    out_dir.mkdir(parents=True, exist_ok=True)
    report = run_pipeline(raw_dir, out_dir)
    write_manifest(out_dir)
    return report


def compare(built: Path, reference: Path, *, rtol: float = 1e-6) -> dict:
    """So hai thư mục dữ liệu: schema và giá trị, KHÔNG so byte.

    So byte là ngưỡng sai cho cột số thực. Đo được: dựng lại từ cùng một raw cho
    ra ``products_clean`` và ``product_snapshot_metrics`` **0 cột khác giá trị**
    (chỉ khác cách in số), còn ``product_transition_metrics.rating_change`` lệch
    81/2184 dòng ở mức **1e-13 tương đối** — ``5.722625162629669e-05`` so với
    ``5.722625162540851e-05``. Đó là trôi phiên bản numpy/pandas kể từ lần dựng
    14/07, không phải đổi logic.

    Một phép kiểm đỏ ở mỗi lần nâng thư viện là một phép kiểm sẽ bị tắt. Ngưỡng
    đúng: **schema và số dòng phải khớp tuyệt đối**, cột không phải số phải khớp
    tuyệt đối, cột số khớp trong dung sai — và **báo cáo độ lệch lớn nhất** để
    dung sai đó kiểm lại được, chứ không phải một tấm thảm để quét bụi vào.

    ``rtol = 1e-6`` không phải con số nới cho tới khi xanh. Độ lệch đo được là
    **1,6e-9** trên đúng 1/2184 dòng — dư 2,6 bậc so với ngưỡng. Với
    ``rating_change`` cỡ 5,7e-5 trên thang 1–5 sao, sai số tuyệt đối ~1e-13 nằm
    dưới mọi ngưỡng có nghĩa nghiệp vụ, trong khi một thay đổi LOGIC sẽ dịch chữ
    số có nghĩa chứ không dịch chữ số thứ chín. ``max_rel_deviation`` in ra ở mọi
    lần chạy, nên biên đó tự kiểm được: nó bò lên gần ngưỡng là thấy ngay.
    """
    import numpy as np
    import pandas as pd

    mismatches: list[dict] = []
    worst = 0.0
    for name in VERSIONED_ARTIFACTS:
        left, right = built / name, reference / name
        if not left.exists() or not right.exists():
            mismatches.append({"artifact": name, "reason": "thiếu file"})
            continue
        a = pd.read_csv(left, low_memory=False)
        b = pd.read_csv(right, low_memory=False)
        if a.shape != b.shape or list(a.columns) != list(b.columns):
            mismatches.append({
                "artifact": name, "reason": "schema khác",
                "built": list(a.shape), "reference": list(b.shape),
            })
            continue
        for column in a.columns:
            if pd.api.types.is_numeric_dtype(a[column]) and pd.api.types.is_numeric_dtype(b[column]):
                x, y = a[column].to_numpy(float), b[column].to_numpy(float)
                close = np.isclose(x, y, rtol=rtol, atol=0.0, equal_nan=True)
                if not close.all():
                    scale = np.where(np.abs(y) > 0, np.abs(y), 1.0)
                    deviation = float(np.nanmax(np.abs(x - y) / scale))
                    worst = max(worst, deviation)
                    mismatches.append({
                        "artifact": name, "column": column,
                        "rows": int((~close).sum()), "max_rel_deviation": deviation,
                    })
            elif not a[column].astype(str).equals(b[column].astype(str)):
                mismatches.append({
                    "artifact": name, "column": column,
                    "rows": int((a[column].astype(str) != b[column].astype(str)).sum()),
                    "reason": "cột không phải số, khác giá trị",
                })
    return {
        "reproducible": not mismatches,
        "rtol": rtol,
        "max_rel_deviation": worst,
        "mismatches": mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/raw", help="thư mục raw đầu vào")
    parser.add_argument("--out", default="", help="ghi vào đây; mặc định là thư mục tạm")
    parser.add_argument("--verify-against", default="",
                        help="dựng lại rồi so schema+giá trị với thư mục này")
    parser.add_argument("--publish", action="store_true",
                        help="chép kết quả vào data/versions/<id>/ kèm manifest")
    parser.add_argument("--activate", action="store_true",
                        help="đổi con trỏ data/CURRENT sang bản vừa publish")
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--notes", default="")
    parser.add_argument("--rtol", type=float, default=1e-6,
                        help="dung sai tương đối cho cột số khi --verify-against")
    parser.add_argument("--fail-on-error", action="store_true",
                        help="thoát khác 0 khi pipeline báo lỗi chất lượng dữ liệu")
    parser.add_argument("--list", action="store_true", help="liệt kê các bản đã có")
    args = parser.parse_args()

    data_root = ROOT / args.data_root
    if args.list:
        for version in list_versions(data_root):
            manifest = version.manifest
            print(f"{version.version_id}  {manifest.get('built_at', '?')}  "
                  f"raw={manifest.get('raw_snapshot') or '?'}  {manifest.get('notes', '')}")
        return 0

    raw_dir = ROOT / args.raw
    temporary = None
    if args.out:
        out_dir = ROOT / args.out
    else:
        temporary = tempfile.mkdtemp(prefix="gladiators-build-")
        out_dir = Path(temporary)

    try:
        report = build(raw_dir, out_dir)
        version_id = compute_version_id(out_dir)
        result = {
            "raw": str(raw_dir.relative_to(ROOT)),
            "version_id": version_id,
            "status": report["status"],
            "rows": report["rows"],
            "severity_counts": report["severity_counts"],
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

        if args.verify_against:
            reference = ROOT / args.verify_against
            verdict = compare(out_dir, reference, rtol=args.rtol)
            result["verify_against"] = str(reference.relative_to(ROOT))
            result.update(verdict)

        if args.publish:
            version = publish(
                out_dir, data_root,
                raw_snapshot=str(raw_dir.relative_to(ROOT)),
                notes=args.notes,
            )
            result["published_to"] = str(version.root.relative_to(ROOT))
            if args.activate:
                switch(data_root, version.version_id)
                result["activated"] = True

        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.verify_against and not result.get("reproducible", True):
            return 1
        if args.fail_on_error and report["status"] == "failed":
            return 2
        return 0
    finally:
        if temporary and not args.out:
            shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
