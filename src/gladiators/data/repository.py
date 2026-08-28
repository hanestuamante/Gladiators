from __future__ import annotations

import hashlib
import json
from functools import cached_property
from pathlib import Path

import pandas as pd

from .contracts import validate_artifacts


# Tên file khai báo phiên bản. Có nó thì `dataset_version` là thứ ĐƯỢC KHAI, không
# phải thứ suy ra bằng cách băm lại CSV mỗi lần — xem docstring của thuộc tính đó.
MANIFEST_NAME = "DATASET_VERSION.json"
POINTER_NAME = "CURRENT"


class ArtifactRepository:
    """Một **ảnh chụp** dữ liệu, bất biến trong suốt đời của object này.

    Trước đây ``read()`` không cache còn ``products``/``dataset_version`` thì cache,
    nên một tiến trình có HAI vòng đời cho cùng một dữ liệu. Đo được: sửa CSV giữa
    hai lần hỏi thì con số đổi 668 → 568 nhưng ``dataset_version`` vẫn đứng ở bản
    mà đáp án là 668 — evidence khai một xuất xứ SAI, đúng thứ cả kiến trúc này
    tồn tại để chặn.

    Giờ mọi thứ đọc qua một cache duy nhất. Muốn dữ liệu mới thì dựng một
    repository mới rồi **đổi con trỏ** — một thao tác tường minh và nguyên tử, chứ
    không phải một hiệu ứng phụ của việc file trên đĩa đổi giữa chừng.
    """

    def __init__(self, root: str | Path = "data/processed", validate: bool = True):
        # Trỏ vào một thư mục CÓ CON TRỎ (data/) thì đi theo con trỏ; trỏ thẳng
        # vào thư mục dữ liệu thì dùng luôn. Giữ cả hai để data/processed cũ chạy
        # y nguyên — một thay đổi hạ tầng bắt mọi người sửa lệnh ngay hôm đó là
        # một thay đổi không ai áp dụng.
        from .versions import resolve

        root = Path(root)
        resolved = resolve(root) if (root / POINTER_NAME).exists() else None
        self.data_root = root
        self.root = resolved or root
        if validate:
            validate_artifacts(self.root)
        self._frames: dict[str, pd.DataFrame] = {}

    def read(self, name: str) -> pd.DataFrame:
        """Đọc một artifact, cache theo ĐỜI CỦA REPOSITORY.

        Trả bản copy: ``Evidence`` bất biến, và một consumer sửa frame tại chỗ sẽ
        làm mọi consumer sau đó thấy một dataset khác dataset đã đóng dấu.
        """
        if name not in self._frames:
            self._frames[name] = pd.read_csv(self.root / name, low_memory=False)
        return self._frames[name].copy()

    @cached_property
    def products(self) -> pd.DataFrame:
        return self.read("products_clean.csv")

    @cached_property
    def snapshots(self) -> pd.DataFrame:
        return self.read("product_snapshot_metrics.csv")

    @cached_property
    def transitions(self) -> pd.DataFrame:
        return self.read("product_transition_metrics.csv")

    @cached_property
    def dataset_version(self) -> str:
        """Phiên bản dữ liệu — **đọc từ manifest nếu có**, băm lại nếu không.

        Băm lại là chế độ tương thích ngược cho thư mục chưa có manifest. Nó đúng
        nhưng yếu ở một điểm: nó là thứ *suy ra được*, nên không có gì buộc nó
        khớp với bộ byte mà câu trả lời thật sự đọc. Manifest là thứ *được khai*,
        sinh ra cùng lúc với dữ liệu, nên nó không thể lệch.
        """
        manifest = self.root / MANIFEST_NAME
        if manifest.exists():
            try:
                declared = json.loads(manifest.read_text(encoding="utf-8")).get("version_id")
            except (OSError, json.JSONDecodeError):
                declared = None
            if declared:
                return str(declared)
        h = hashlib.sha256()
        for name in sorted(["products_clean.csv", "product_snapshot_metrics.csv", "product_transition_metrics.csv"]):
            # Git may check text artifacts out as CRLF on Windows and LF on
            # Linux.  The dataset is identical in both cases, so its version
            # must be based on canonical text bytes rather than OS line endings.
            payload = (self.root / name).read_bytes()
            h.update(payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
        return h.hexdigest()[:16]

    def capability_profile(self) -> dict[str, object]:
        p = self.products
        return {
            "countries": sorted(p.country_code.dropna().unique().tolist()),
            "dates": sorted(p.date.dropna().astype(str).unique().tolist()),
            "fields": sorted(p.columns.tolist()),
            "snapshot_count": int(p.date.nunique()),
            "voucher_structured_by_country": p.groupby("country_code")["voucher_code"].apply(lambda s: int(s.notna().sum())).to_dict(),
        }
