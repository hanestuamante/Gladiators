"""Một nguồn duy nhất cho ``dataset_version`` — SolutionSpec2808 §2.5 (W1.3).

Trước đây repository và ``build_value_index`` mỗi bên tự băm một thứ khác nhau
(SHA-256 trên byte đã chuẩn hoá CRLF của 3 CSV, so với SHA-256 trên chuỗi
``product_snapshot_key`` đã sort), nên *"chỉ mục dựng cho dataset nào"* là một
câu hỏi không ai trả lời được: ``27de9bff…`` và ``a821e39d…`` cùng chỉ một bộ
dữ liệu mà không chỗ nào kiểm lệch.

Module này **chỉ phụ thuộc stdlib** — đó là điều kiện để script chỉ mục import
được nó mà không thừa hưởng giả định ngữ nghĩa nào của hệ bị kiểm.

Thuật toán chuyển NGUYÊN VẸN từ ``data/repository.py``: giá trị
``27de9bff184f4f89`` không được đổi, vì nó nằm trong trace, plan cache key và
evidence đã ghi.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

# Tập file quyết định dataset_version. Cố ý HẸP — đúng ba artifact mà câu trả
# lời đọc số từ đó; thêm file phụ vào đây là đổi nghĩa của mọi version đã ghi.
VERSIONED_ARTIFACTS: tuple[str, ...] = (
    "products_clean.csv",
    "product_snapshot_metrics.csv",
    "product_transition_metrics.csv",
)


class DatasetVersionError(ValueError):
    """Chỉ mục/artifact lệch phiên bản dataset — thông tin SAI, không phải thiếu."""


def compute_dataset_version(root: str | Path) -> str:
    """SHA-256 (16 hex đầu) trên byte đã chuẩn hoá xuống dòng của 3 CSV.

    Git checkout ra CRLF trên Windows và LF trên Linux; dataset y hệt nhau ở cả
    hai, nên version của nó không được phụ thuộc cách hệ điều hành xuống dòng.
    """
    root = Path(root)
    digest = hashlib.sha256()
    for name in sorted(VERSIONED_ARTIFACTS):
        payload = (root / name).read_bytes()
        digest.update(payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    return digest.hexdigest()[:16]
