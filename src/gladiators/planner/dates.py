"""W20 — ngày là một hàm TOÀN PHẦN, không phải một regex khớp được thì khớp.

``extract_date_range`` trước module này dùng
``_DATE_DAY_MONTH = r"0?([123])\\s*/\\s*0?7"``: chỉ ngày **1, 2, 3** của tháng
**7**. Trên bộ đóng băng regex đó phủ đúng cửa sổ, nên nó chỉ bỏ sót ngày NGOÀI
cửa sổ — và một ngày ngoài cửa sổ không tồn tại trong request thì template điền
``LATEST_SNAPSHOT``, câu trả lời khai đúng scope nó đã dùng nhưng **không nói
rằng scope đó khác scope được hỏi**. Đó là hai trong ba ca ``over_answer``.

Trên bộ 20 ngày cùng dòng code đó bỏ sót **17 ngày CÓ THẬT**, và lớp lỗi nặng
hơn: nó biến một câu hỏi trả lời được thành một con số của ngày khác.

**Năm ô, không phải bốn.** ``2026-07-12`` không có đợt thu nào trên bộ mới. Nó
không phải "ngoài cửa sổ" (nó nằm giữa 01 và 21/07) và không phải "có dữ liệu".
Gộp nó vào ``out_of_window`` sẽ nói với người dùng rằng dữ liệu chỉ có tới
11/07 — sai. Lấy ngày lân cận trả thay là ``LATEST_SNAPSHOT`` mặc một cái áo
khác (LUẬT W20-R5).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from gladiators.domain.calendar import SnapshotCalendar

# Ngữ pháp ngày — KHÔNG giới hạn tháng, KHÔNG giới hạn ngày.
_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_DMY = re.compile(r"(?<![0-9])(\d{1,2})\s*[/-]\s*(\d{1,2})(?:\s*[/-]\s*(\d{4}))?(?![0-9])")
_VI_DAY_MONTH = re.compile(r"ngay\s+(\d{1,2})\s+thang\s+(\d{1,2})")
_ID_DAY = re.compile(r"tanggal\s+(\d{1,2})")

# Khoảng CÓ TÊN. Giá trị là (offset_bắt_đầu, số_ngày) tính từ mốc đầu lịch, hoặc
# một hàm đặc biệt xử lý ở dưới.
_NAMED_WINDOWS: dict[str, str] = {
    "tuan dau thang": "first_week",
    "dau thang": "first_week",
    "minggu pertama": "first_week",
    "first week": "first_week",
    "giua thang": "mid_month",
    "cuoi thang": "last_week",
    "tuan cuoi": "last_week",
    "tuan truoc": "last_week",
    "last week": "last_week",
    "hom nay": "latest",
    "hari ini": "latest",
    "today": "latest",
    "moi nhat": "latest",
    "gan nhat": "latest",
}


@dataclass(frozen=True)
class DateRequest:
    """Mọi span hình-dạng-ngày rơi vào ĐÚNG MỘT ô. Không có ô "bỏ qua"."""

    dates: tuple[str, ...] = ()             # có đợt thu
    missing_snapshot: tuple[str, ...] = ()  # trong kỳ, KHÔNG có đợt thu  ← W20
    out_of_window: tuple[str, ...] = ()     # phân tích được, ngoài kỳ
    relative: tuple[str, ...] = ()          # khoảng có tên đã nhận ra
    clamped: bool = False                   # relative đã bị cắt về cửa sổ
    unparsed: tuple[str, ...] = ()          # hình-dạng-ngày không phân giải được

    def is_empty(self) -> bool:
        """Rỗng ở CẢ NĂM ô — điều kiện duy nhất cho phép mặc định đợt thu mới nhất."""
        return not (
            self.dates or self.missing_snapshot or self.out_of_window
            or self.relative or self.unparsed
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "dates": list(self.dates),
            "missing_snapshot": list(self.missing_snapshot),
            "out_of_window": list(self.out_of_window),
            "relative": list(self.relative),
            "clamped": self.clamped,
            "unparsed": list(self.unparsed),
        }


def _iso(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _candidates(normalized: str, calendar: SnapshotCalendar) -> list[str]:
    """Mọi ngày phân tích được từ câu, ở dạng ISO. Không lọc theo lịch."""
    default_year = int(calendar.first()[:4])
    out: list[str] = []
    for year, month, day in _ISO.findall(normalized):
        iso = _iso(int(year), int(month), int(day))
        if iso:
            out.append(iso)
    for day, month, year in _DMY.findall(normalized):
        iso = _iso(int(year) if year else default_year, int(month), int(day))
        if iso:
            out.append(iso)
    for day, month in _VI_DAY_MONTH.findall(normalized):
        iso = _iso(default_year, int(month), int(day))
        if iso:
            out.append(iso)
    for day in _ID_DAY.findall(normalized):
        iso = _iso(default_year, int(calendar.first()[5:7]), int(day))
        if iso:
            out.append(iso)
    return list(dict.fromkeys(out))


def _window(kind: str, calendar: SnapshotCalendar) -> tuple[str, ...]:
    dates = calendar.dates
    if kind == "latest":
        return (calendar.last(),)
    if kind == "first_week":
        start = date.fromisoformat(calendar.first())
        limit = start.toordinal() + 6
        return tuple(d for d in dates if date.fromisoformat(d).toordinal() <= limit)
    if kind == "last_week":
        end = date.fromisoformat(calendar.last())
        floor = end.toordinal() - 6
        return tuple(d for d in dates if date.fromisoformat(d).toordinal() >= floor)
    if kind == "mid_month":
        # Một phần ba giữa của cửa sổ đã thu — mô tả theo LỊCH THẬT, không theo
        # một khái niệm "giữa tháng" của lịch dương mà dữ liệu có thể không phủ.
        if len(dates) < 3:
            return dates
        third = len(dates) // 3
        return dates[third:len(dates) - third] or dates
    return ()


def parse_date_expressions(
    normalized: str, calendar: SnapshotCalendar,
) -> DateRequest:
    """Phân giải mọi cụm ngày trong câu vào năm ô (LUẬT W20-R1)."""
    dates: list[str] = []
    missing: list[str] = []
    outside: list[str] = []
    for iso in _candidates(normalized, calendar):
        if calendar.contains(iso):
            dates.append(iso)
        elif calendar.is_gap(iso):
            missing.append(iso)
        else:
            outside.append(iso)

    relative: list[str] = []
    clamped = False
    if not dates and not missing and not outside:
        for surface, kind in _NAMED_WINDOWS.items():
            if surface in normalized:
                window = _window(kind, calendar)
                if window:
                    relative.append(surface)
                    dates.extend(window)
                    # LUẬT W20-R3: cắt phải KHAI BÁO. Một khoảng có tên phủ
                    # nhiều hơn số đợt thu thật thì phần ngoài đã bị bỏ, và
                    # alignment phải kiểm được phép cắt đó thay vì tin nó.
                    clamped = kind != "latest" and len(window) < len(calendar.dates)
                break

    return DateRequest(
        dates=tuple(sorted(dict.fromkeys(dates))),
        missing_snapshot=tuple(sorted(dict.fromkeys(missing))),
        out_of_window=tuple(sorted(dict.fromkeys(outside))),
        relative=tuple(relative),
        clamped=clamped,
    )
