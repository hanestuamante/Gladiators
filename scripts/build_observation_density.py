"""W29 — đo MẬT ĐỘ QUAN SÁT của từng cột, theo ngày và theo thị trường.

Vì sao artifact này tồn tại (Spec3008 §16.1):

``median rating vn 03/07`` = **4.9236** trên 668 quan sát ở bộ đóng băng, và
**4.9300** trên **5** quan sát ở bộ 20 ngày. Cả hai đi qua gate ✓, compiler ✓,
executor ✓, evidence ✓, verifier ✓, A22 ✓. Không có gì trong hệ phát biểu được
rằng con số thứ hai là một mẫu 0,4% trình bày như một phát biểu về thị trường.

Nguyên nhân gốc: catalog khai *một measure ĐO CÁI GÌ*, không khai *nó ĐƯỢC QUAN
SÁT NHƯ THẾ NÀO*. Trên bộ 3 ngày hai thứ đó trùng nhau nên khoảng trống không
lộ.

``mode`` suy ra bằng LUẬT ĐO ĐƯỢC, không bằng ý kiến — xem ``_mode_of``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gladiators.data.dataset_version import compute_dataset_version  # noqa: E402

SCHEMA_VERSION = "observation-density.v1"
FILENAME = "observation_density.json"

# Coi như phủ toàn bộ phạm vi.
COVERAGE_DENSE = 0.95

# Dưới mức này, một tổng hợp KHÔNG phải một phát biểu về phạm vi.
#
# NGƯỠNG ĐƯỢC CHỌN, không phải một số đo. Căn cứ: một trung vị tính trên dưới
# nửa phạm vi không phải một phát biểu về phạm vi đó, bất kể mẫu có đại diện hay
# không — vì hệ **không biết** nó có đại diện không và không có cách nào biết.
# Đây là ranh giới của thứ NÓI ĐƯỢC, không phải một ngưỡng thống kê. Ghi rõ ở
# đây để người sau không đi tìm một cơ sở thống kê không tồn tại.
COVERAGE_REFUSE = 0.50

# Artifact có cột đo được. Bỏ qua bảng tra cứu (category_platform) vì chúng
# không có grain thời gian.
SOURCES = (
    "products_clean.csv",
    "product_snapshot_metrics.csv",
    "shop_stats_clean.csv",
)


def _mode_of(by_date: dict[str, float], overall: float, entities: int, observed: int) -> str:
    """``panel`` | ``point_in_time``.

    * mọi đợt thu đều dày  ⇒ ``panel``;
    * đúng MỘT đợt thu dày, và tổng quan sát xấp xỉ số thực thể ⇒ ``point_in_time``;
    * còn lại ⇒ ``point_in_time`` (phía an toàn).

    Phía an toàn là ``point_in_time`` chứ không phải ``panel``: đoán nhầm thành
    panel làm hệ phát biểu về một phạm vi nó không quan sát; đoán nhầm thành
    point_in_time chỉ làm nó hỏi lại.
    """
    if not by_date:
        return "point_in_time"
    if all(value >= COVERAGE_DENSE for value in by_date.values()):
        return "panel"
    dense_days = sum(1 for value in by_date.values() if value >= COVERAGE_DENSE)
    if dense_days <= 1 and entities and abs(observed - entities) <= max(2, entities * 0.05):
        return "point_in_time"
    return "point_in_time"


def build(data_dir: Path) -> dict:
    columns: dict[str, dict] = {}
    for artifact in SOURCES:
        path = data_dir / artifact
        if not path.exists():
            continue                      # artifact tuỳ chọn chưa thu (W31)
        frame = pd.read_csv(path, low_memory=False)
        if "date" not in frame.columns:
            continue
        key = (
            "product_listing_key" if "product_listing_key" in frame.columns
            else "shop_id" if "shop_id" in frame.columns else None
        )
        entities = int(frame[key].nunique()) if key else 0
        by_day = frame.groupby(frame["date"].astype(str))
        for column in frame.columns:
            if not (column.endswith("_num") or column.endswith("_count")):
                continue
            series = frame[column]
            if series.notna().sum() == 0:
                continue
            per_date = {
                str(day): round(float(group[column].notna().mean()), 6)
                for day, group in by_day
            }
            per_country = {}
            if "country_code" in frame.columns:
                per_country = {
                    str(market): round(float(group[column].notna().mean()), 6)
                    for market, group in frame.groupby("country_code")
                }
            overall = round(float(series.notna().mean()), 6)
            columns[f"{artifact}.{column}"] = {
                "mode": _mode_of(per_date, overall, entities, int(series.notna().sum())),
                "overall_coverage": overall,
                "by_date": per_date,
                "by_country": per_country,
            }
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_version": compute_dataset_version(data_dir),
        "coverage_dense": COVERAGE_DENSE,
        "coverage_refuse": COVERAGE_REFUSE,
        "columns": columns,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(ROOT / "data" / "processed"))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    payload = build(data_dir)
    out = Path(args.output) if args.output else data_dir / FILENAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    modes: dict[str, int] = {}
    for entry in payload["columns"].values():
        modes[entry["mode"]] = modes.get(entry["mode"], 0) + 1
    print(json.dumps({
        "schema_version": payload["schema_version"],
        "dataset_version": payload["dataset_version"],
        "columns": len(payload["columns"]),
        "modes": modes,
        "output": str(out),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
