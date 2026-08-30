"""Bản dữ liệu là một **artifact có tên**, không phải một thư mục ngẫu nhiên.

Đây là mảnh còn thiếu khiến ba vấn đề tưởng như riêng biệt thật ra là một:

* notebook phải bấm Run All bằng tay — vì **không ai đặt tên cho thứ nó sinh ra**,
  nên không có gì để một job CI gọi tên và không có gì để rollback về;
* server phải dựng lại để thấy dữ liệu mới — vì **không có con trỏ nào để đổi**;
* ``dataset_version`` từng khai sai xuất xứ — vì nó là thứ *suy ra được* chứ
  không phải thứ *được khai cùng lúc với dữ liệu*.

Bố cục::

    data/versions/<version_id>/         ← BẤT BIẾN, không bao giờ sửa tại chỗ
        products_clean.csv  …
        DATASET_VERSION.json            ← manifest: id, nguồn raw, mốc, hash
    data/CURRENT                        ← file trỏ, nội dung là <version_id>

Dùng **file trỏ** chứ không symlink: symlink trên Windows đòi quyền admin hoặc
Developer Mode, nên một thiết kế dựa vào nó sẽ chạy trên máy người này và hỏng
trên máy người kia — đúng thứ "không ai chạy lại được ngoài người viết".

Nguyên lý nền là *Functional Data Engineering*: partition bất biến, task
idempotent, kho staging còn mãi. Ghi đè cả một partition thì chạy lại bao nhiêu
lần cũng ra một kết quả; sửa tại chỗ thì không.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "DATASET_VERSION.json"
POINTER_NAME = "CURRENT"
VERSIONS_DIRNAME = "versions"

# File tạo nên danh tính của một bản. Cố ý HẸP: chỉ những artifact mà câu trả lời
# thật sự đọc. Băm cả thư mục sẽ làm một file log đổi cũng sinh ra một "bản dữ
# liệu mới", và version_id mất nghĩa.
VERSIONED_ARTIFACTS: tuple[str, ...] = (
    "products_clean.csv",
    "product_snapshot_metrics.csv",
    "product_transition_metrics.csv",
    "shop_info_clean.csv",
    "category_list_clean.csv",
    "category_platform_clean.csv",
    "product_categories_clean.csv",
)

# Artifact góp vào danh tính CHỈ KHI có mặt. Bản chưa thu ``shop_stats`` băm ra
# đúng version như trước khi khoá này tồn tại — thêm mà không dịch chuyển bản cũ.
OPTIONAL_VERSIONED_ARTIFACTS: tuple[str, ...] = (
    "shop_stats_clean.csv",
)


class DatasetVersionError(ValueError):
    """Bố cục version sai ⇒ hỏng ngay, không phục vụ một bản nửa vời."""


@dataclass(frozen=True)
class DatasetVersion:
    version_id: str
    root: Path
    manifest: dict


def _canonical_hash(path: Path) -> str:
    """Băm theo **byte đã chuẩn hoá xuống dòng**.

    Git checkout ra CRLF trên Windows và LF trên Linux; dataset y hệt nhau ở cả
    hai, nên version của nó không được phụ thuộc vào cách hệ điều hành xuống dòng.
    """
    payload = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(payload).hexdigest()


def compute_version_id(root: Path) -> str:
    """Id nội dung của một thư mục dữ liệu — hàm thuần của chính các byte đó."""
    digest = hashlib.sha256()
    for name in sorted(VERSIONED_ARTIFACTS):
        path = root / name
        if not path.exists():
            raise DatasetVersionError(f"thiếu artifact bắt buộc: {name}")
        digest.update(name.encode("utf-8"))
        digest.update(_canonical_hash(path).encode("utf-8"))
    for name in sorted(OPTIONAL_VERSIONED_ARTIFACTS):
        path = root / name
        if not path.exists():
            continue
        digest.update(name.encode("utf-8"))
        digest.update(_canonical_hash(path).encode("utf-8"))
    return digest.hexdigest()[:16]


def _calendar_block(root: Path) -> dict:
    from gladiators.domain.calendar import load_calendar

    load_calendar.cache_clear()
    return load_calendar(root).as_dict()


def write_manifest(
    root: Path, *, raw_snapshot: str | None = None,
    built_by: str | None = None, notes: str = "",
) -> dict:
    """Ghi manifest cho một thư mục dữ liệu đã dựng xong.

    ``version_id`` tính TỪ nội dung rồi mới ghi ra, nên nó không thể mâu thuẫn
    với dữ liệu nằm cạnh nó.
    """
    version_id = compute_version_id(root)
    manifest = {
        "version_id": version_id,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "built_by": built_by or os.getenv("USERNAME") or os.getenv("USER") or "unknown",
        # Bản raw nào sinh ra bản này. Thiếu nó thì không tái lập được, và một
        # bản dữ liệu không tái lập được là một giai thoại.
        "raw_snapshot": raw_snapshot,
        # W30: lịch snapshot đi CÙNG bản dữ liệu. Đọc lại từ artifact mỗi lần
        # khởi động thì mỗi tiến trình tự trả lời "bản này quan sát ngày nào" —
        # và hai câu trả lời khác nhau cho cùng một bản là cách chúng lệch nhau.
        "calendar": _calendar_block(root),
        "artifacts": {
            name: _canonical_hash(root / name)
            for name in sorted(VERSIONED_ARTIFACTS + OPTIONAL_VERSIONED_ARTIFACTS)
            if (root / name).exists()
        },
        "notes": notes,
    }
    (root / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return manifest


def read_manifest(root: Path) -> dict | None:
    path = Path(root) / MANIFEST_NAME
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def verify(root: Path) -> tuple[str, ...]:
    """Artifact có hash lệch manifest. Rỗng nghĩa là bản này còn nguyên vẹn.

    Đây là thứ biến "bất biến" từ một quy ước thành một điều **kiểm được**.
    """
    manifest = read_manifest(root)
    if manifest is None:
        raise DatasetVersionError(f"không có {MANIFEST_NAME} trong {root}")
    declared = manifest.get("artifacts") or {}
    drifted = [
        name for name, digest in declared.items()
        if not (Path(root) / name).exists() or _canonical_hash(Path(root) / name) != digest
    ]
    return tuple(sorted(drifted))


def publish(
    source: Path, data_root: Path, *, raw_snapshot: str | None = None,
    built_by: str | None = None, notes: str = "",
) -> DatasetVersion:
    """Chép một thư mục đã dựng vào ``data/versions/<id>/`` và ghi manifest.

    Bản đã tồn tại thì **không ghi đè**: id là hàm của nội dung, nên trùng id
    nghĩa là trùng byte, và ghi lại chỉ tổ tạo cơ hội cho hai bản cùng tên khác
    ruột.
    """
    source, data_root = Path(source), Path(data_root)
    version_id = compute_version_id(source)
    target = data_root / VERSIONS_DIRNAME / version_id
    if target.exists():
        return DatasetVersion(version_id, target, read_manifest(target) or {})

    staging = target.with_name(f".{version_id}.partial")
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(source, staging)
    write_manifest(staging, raw_snapshot=raw_snapshot, built_by=built_by, notes=notes)
    # Đổi tên là thao tác NGUYÊN TỬ trên cùng một ổ đĩa: không ai đọc được một
    # thư mục version đang chép dở.
    staging.rename(target)
    return DatasetVersion(version_id, target, read_manifest(target) or {})


def pointer_path(data_root: Path) -> Path:
    return Path(data_root) / POINTER_NAME


def current_version_id(data_root: Path) -> str | None:
    path = pointer_path(data_root)
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def resolve(data_root: Path) -> Path | None:
    """Thư mục mà con trỏ đang chỉ tới, hoặc ``None`` nếu chưa có con trỏ."""
    version_id = current_version_id(data_root)
    if not version_id:
        return None
    target = Path(data_root) / VERSIONS_DIRNAME / version_id
    if not target.is_dir():
        raise DatasetVersionError(
            f"{POINTER_NAME} trỏ tới bản không tồn tại: {version_id}",
        )
    return target


def switch(data_root: Path, version_id: str) -> Path:
    """Đổi con trỏ sang một bản khác. Đây là toàn bộ thao tác "nạp dữ liệu mới".

    Ghi ra file tạm rồi ``replace`` — nguyên tử, nên không có khoảnh khắc nào con
    trỏ rỗng hoặc chỉ tới nửa cái tên.
    """
    data_root = Path(data_root)
    target = data_root / VERSIONS_DIRNAME / version_id
    if not target.is_dir():
        raise DatasetVersionError(f"không có bản {version_id} trong {data_root}")
    drifted = verify(target)
    if drifted:
        # Trỏ vào một bản đã bị sửa tại chỗ là phá đúng bất biến mà kho này dựng
        # lên để giữ.
        raise DatasetVersionError(
            f"bản {version_id} đã bị sửa sau khi publish: {', '.join(drifted)}",
        )
    pointer = pointer_path(data_root)
    pointer.parent.mkdir(parents=True, exist_ok=True)
    temporary = pointer.with_suffix(".tmp")
    temporary.write_text(version_id + "\n", encoding="utf-8")
    os.replace(temporary, pointer)
    return target


def list_versions(data_root: Path) -> tuple[DatasetVersion, ...]:
    versions_root = Path(data_root) / VERSIONS_DIRNAME
    if not versions_root.is_dir():
        return ()
    found = []
    for path in sorted(versions_root.iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        found.append(DatasetVersion(path.name, path, read_manifest(path) or {}))
    return tuple(found)
