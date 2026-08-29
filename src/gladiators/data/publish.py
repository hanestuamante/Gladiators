"""Cửa publish — W10.2 (SolutionSpec2808 §11.2).

Mọi bộ dữ liệu muốn vào ``data/processed`` phải qua bốn bước; hỏng ở đâu thì
dừng ở đó với một lý do CÓ KIỂU. Bộ hỏng đi vào cách ly
``data/quarantine/<tên>/`` — hệ vẫn phục vụ bản cũ, không bao giờ nửa-ghi.

``raw_extra_data`` cấp bốn ca lỗi THẬT nên test không cần gieo lỗi giả:
``products_timeseries`` không phải time series (một dòng mỗi item), ``unit_sold``
toàn 0 (cột hằng số), ``public/test_*.csv`` rỗng (EmptyDataError), và
``product_promotions`` khuyết đúng ngày 2026-07-12 giữa dải liên tục.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import pandas as pd

from gladiators.data.dataset_version import compute_dataset_version

RefusalCode = Literal[
    "manifest_missing", "manifest_invalid", "file_hash_mismatch",
    "row_count_mismatch",
]
QuarantineCode = Literal[
    "contract_violation", "constant_column", "all_null_column",
    "missing_date_in_range", "grain_mismatch", "unreadable_file",
]


@dataclass(frozen=True)
class PublishIssue:
    code: str
    table: str | None
    detail: str


@dataclass(frozen=True)
class PublishResult:
    status: Literal["published", "refused", "quarantined"]
    issues: tuple[PublishIssue, ...] = ()
    dataset_version: str | None = None
    quarantine_dir: str | None = None
    checked_tables: tuple[str, ...] = ()
    # Khoá đếm (§0.3 ô 4): từng bước có THẬT SỰ chạy hay không.
    steps_run: tuple[str, ...] = ()


# Grain khai theo TÊN BẢNG. "products_timeseries" khai time series ⇒ phải có
# nhiều hơn một dòng cho ít nhất một khoá; một dòng mỗi item là một bảng
# snapshot đội lốt — join theo tên file là sai.
_DECLARED_TIMESERIES_PREFIXES = ("products_timeseries", "shop_stats")
_DATE_COLUMNS = ("date", "promotion_date", "observed_date", "stat_date")
_KEY_COLUMNS = ("item_id", "shop_id", "product_id")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _known_degenerate(baseline_dir: Path) -> set[str]:
    """Cột đã hằng-số/toàn-null trong BASELINE đang phục vụ — thuộc tính đã
    biết, không phải khuyết tật mới.

    Cửa publish mà cách ly chính bộ dữ liệu đang đóng băng là một cái cửa vô
    nghĩa: data/processed có path_dataset/'Shopee'/client_num hằng số (hiện vật
    export) và is_ad_bool/is_sold_out_bool zero-variance ĐÃ KHAI
    (coverage.ZERO_VARIANCE_COLUMNS, column_semantics). Luật vì thế so với
    baseline: chỉ cột degenerate MỚI mới chặn — unit_sold toàn 0 của
    raw_extra_data không có trong baseline nên vẫn bị bắt.
    """
    known: set[str] = set()
    if not baseline_dir.exists():
        return known
    for path in baseline_dir.glob("*.csv"):
        try:
            frame = pd.read_csv(path)
        except Exception:  # noqa: BLE001 — baseline hỏng thì không allowlist gì
            continue
        for column in frame.columns:
            series = frame[column]
            if series.isna().all() or (
                len(frame) > 1 and series.nunique(dropna=True) <= 1
            ):
                known.add(column)
    return known


def _quality_issues(
    name: str, frame: pd.DataFrame, known_degenerate: set[str],
) -> list[PublishIssue]:
    issues: list[PublishIssue] = []
    for column in frame.columns:
        if column in known_degenerate:
            continue
        series = frame[column]
        if series.isna().all():
            issues.append(PublishIssue("all_null_column", name, column))
        elif len(frame) > 1 and series.nunique(dropna=True) <= 1 and series.notna().any():
            # Cột hằng số trên một bảng nhiều dòng: "không đo được" đội lốt
            # "đo được và bằng phẳng" — unit_sold toàn 0 là ca thật.
            issues.append(PublishIssue(
                "constant_column", name,
                f"{column} chỉ có một giá trị: {series.dropna().iloc[0]!r}",
            ))
    date_column = next((c for c in _DATE_COLUMNS if c in frame.columns), None)
    if date_column is not None:
        observed = pd.to_datetime(frame[date_column], errors="coerce").dt.date.dropna()
        distinct = sorted(set(observed))
        if len(distinct) >= 3:
            expected = set()
            cursor = distinct[0]
            while cursor <= distinct[-1]:
                expected.add(cursor)
                cursor += timedelta(days=1)
            missing = sorted(expected - set(distinct))
            if missing:
                issues.append(PublishIssue(
                    "missing_date_in_range", name,
                    "khuyết ngày giữa dải liên tục: "
                    + ", ".join(str(d) for d in missing[:5]),
                ))
    if any(name.startswith(prefix) for prefix in _DECLARED_TIMESERIES_PREFIXES):
        key_column = next((c for c in _KEY_COLUMNS if c in frame.columns), None)
        if key_column is not None and len(frame) > 0:
            per_key = frame.groupby(key_column).size()
            if int(per_key.max()) <= 1:
                issues.append(PublishIssue(
                    "grain_mismatch", name,
                    "tên bảng khai time series nhưng mỗi khoá có đúng một dòng "
                    "— một snapshot đội lốt chuỗi thời gian",
                ))
    return issues


def publish_dataset(
    source_dir: str | Path,
    *,
    quarantine_root: str | Path = "data/quarantine",
    label: str | None = None,
    baseline_dir: str | Path = "data/processed",
) -> PublishResult:
    """Bốn bước của §11.2. Không bao giờ đè bản đang phục vụ.

    Bước 1 hỏng ⇒ ``refused`` và KHÔNG ghi gì. Bước 2/3 hỏng ⇒ ``quarantined``:
    chép nguyên bộ vào ``data/quarantine/<label>/`` kèm ``QUARANTINE.json`` lý
    do có kiểu. Bước 4 chỉ chạy khi sạch.
    """
    source = Path(source_dir)
    steps: list[str] = []

    # ── bước 1 · manifest ──
    steps.append("manifest")
    manifest_path = source / "manifest.json"
    if not manifest_path.exists():
        return PublishResult("refused", (PublishIssue(
            "manifest_missing", None,
            "thiếu manifest.json (nguồn, thời điểm export, sha256 từng file, số dòng)",
        ),), steps_run=tuple(steps))
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        declared_files = manifest["files"]
        assert manifest.get("source") and manifest.get("exported_at")
    except (json.JSONDecodeError, KeyError, AssertionError) as exc:
        return PublishResult("refused", (PublishIssue(
            "manifest_invalid", None, f"manifest không hợp lệ: {exc}",
        ),), steps_run=tuple(steps))
    refusals: list[PublishIssue] = []
    for name, declared in declared_files.items():
        path = source / name
        if not path.exists():
            refusals.append(PublishIssue("manifest_invalid", name, "file khai mà vắng"))
            continue
        if _sha256(path) != declared.get("sha256"):
            refusals.append(PublishIssue("file_hash_mismatch", name, "sha256 lệch manifest"))
    if refusals:
        return PublishResult("refused", tuple(refusals), steps_run=tuple(steps))

    # ── bước 2 + 3 · đọc được, contract, luật chất lượng ──
    issues: list[PublishIssue] = []
    frames: dict[str, pd.DataFrame] = {}
    checked: list[str] = []
    steps.append("contracts")
    for name, declared in declared_files.items():
        checked.append(name)
        try:
            frame = pd.read_csv(source / name)
        except pd.errors.EmptyDataError:
            issues.append(PublishIssue("contract_violation", name,
                                       "file rỗng (EmptyDataError)"))
            continue
        except Exception as exc:  # noqa: BLE001 — mọi lỗi đọc là contract_violation
            issues.append(PublishIssue("unreadable_file", name,
                                       f"{type(exc).__name__}: {exc}"))
            continue
        declared_rows = declared.get("rows")
        if declared_rows is not None and int(declared_rows) != len(frame):
            issues.append(PublishIssue(
                "contract_violation", name,
                f"số dòng thật {len(frame)} lệch manifest {declared_rows}",
            ))
        frames[name] = frame
    steps.append("quality")
    known_degenerate = _known_degenerate(Path(baseline_dir))
    for name, frame in frames.items():
        issues.extend(_quality_issues(name, frame, known_degenerate))

    if issues:
        target = Path(quarantine_root) / (label or source.name)
        target.mkdir(parents=True, exist_ok=True)
        for name in declared_files:
            if (source / name).exists():
                shutil.copy2(source / name, target / Path(name).name)
        shutil.copy2(manifest_path, target / "manifest.json")
        (target / "QUARANTINE.json").write_text(json.dumps({
            "schema_version": "quarantine.v1",
            "source": str(source),
            "issues": [issue.__dict__ for issue in issues],
        }, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        return PublishResult(
            "quarantined", tuple(issues),
            quarantine_dir=str(target), checked_tables=tuple(checked),
            steps_run=tuple(steps),
        )

    # ── bước 4 · dataset_version vào manifest ──
    steps.append("version")
    version = None
    try:
        version = compute_dataset_version(source)
    except FileNotFoundError:
        # Bộ không mang đúng ba artifact versioned — hợp lệ cho dataset phụ;
        # version để trống và người ghép (W10.3) phải tự khai.
        pass
    if version is not None:
        manifest["dataset_version"] = version
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return PublishResult(
        "published", (), dataset_version=version,
        checked_tables=tuple(checked), steps_run=tuple(steps),
    )
