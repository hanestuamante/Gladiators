"""Một cột toàn False nghĩa là gì — và ai được quyền nói (W8.1, SolutionSpec2808 §9.2).

"Đã quan sát và đúng là không có cái nào" với "chỗ này không thu thập được" cho
HAI câu trả lời trái ngược nhau từ cùng một cột. Không dữ liệu nào trong dataset
phân biệt được hai thứ đó, nên nó là một quyết định của NGƯỜI SỞ HỮU DỮ LIỆU.

Mặc định là ``unknown`` và ``unknown`` fail-closed: viết code trả lời trước khi
có quyết định sẽ đẻ ra một câu trả lời trông rất chuẩn, có số má đầy đủ, và sai
âm thầm — đúng lớp lỗi ở §2 của spec.

Agent không được điền ``approved_by`` — cùng luật với A12-R6 và
``ValueClassRule.decision_id``: một chữ ký do máy gõ biến "đã có người quyết"
thành một chuỗi ký tự.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

ObservationSemantics = Literal["observed", "not_collected", "unknown"]


class ColumnSemanticsError(ValueError):
    """Registry ngữ nghĩa quan sát tự mâu thuẫn — nổ lúc import, không lúc chạy."""


@dataclass(frozen=True)
class ColumnSemantics:
    column: str                  # "<table>.<column>"
    semantics: ObservationSemantics
    approved_by: str | None      # None khi semantics == "unknown"
    approved_at: str | None
    caveat_key: str | None       # message key BẮT BUỘC khi semantics == "observed"


COLUMN_SEMANTICS: dict[str, ColumnSemantics] = {
    "products_clean.csv.is_ad_bool": ColumnSemantics(
        "products_clean.csv.is_ad_bool", "unknown", None, None, None,
    ),
    "products_clean.csv.is_sold_out_bool": ColumnSemantics(
        "products_clean.csv.is_sold_out_bool", "unknown", None, None, None,
    ),
}


def _check(registry: dict[str, ColumnSemantics]) -> None:
    # Đọc từ binding snapshot (219 cột thật của 7 artifact) — cùng nguồn mà
    # _project_relation dùng, nên "cột tồn tại" nghĩa là tồn tại THẬT.
    from gladiators.domain.bindings import default_binding_snapshot

    snapshot = default_binding_snapshot()
    known_columns = {
        f"{table_name}.{column.name}"
        for table_name, table in snapshot.tables.items()
        for column in table.columns
    }
    for key, spec in registry.items():
        if key != spec.column:
            raise ColumnSemanticsError(f"khoá {key} lệch spec.column {spec.column}")
        if spec.column not in known_columns:
            raise ColumnSemanticsError(f"cột không tồn tại trong tables.py: {spec.column}")
        if spec.semantics != "unknown" and (not spec.approved_by or not spec.approved_at):
            raise ColumnSemanticsError(
                f"{spec.column}: semantics {spec.semantics!r} cần approved_by/approved_at "
                "— quyết định của chủ dữ liệu, không phải của code",
            )
        if spec.semantics == "observed" and not spec.caveat_key:
            raise ColumnSemanticsError(
                f"{spec.column}: observed bắt buộc có caveat_key — một cột toàn False "
                "trả lời được thì câu trả lời phải mang lời dè chừng của nó",
            )


REGISTRY_HASH: str = hashlib.sha256(json.dumps(
    [
        {"column": spec.column, "semantics": spec.semantics,
         "approved_by": spec.approved_by, "approved_at": spec.approved_at,
         "caveat_key": spec.caveat_key}
        for spec in sorted(COLUMN_SEMANTICS.values(), key=lambda item: item.column)
    ],
    ensure_ascii=False, sort_keys=True, separators=(",", ":"),
).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ColumnObservation:
    """Kết quả có kiểu của ``classify_column_observation`` khi registry ĐÃ quyết."""

    column: str
    semantics: ObservationSemantics
    caveat_key: str | None


# Hai loại yêu cầu được nhận diện riêng: hỏi CỜ quảng cáo và hỏi trạng thái hết
# hàng. Câu hỏi HIỆU QUẢ quảng cáo (impression/click/chi phí) không thuộc đây —
# nó đúng là A-MISSING-ADS ở mọi trạng thái registry.
_AD_FLAG_MARKERS = (
    "duoc gan co quang cao", "gan co quang cao", "co quang cao",
    "dang quang cao", "flagged as ad", "is ad", "iklan berbayar",
)
_SOLD_OUT_MARKERS = ("het hang", "sold out", "chay hang", "habis terjual", "stok habis")
_AD_PERFORMANCE_MARKERS = (
    "impression", "click", "chi phi", "hieu qua", "ad spend", "ctr",
)

_COLUMN_BY_KIND = {
    "ad_flag": "products_clean.csv.is_ad_bool",
    "sold_out": "products_clean.csv.is_sold_out_bool",
}


def classify_column_observation(normalized_text: str):
    """``ColumnObservation`` khi câu hỏi chạm một cột registry ĐÃ QUYẾT, else None.

    ``unknown`` trả ``None`` — giữ nguyên đường từ chối hiện hành của từng câu.
    Đây là ĐƯỜNG GỌI DUY NHẤT đọc registry ở runtime: không đặt nhánh kiểm thứ
    hai trong gate hay synthesizer.
    """
    if any(marker in normalized_text for marker in _AD_PERFORMANCE_MARKERS):
        return None  # hiệu quả quảng cáo: dataset thật sự không có, mọi trạng thái
    kind = None
    if any(marker in normalized_text for marker in _AD_FLAG_MARKERS):
        kind = "ad_flag"
    elif any(marker in normalized_text for marker in _SOLD_OUT_MARKERS):
        kind = "sold_out"
    if kind is None:
        return None
    spec = COLUMN_SEMANTICS[_COLUMN_BY_KIND[kind]]
    if spec.semantics == "unknown":
        return None
    return ColumnObservation(spec.column, spec.semantics, spec.caveat_key)


_check(COLUMN_SEMANTICS)
