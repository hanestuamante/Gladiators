"""Dò tồn tại giá trị — Spec2308 §WP-A5.1, vòng P.

Bản song sinh của ``A-ENTITY-NOT-FOUND`` cho **giá trị chiều**: hỏi về một
thương hiệu không có trong dữ liệu thì phải bị chặn **sớm**, thay vì lập cả kế
hoạch rồi mới hỏng ở một tầng khác với một lý do mô tả sai vấn đề.

Không LLM, không truy vấn thêm: chỉ tra một chỉ mục dựng sẵn.

A4-R4: khớp **chính xác theo token đã chuẩn hoá**, không fuzzy. Một tên gần
giống bị đoán thành tên khác là đúng lớp lỗi tệ nhất của hệ này.
"""
from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

VALUE_INDEX_PATH = Path("artifacts/value_index.json")

# Chỉ ba chiều này có chỉ mục; ref khác không dò được và phải đi lối cũ.
INDEXED_REFS = frozenset({
    "dim.platform_category_name", "dim.brand", "dim.shop_name",
})


def _fold(value: str) -> str:
    lowered = str(value).strip().lower().replace("đ", "d")
    stripped = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in stripped if unicodedata.category(char) != "Mn")


@lru_cache(maxsize=1)
def _index() -> dict[str, dict[str, set[str]]]:
    """Chỉ mục đã fold. Không có file ⇒ rỗng ⇒ vòng P im lặng bỏ qua.

    Im lặng ở đây là đúng: thiếu chỉ mục là thiếu THÔNG TIN để kết luận, không
    phải bằng chứng rằng giá trị không tồn tại.
    """
    if not VALUE_INDEX_PATH.exists():
        return {}
    try:
        payload = json.loads(VALUE_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        ref: {country: {_fold(name) for name in names} for country, names in per.items()}
        for ref, per in (payload.get("values") or {}).items()
    }


def index_is_available() -> bool:
    return bool(_index())


def missing_values(request) -> tuple[tuple[str, str], ...]:
    """Cặp ``(ref, giá trị)`` mà chỉ mục nói là KHÔNG tồn tại ở thị trường này.

    Chỉ xét predicate có ref nằm trong ``INDEXED_REFS`` và giá trị là chuỗi —
    một predicate boolean hay số không phải "giá trị dữ liệu" theo nghĩa này.
    """
    index = _index()
    if not index:
        return ()

    country = None
    for predicate in request.filters:
        if predicate.field_ref == "dim.country" and isinstance(predicate.value_binding, str):
            country = predicate.value_binding
    if country is None:
        return ()

    missing: list[tuple[str, str]] = []
    for predicate in request.filters:
        ref = predicate.field_ref
        value = predicate.value_binding
        if ref not in INDEXED_REFS or not isinstance(value, str) or not value.strip():
            continue
        known = index.get(ref, {}).get(country)
        if known is None:
            continue
        if _fold(value) not in known:
            missing.append((ref, value))
    return tuple(missing)


MIN_VALUE_LENGTH = 6


def bind_values(
    normalized_question: str, country: str | None,
    dimension_refs: frozenset[str] = frozenset(),
) -> tuple[tuple[str, str], ...]:
    """Giá trị có thật xuất hiện nguyên văn trong câu — A4.3 bước 2.

    Khớp CHÍNH XÁC theo token đã chuẩn hoá, không fuzzy (A4-R4). Ưu tiên giá trị
    DÀI nhất: "Nestlé Chính hãng" phải thắng "Nestlé", vì bind cái ngắn hơn là
    lọc rộng hơn câu hỏi.

    Khớp nhiều giá trị cùng một ref ⇒ trả rỗng cho ref đó: câu hỏi đang gom
    nhóm, không lọc (§A4.4 bước 2).
    """
    index = _index()
    if not index or not country:
        return ()
    folded = f" {_fold(normalized_question)} "
    bound: list[tuple[str, str]] = []
    for ref, per_country in index.items():
        # Chỉ bind giá trị cho chiều mà câu hỏi ĐÃ nêu tên. Không có điều kiện
        # này, "giá TRUNG vị" khớp một danh mục tên "trung" và câu hỏi bị lọc
        # theo một chiều người dùng chưa bao giờ nhắc tới — lọc âm thầm, đúng
        # lớp lỗi tệ nhất của hệ này.
        if ref not in dimension_refs:
            continue
        names = per_country.get(country) or set()
        hits = [
            name for name in names
            if len(name) >= MIN_VALUE_LENGTH and f" {name} " in folded
        ]
        if len(hits) != 1:
            continue
        bound.append((ref, max(hits, key=len)))
    return tuple(bound)


