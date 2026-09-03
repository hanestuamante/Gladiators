"""W30 — lịch snapshot là DỮ LIỆU, không phải hằng số.

Trước module này, cửa sổ ngày của bộ đóng băng được viết thẳng vào **45 chỗ ở 13
file**: ``GOVERNED_DATES``, ``LATEST_SNAPSHOT``, regex ``_DATE_DAY_MONTH`` chỉ
khớp ngày 1–3 tháng 7, ``expected_cardinality="<=3341"``, và ``time_scope`` của
sáu template cùng ba macro.

Trên bộ 3 ngày những hằng số đó **đúng**, nên không phép kiểm nào bắt được chúng.
Trên bộ 20 ngày:

* regex bỏ qua **17 ngày có thật** ⇒ chúng rơi vào ``LATEST_SNAPSHOT``, tức đúng
  lỗ ``over_answer`` mà W20 sinh ra để đóng — lần này với một ngày CÓ dữ liệu;
* ``"<=3341"`` bị vi phạm bởi một plan quét toàn bảng ⇒ postcondition fail ⇒
  fail-closed đúng, nhưng nguyên nhân bị nói sai.

Ba trạng thái của một ngày, và vì sao phải là ba chứ không phải hai:

``2026-07-12`` **không có đợt thu nào** trên bộ mới. Nó không phải "ngoài cửa
sổ" (nó nằm giữa 01 và 21/07) và không phải "có dữ liệu". Gộp nó vào
``out_of_window`` sẽ nói với người dùng rằng dữ liệu chỉ có tới 11/07 — sai. Lấy
ngày lân cận trả thay là ``LATEST_SNAPSHOT`` mặc một cái áo khác.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

MANIFEST_NAME = "DATASET_VERSION.json"
POINTER_NAME = "CURRENT"
CALENDAR_KEY = "calendar"

# Artifact mà lịch đọc ra khi manifest chưa mang sẵn khối ``calendar``.
_SOURCE_ARTIFACT = "products_clean.csv"


class CalendarError(ValueError):
    """Bản dữ liệu không nói được nó quan sát những ngày nào."""


@dataclass(frozen=True)
class SnapshotCalendar:
    """Những ngày một bản dữ liệu THẬT SỰ quan sát, cộng các lỗ giữa chúng."""

    dates: tuple[str, ...]
    gaps: tuple[str, ...]
    listing_count: int
    row_count: int

    def first(self) -> str:
        return self.dates[0]

    def last(self) -> str:
        return self.dates[-1]

    def contains(self, iso: str) -> bool:
        """Ngày này CÓ đợt thu."""
        return iso in self.dates

    def in_range(self, iso: str) -> bool:
        """Ngày này nằm trong kỳ thu thập — kể cả khi nó là một lỗ."""
        return bool(self.dates) and self.first() <= iso <= self.last()

    def is_gap(self, iso: str) -> bool:
        """Trong kỳ nhưng không có đợt thu. Trạng thái thứ ba."""
        return iso in self.gaps

    def boundary_pair(self) -> tuple[str, str]:
        """Hai mốc để so sánh biến động.

        Lấy hai ĐỢT THU đầu/cuối chứ không phải hai ngày lịch: lấy theo ngày lịch
        có thể trúng một lỗ, và một vế rỗng trong phép so sánh trông giống hệt
        "giảm về 0".
        """
        if len(self.dates) < 2:
            raise CalendarError(
                "bản dữ liệu chỉ có một đợt thu — không có cặp mốc để so sánh",
            )
        return self.dates[0], self.dates[-1]

    def as_dict(self) -> dict[str, object]:
        return {
            "dates": list(self.dates),
            "gaps": list(self.gaps),
            "listing_count": self.listing_count,
            "row_count": self.row_count,
        }


def _gaps_between(dates: tuple[str, ...]) -> tuple[str, ...]:
    if len(dates) < 2:
        return ()
    start = date.fromisoformat(dates[0])
    end = date.fromisoformat(dates[-1])
    observed = set(dates)
    out: list[str] = []
    day = start
    while day <= end:
        iso = day.isoformat()
        if iso not in observed:
            out.append(iso)
        day += timedelta(days=1)
    return tuple(out)


def calendar_from_dates(
    dates: tuple[str, ...] | list[str],
    *,
    listing_count: int = 0,
    row_count: int = 0,
) -> SnapshotCalendar:
    """Hàm THUẦN — dựng lịch từ danh sách ngày, không đọc file.

    Dùng ở test và ở bước build; runtime đi qua ``load_calendar``.
    """
    ordered = tuple(sorted({str(day) for day in dates}))
    if not ordered:
        raise CalendarError("không có ngày nào — bản dữ liệu rỗng")
    return SnapshotCalendar(
        dates=ordered,
        gaps=_gaps_between(ordered),
        listing_count=int(listing_count),
        row_count=int(row_count),
    )


def _resolve_root(root: str | Path | None) -> Path:
    """Trỏ vào thư mục CÓ con trỏ thì đi theo con trỏ — cùng luật với repository."""
    from gladiators.data.repository import DEFAULT_DATA_DIR

    path = Path(root if root is not None else DEFAULT_DATA_DIR)
    pointer = path / POINTER_NAME
    if pointer.exists():
        target = pointer.read_text(encoding="utf-8").strip()
        if target:
            candidate = path / "versions" / target
            return candidate if candidate.exists() else Path(target)
    return path


def _from_manifest(root: Path) -> SnapshotCalendar | None:
    manifest = root / MANIFEST_NAME
    if not manifest.exists():
        return None
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    block = payload.get(CALENDAR_KEY)
    if not isinstance(block, dict) or not block.get("dates"):
        return None
    return SnapshotCalendar(
        dates=tuple(str(day) for day in block["dates"]),
        gaps=tuple(str(day) for day in block.get("gaps", ())),
        listing_count=int(block.get("listing_count", 0)),
        row_count=int(block.get("row_count", 0)),
    )


def _from_artifact(root: Path) -> SnapshotCalendar:
    """Đọc thẳng artifact khi manifest chưa mang khối ``calendar``.

    Import pandas TRONG hàm: module này được import từ ``invariant_handlers``,
    thứ nằm trên đường import của gần như mọi thứ, và một import pandas ở đầu file
    kéo nó vào cả những tiến trình chỉ cần hằng số.
    """
    import pandas as pd

    path = root / _SOURCE_ARTIFACT
    if not path.exists():
        raise CalendarError(
            f"không dựng được lịch snapshot: thiếu {path}. Lịch là dữ liệu của "
            "bản dữ liệu, không phải một hằng số có thể đoán.",
        )
    frame = pd.read_csv(path, usecols=["date", "product_listing_key"], low_memory=False)
    dates = tuple(sorted(frame["date"].dropna().astype(str).unique()))
    return calendar_from_dates(
        dates,
        listing_count=int(frame["product_listing_key"].nunique()),
        row_count=int(len(frame)),
    )


@lru_cache(maxsize=8)
def load_calendar(data_root: str | Path | None = None) -> SnapshotCalendar:
    """Lịch của bản dữ liệu tại ``data_root``, cache theo đường dẫn.

    Ưu tiên khối ``calendar`` trong manifest (ghi lúc build); lùi về đọc artifact
    khi manifest chưa có nó, để bản dữ liệu cũ vẫn dùng được mà không phải dựng
    lại.
    """
    root = _resolve_root(data_root)
    return _from_manifest(root) or _from_artifact(root)


def default_calendar() -> SnapshotCalendar:
    """Lịch của bản dữ liệu đang phục vụ."""
    return load_calendar()


def full_window() -> tuple[str, ...]:
    """Toàn bộ đợt thu của bản dữ liệu đang phục vụ."""
    return default_calendar().dates


def latest_snapshot() -> str:
    """Đợt thu mới nhất (W30-R2)."""
    return default_calendar().last()


def boundary_pair() -> tuple[str, str]:
    """Hai mốc biên để so sánh biến động (W21-R4)."""
    return default_calendar().boundary_pair()
