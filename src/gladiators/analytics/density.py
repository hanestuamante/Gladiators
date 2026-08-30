"""W29 — mật độ quan sát là một HỢP ĐỒNG, không phải một chi tiết của dữ liệu.

Đọc ``<data_root>/observation_density.json`` (dựng bởi
``scripts/build_observation_density.py``) và trả lời đúng một câu hỏi mà không
lớp nào khác trong hệ hỏi được:

    *Phạm vi mà plan này chạm tới có ĐỦ quan sát để phát biểu về nó không?*

Vị trí trong luồng là có chủ đích (LUẬT W29-R6): **sau compile, trước execute**.
Nó cần plan đã hợp lệ để biết scope, và phải chặn **trước khi một con số tồn
tại** — một con số đã tính rồi thì mọi lớp sau đều thấy nó hợp lệ.

Thiếu file mật độ là một **lỗi ồn ào**, không phải một mặc định êm: nếu W29 lùi
về "coi như dày đặc" thì cấu hình nguy hiểm nhất lại là cấu hình dễ xảy ra nhất.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

FILENAME = "observation_density.json"
SCHEMA_VERSION = "observation-density.v1"


class DensityError(ValueError):
    """Bản dữ liệu không nói được nó quan sát dày tới đâu."""


@dataclass(frozen=True)
class DensityVerdict:
    """Kết luận cho MỘT phép tổng hợp trên MỘT scope."""

    column: str
    mode: str                 # panel | point_in_time
    coverage: float
    observed_rows: int
    scope_rows: int
    action: str               # allow | qualify | clarify

    def as_attrs(self) -> dict[str, object]:
        """LUẬT W29-R3 — ``n`` và MẪU SỐ phải có trong evidence, LUÔN.

        Verifier hôm nay kiểm *số hiển thị có evidence không*; nó không kiểm
        *evidence phủ bao nhiêu phần phạm vi*. Thiếu hai khoá này thì W29 không
        kiểm được sau khi chạy, và "đã đo" lại không phân biệt được với "đã
        chạy".
        """
        return {
            "observation_coverage": round(self.coverage, 4),
            "observed_rows": self.observed_rows,
            "scope_rows": self.scope_rows,
            "observation_mode": self.mode,
            "partial_observation": self.action == "qualify",
        }


@lru_cache(maxsize=8)
def _payload(data_root: str) -> dict:
    path = Path(data_root) / FILENAME
    if not path.exists():
        raise DensityError(
            f"thiếu {path}. Mật độ quan sát là dữ liệu của bản dữ liệu; thiếu nó "
            "mà vẫn chạy là coi mọi chỉ số như quan sát đầy đủ — đúng cấu hình "
            "nguy hiểm nhất. Dựng bằng scripts/build_observation_density.py.",
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise DensityError(
            f"observation_density.json schema {data.get('schema_version')!r} "
            f"không phải {SCHEMA_VERSION!r}",
        )
    return data


def thresholds(data_root: str = "data/processed") -> tuple[float, float]:
    data = _payload(data_root)
    return float(data.get("coverage_dense", 0.95)), float(data.get("coverage_refuse", 0.50))


def mode_of(column: str, data_root: str = "data/processed") -> str:
    """``panel`` | ``point_in_time`` cho một cột vật lý ``<artifact>.<column>``."""
    entry = (_payload(data_root).get("columns") or {}).get(column)
    return str(entry["mode"]) if entry else "panel"


def coverage_of(
    column: str, dates: tuple[str, ...] = (), country: str | None = None,
    data_root: str = "data/processed",
) -> float | None:
    """Mật độ của cột trên SCOPE được nêu (LUẬT W29-R5).

    Tính trên toàn bảng sẽ cho ``rating`` 5,6% ở MỌI câu hỏi, kể cả câu hỏi về
    ngày mà nó dày 100%. Scope là thứ quyết định.
    """
    entry = (_payload(data_root).get("columns") or {}).get(column)
    if entry is None:
        return None
    if dates:
        by_date = entry.get("by_date") or {}
        values = [by_date[d] for d in dates if d in by_date]
        if values:
            return sum(values) / len(values)
    if country:
        by_country = entry.get("by_country") or {}
        if country in by_country:
            return float(by_country[country])
    return float(entry.get("overall_coverage", 1.0))


def check(
    refs: tuple[str, ...], dates: tuple[str, ...], country: str | None,
    aggregation: str | None, data_root: str = "data/processed",
    filter_refs: tuple[str, ...] = (),
) -> DensityVerdict | None:
    """Kết luận cho một plan, hoặc ``None`` khi W29 không có gì để nói.

    W29 áp cho **tổng hợp** của measure ``point_in_time``. Áp nó cho ĐẾM của một
    measure sẽ tạo ra đúng lớp lỗi "đếm thừa hưởng bộ lọc của đo" — một câu hỏi
    *bao nhiêu listing* là câu hỏi về LISTING, không về việc chỉ số kia đo được
    hay không, nên nó vẫn phải trả lời được.

    NHƯNG một ĐẾM có **bộ lọc** đặt trên cột thưa là chuyện khác hẳn, và phân
    biệt được bằng hành vi: *"bao nhiêu listing giảm giá trên 50% tại VN ngày
    03/07"* trả **0** trên bộ 20 ngày, nơi ``discount_percent`` chỉ có 5 quan
    sát trong 668 dòng của ngày đó — sự thật là 8, và cả gate, verifier lẫn A22
    đều thấy số 0 hợp lệ. Ở đây bộ lọc KHÔNG chọn ra tập rỗng; nó chọn ra tập
    *không quan sát được*, và hai thứ đó hiện ra giống hệt nhau. Vì vậy ref của
    bộ lọc luôn được kiểm, bất kể phép tổng hợp là gì (LUẬT W29-R7).
    """
    from gladiators.domain.catalog import CATALOG

    scope = tuple(filter_refs)
    if aggregation not in (None, "count", "share"):
        scope = tuple(dict.fromkeys(scope + tuple(refs)))
    if not scope:
        return None

    dense, refuse = thresholds(data_root)
    worst: DensityVerdict | None = None
    for ref in scope:
        obj = CATALOG.get(ref)
        if obj is None or obj.kind not in {"measure", "derived_metric"}:
            continue
        for column in obj.physical:
            if mode_of(column, data_root) != "point_in_time":
                continue
            coverage = coverage_of(column, dates, country, data_root)
            if coverage is None:
                continue
            action = (
                "allow" if coverage >= dense
                else "qualify" if coverage >= refuse
                else "clarify"
            )
            verdict = DensityVerdict(
                column=column, mode="point_in_time", coverage=coverage,
                observed_rows=0, scope_rows=0, action=action,
            )
            if worst is None or coverage < worst.coverage:
                worst = verdict
    return worst