# Alias của ba chiều có chỉ mục, dùng để biết câu hỏi đang NÓI VỀ chiều nào.
_DIMENSION_CUES: dict[str, tuple[str, ...]] = {
    "dim.brand": ("brand", "thuong hieu", "merek"),
    "dim.shop_name": ("shop", "cua hang", "toko"),
    "dim.platform_category_name": ("danh muc", "category", "kategori"),
}


def named_but_absent(
    normalized_question: str, country: str | None,
    dimension_refs: frozenset[str] = frozenset(),
    raw_question: str = "",
) -> tuple[tuple[str, str], ...]:
    """Câu nêu một giá trị CỤ THỂ cho một chiều, mà giá trị đó không có.

    ``missing_values`` chỉ nhìn predicate đã bind, mà bind chỉ xảy ra khi giá trị
    TỒN TẠI — nên riêng nó không bao giờ bắt được ca này. §A4.4 bước 2 gọi đây là
    nhánh ``data_absent``, và nó phải từ chối chứ KHÔNG được mở rộng câu hỏi
    thành "tất cả các brand" (A4-R5).

    Dấu hiệu "nêu một giá trị cụ thể" cố ý HẸP: token ngay sau tên chiều phải
    trông như một TÊN RIÊNG — viết hoa trong câu gốc, hoặc nằm trong ngoặc kép.

    Không có điều kiện đó, "Rating theo brand KHÔNG TỒN TẠI tại VN" bị đọc thành
    'có một brand tên là "không"', và một câu mô tả bị biến thành một tên riêng.
    """
    index = _index()
    if not index or not country:
        return ()
    folded = _fold(normalized_question)
    words = folded.split()
    stop = {"tai", "o", "cua", "theo", "la", "bao", "nhieu", "nao", "va", "trong",
            "ngay", "vn", "id", "viet", "nam", "indonesia", "cao", "thap", "nhat"}
    absent: list[tuple[str, str]] = []
    for ref, cues in _DIMENSION_CUES.items():
        if ref not in dimension_refs:
            continue
        known = index.get(ref, {}).get(country) or set()
        for cue in cues:
            parts = cue.split()
            for position in range(len(words) - len(parts)):
                if words[position:position + len(parts)] != parts:
                    continue
                candidate = words[position + len(parts)]
                if candidate in stop or len(candidate) < 4:
                    continue
                if not _looks_like_a_proper_name(candidate, raw_question):
                    continue
                if not any(candidate in name for name in known):
                    absent.append((ref, candidate))
                break
    return tuple(dict.fromkeys(absent))


def _looks_like_a_proper_name(folded_token: str, raw_question: str) -> bool:
    """Token có viết hoa hoặc nằm trong ngoặc kép ở câu GỐC hay không."""
    if not raw_question:
        return False
    import re

    quoted = " ".join(re.findall(r"[\"“”'](.+?)[\"“”']", raw_question))
    if quoted and folded_token in _fold(quoted):
        return True
    for word in re.findall(r"\S+", raw_question):
        if _fold(word).strip(".,?!;:") == folded_token and word[:1].isupper():
            return True
    return False
