"""W10.2 — cửa publish (SolutionSpec2808 §11.2).

Bốn ca lỗi lấy từ ``raw_extra_data`` THẬT — không gieo lỗi giả: một bảng khai
time series mà mỗi khoá có đúng một dòng, một cột toàn một giá trị, một file
rỗng, và một ngày khuyết giữa dải liên tục.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from gladiators.data.publish import publish_dataset
from conftest import DATA_DIR

REPO = Path(__file__).resolve().parents[1]
EXTRA = REPO / "raw_extra_data" / "datashopee"


def _manifest_for(directory: Path, **overrides) -> None:
    files = {}
    for path in sorted(directory.glob("*.csv")):
        files[path.name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "rows": max(sum(1 for _ in path.open(encoding="utf-8")) - 1, 0),
        }
    payload = {
        "source": "test", "exported_at": "2026-08-27T19:24:00", "files": files,
    }
    payload.update(overrides)
    (directory / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8",
    )


def _stage(tmp_path: Path, *names: str) -> Path:
    import shutil

    staging = tmp_path / "incoming"
    staging.mkdir()
    for name in names:
        source = next(EXTRA.glob(f"{name}_*.csv"))
        shutil.copy2(source, staging / source.name)
    return staging


# --- bước 1 · manifest ------------------------------------------------------

def test_no_manifest_is_refused_and_nothing_is_written(tmp_path):
    staging = _stage(tmp_path, "shop_info")
    result = publish_dataset(staging, quarantine_root=tmp_path / "q")
    assert result.status == "refused"
    assert result.issues[0].code == "manifest_missing"
    assert not (tmp_path / "q").exists()


def test_a_hash_mismatch_is_refused(tmp_path):
    staging = _stage(tmp_path, "shop_info")
    _manifest_for(staging)
    victim = next(staging.glob("shop_info_*.csv"))
    victim.write_bytes(victim.read_bytes() + b"\n")
    result = publish_dataset(staging, quarantine_root=tmp_path / "q")
    assert result.status == "refused"
    assert any(issue.code == "file_hash_mismatch" for issue in result.issues)


# --- bước 2/3 · bốn ca lỗi THẬT của raw_extra_data --------------------------

@pytest.mark.skipif(not EXTRA.exists(), reason="raw_extra_data chưa có trong checkout")
def test_the_fake_timeseries_is_quarantined_for_grain(tmp_path):
    """products_timeseries: 1276 dòng / 1276 item — đúng một dòng mỗi item.
    Tên bảng khai time series; join theo tên file là sai."""
    staging = _stage(tmp_path, "products_timeseries")
    _manifest_for(staging)
    result = publish_dataset(staging, quarantine_root=tmp_path / "q")
    assert result.status == "quarantined"
    assert any(issue.code == "grain_mismatch" for issue in result.issues)
    assert (Path(result.quarantine_dir) / "QUARANTINE.json").exists()


@pytest.mark.skipif(not EXTRA.exists(), reason="raw_extra_data chưa có trong checkout")
def test_the_constant_column_is_quarantined(tmp_path):
    """unit_sold toàn 0 trên products_timeseries — cột hằng số."""
    staging = _stage(tmp_path, "products_timeseries")
    _manifest_for(staging)
    result = publish_dataset(staging, quarantine_root=tmp_path / "q")
    assert result.status == "quarantined"
    constant = [issue for issue in result.issues if issue.code == "constant_column"]
    assert any("unit_sold" in issue.detail for issue in constant)


def test_an_empty_csv_is_quarantined_not_crashed(tmp_path):
    """public/test_*.csv rỗng — EmptyDataError phải thành lý do có kiểu."""
    staging = tmp_path / "incoming"
    staging.mkdir()
    empty = REPO / "raw_extra_data" / "public"
    if empty.exists() and list(empty.glob("test_*.csv")):
        import shutil

        source = next(empty.glob("test_*.csv"))
        shutil.copy2(source, staging / source.name)
    else:
        (staging / "test_empty.csv").write_text("", encoding="utf-8")
    _manifest_for(staging)
    result = publish_dataset(staging, quarantine_root=tmp_path / "q")
    assert result.status == "quarantined"
    assert any(
        issue.code in {"contract_violation", "all_null_column"}
        for issue in result.issues
    )


@pytest.mark.skipif(not EXTRA.exists(), reason="raw_extra_data chưa có trong checkout")
def test_the_missing_day_in_the_promotion_range_is_caught(tmp_path):
    """product_promotions: 20 ngày trong dải 07-01→07-21 — khuyết 2026-07-12."""
    staging = _stage(tmp_path, "product_promotions")
    _manifest_for(staging)
    result = publish_dataset(staging, quarantine_root=tmp_path / "q")
    assert result.status == "quarantined"
    missing = [issue for issue in result.issues
               if issue.code == "missing_date_in_range"]
    assert missing and "2026-07-12" in missing[0].detail


# --- đường sạch -------------------------------------------------------------

def test_a_clean_dataset_publishes_and_gets_its_version(tmp_path):
    staging = tmp_path / "incoming"
    staging.mkdir()
    frame = pd.DataFrame({
        "item_id": [1, 2, 3], "date": ["2026-07-01", "2026-07-02", "2026-07-03"],
        "price_num": [10.0, 11.0, 12.0],
    })
    frame.to_csv(staging / "sample_table.csv", index=False)
    _manifest_for(staging)
    result = publish_dataset(staging, quarantine_root=tmp_path / "q")
    assert result.status == "published", result.issues
    assert result.steps_run == ("manifest", "contracts", "quality", "version")
    # Bộ phụ không mang ba artifact versioned ⇒ version để trống, người ghép
    # W10.3 phải tự khai — không bịa một version.
    assert result.dataset_version is None


def test_the_frozen_dataset_would_pass_and_keep_its_version(tmp_path):
    """Bản đóng băng đi qua cửa với ĐÚNG 27de9bff184f4f89 —
    cửa publish không được đổi nghĩa của bản đang đóng băng."""
    import shutil

    staging = tmp_path / "incoming"
    shutil.copytree(Path(DATA_DIR), staging)
    # Bỏ file phụ không phải bảng để manifest chỉ khai CSV.
    _manifest_for(staging)
    result = publish_dataset(staging, quarantine_root=tmp_path / "q")
    assert result.status == "published", result.issues[:4]
    assert result.dataset_version == "27de9bff184f4f89"
