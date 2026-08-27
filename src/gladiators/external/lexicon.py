"""Nấc 1 — chuẩn hoá về chuỗi ĐÃ CÓ trong dataset (Spec2308 §WP-A12.1).

Luật vàng của toàn bộ nấc 1:

    kết quả tìm kiếm chỉ được phép **CHỌN** trong tập đã có,
    không bao giờ được phép **THÊM** vào tập.

Giữ luật đó thì mọi bất biến hiện tại còn nguyên và ``verifier`` không cần biết
là có nó: một giá trị trả về từ đây luôn là một chuỗi đã tồn tại trong dữ liệu,
nên nó không thể trở thành một claim không có evidence.

Ranh giới giữa "hiểu câu hỏi" và "bịa dữ liệu" nằm đúng ở bước 4 dưới đây: khớp
**0 hoặc >1** thì trả ``None`` và bỏ. Không đoán. Một tên gần giống bị đoán
thành tên khác là đúng lớp lỗi tệ nhất của hệ này (A4-R4).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from gladiators.agent.value_probe import INDEXED_REFS, _fold, _index
from gladiators.external.injection_guard import sanitize_and_check

# Cụm ứng viên tối thiểu. Ngắn hơn thì một mảnh chữ bất kỳ trong snippet cũng
# khớp được một tên trong index, và "chọn trong tập đã có" biến thành "chọn bừa
# trong tập đã có".
MIN_SURFACE_LENGTH = 4

_TOKEN = re.compile(r"[\wÀ-ỹ]+", re.UNICODE)


@dataclass(frozen=True)
class LexiconResolution:
    """Một lần chuẩn hoá, kèm đủ thứ để kiểm lại nó sau."""

    surface: str
    resolved: str | None
    ref: str
    country: str
    source_id: str | None = None
    guard_hits: tuple[str, ...] = ()
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "surface": self.surface, "resolved": self.resolved, "ref": self.ref,
            "country": self.country, "source_id": self.source_id,
            "guard_hits": list(self.guard_hits), "reason": self.reason,
        }


def normalize_to_dataset_value(
    surface: str, ref: str, country: str, *, source_id: str | None = None,
) -> LexiconResolution:
    """Trả về một giá trị **CÓ THẬT** trong value index, hoặc ``None``.

    ``surface`` là văn bản đến từ bên ngoài, nên nó đi qua ``injection_guard``
    TRƯỚC mọi thứ khác (A12-R2) — **không có ngoại lệ, kể cả ở nấc 1**. Một câu
    ép model nằm trong một snippet dùng để "chuẩn hoá tên thương hiệu" vẫn là một
    câu ép model.
    """
    guard = sanitize_and_check(surface)
    if not guard.safe:
        return LexiconResolution(
            surface=surface, resolved=None, ref=ref, country=country,
            source_id=source_id, guard_hits=guard.hits, reason="blocked_by_guard",
        )
    if ref not in INDEXED_REFS:
        return LexiconResolution(
            surface=surface, resolved=None, ref=ref, country=country,
            source_id=source_id, reason="ref_not_indexed",
        )

    known = _index().get(ref, {}).get(country)
    if not known:
        # Thiếu chỉ mục là thiếu THÔNG TIN để kết luận, không phải bằng chứng
        # rằng giá trị không tồn tại.
        return LexiconResolution(
            surface=surface, resolved=None, ref=ref, country=country,
            source_id=source_id, reason="index_unavailable",
        )

    matches = _candidates(guard.text, known)
    if len(matches) != 1:
        return LexiconResolution(
            surface=surface, resolved=None, ref=ref, country=country,
            source_id=source_id,
            reason="no_match" if not matches else "ambiguous_match",
        )
    return LexiconResolution(
        surface=surface, resolved=_original_of(matches[0], ref, country),
        ref=ref, country=country, source_id=source_id, reason="resolved",
    )


def _candidates(text: str, known: set[str]) -> list[str]:
    """Giá trị trong index xuất hiện NGUYÊN VĂN trong văn bản đã guard.

    Chỉ giữ cụm dài nhất khi một cụm nằm trong cụm khác: "Nestlé" nằm trong
    "Nestlé Chính hãng", và đếm cả hai sẽ biến một khớp rõ ràng thành một khớp
    mơ hồ rồi bỏ mất nó.
    """
    folded = f" {_fold(text)} "
    hits = [
        name for name in known
        if len(name) >= MIN_SURFACE_LENGTH and f" {name} " in folded
    ]
    return [
        name for name in hits
        if not any(name != other and name in other for other in hits)
    ]


def _original_of(folded: str, ref: str, country: str) -> str | None:
    """Chuỗi NGUYÊN VĂN trong dataset ứng với dạng đã fold.

    Trả bản đã fold sẽ là trả một chuỗi không tồn tại trong dữ liệu — đúng thứ
    luật vàng cấm, chỉ ở dạng khó thấy hơn.
    """
    import json
    from gladiators.agent.value_probe import VALUE_INDEX_PATH

    if not VALUE_INDEX_PATH.exists():
        return None
    payload = json.loads(VALUE_INDEX_PATH.read_text(encoding="utf-8"))
    for name in (payload.get("values") or {}).get(ref, {}).get(country, []):
        if _fold(name) == folded:
            return name
    return None


def candidate_surfaces(text: str) -> tuple[str, ...]:
    """Cụm danh từ ứng viên, lấy thô từ snippet đã guard.

    Cố ý thô: đây chỉ là bước sinh ứng viên, và bước quyết định là phép đối chiếu
    CHÍNH XÁC với value index ở trên. Một bộ sinh ứng viên tinh vi hơn không làm
    kết quả đúng hơn — nó chỉ làm nhiều thứ hơn bị bỏ ở bước sau.
    """
    tokens = _TOKEN.findall(text)
    surfaces: list[str] = []
    for size in (3, 2, 1):
        for start in range(len(tokens) - size + 1):
            phrase = " ".join(tokens[start:start + size])
            if len(phrase) >= MIN_SURFACE_LENGTH:
                surfaces.append(phrase)
    return tuple(dict.fromkeys(surfaces))
