"""Dò tồn tại giá trị — Spec2308 §WP-A5.1, nâng schema v2 ở SolutionSpec2808 §2.

Bản song sinh của ``A-ENTITY-NOT-FOUND`` cho **giá trị chiều**: hỏi về một
thương hiệu không có trong dữ liệu thì phải bị chặn **sớm**, thay vì lập cả kế
hoạch rồi mới hỏng ở một tầng khác với một lý do mô tả sai vấn đề.

Không LLM, không truy vấn thêm: chỉ tra một chỉ mục dựng sẵn.

A4-R4: khớp **chính xác theo token đã chuẩn hoá**, không fuzzy. Một tên gần
giống bị đoán thành tên khác là đúng lớp lỗi tệ nhất của hệ này.

**W1.1 — vì sao chỉ mục phải mang cả bản gốc.** Bản v1 fold tên rồi chỉ giữ bản
đã fold; literal ``"bibica"`` đi thẳng vào predicate và ``brand = 'bibica'`` trả
**0 dòng** trong khi dữ liệu ghi ``Bibica`` và đáp án là **96**. Số 0 đó đi qua
mọi lớp kiểm như một "kết quả rỗng hợp lệ" — trả bản đã fold là trả một chuỗi
KHÔNG tồn tại trong dữ liệu.
"""
from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
import os
from pathlib import Path

# Đường dẫn chỉ mục giá trị. Cho phép trỏ đi nơi khác để chạy được một BẢN DỮ
# LIỆU khác mà không ghi đè chỉ mục của bản đang phát hành: hai bản có
# dataset_version khác nhau, và ``assert_index_matches`` fail-closed khi lệch —
# nên "dùng chung một file" tương đương "chỉ chạy được đúng một bản".
VALUE_INDEX_PATH = Path(
    os.environ.get("GLADIATORS_VALUE_INDEX") or "artifacts/value_index.json"
)

# W1.1: loader v2 phải TỪ CHỐI payload v1 — một chỉ mục v1 (list) nạp bằng loader
# v2 (dict) sẽ đọc list thành iterable của ký tự và bind ra literal một chữ cái.
INDEX_SCHEMA_VERSION = "value-index.v2"

# Chỉ ba chiều này có chỉ mục; ref khác không dò được và phải đi lối cũ.
INDEXED_REFS = frozenset({
    "dim.platform_category_name", "dim.brand", "dim.shop_name",
})


def _fold(value: str) -> str:
    lowered = str(value).strip().lower().replace("đ", "d")
    stripped = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in stripped if unicodedata.category(char) != "Mn")


@lru_cache(maxsize=1)
def _payload() -> dict:
    """Payload thô đã qua kiểm schema. Sai schema ⇒ ``{}`` như khi thiếu file."""
    if not VALUE_INDEX_PATH.exists():
        return {}
    try:
        payload = json.loads(VALUE_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if payload.get("schema_version") != INDEX_SCHEMA_VERSION:
        return {}
    values = payload.get("values")
    if not isinstance(values, dict):
        return {}
    for per_country in values.values():
        if not isinstance(per_country, dict):
            return {}
        for mapping in per_country.values():
            if not isinstance(mapping, dict):
                return {}
    ambiguous = payload.get("ambiguous", {})
    if not isinstance(ambiguous, dict):
        return {}
    return payload


def _index() -> dict[str, dict[str, dict[str, str]]]:
    """``ref -> country -> {folded: original}``. Rỗng ⇒ vòng P im lặng bỏ qua.

    Im lặng ở đây là đúng: thiếu chỉ mục là thiếu THÔNG TIN để kết luận, không
    phải bằng chứng rằng giá trị không tồn tại.
    """
    return _payload().get("values") or {}


def _ambiguous() -> dict[str, dict[str, dict[str, list[str]]]]:
    """Khoá fold mà HAI TÊN GỐC trở lên cùng đổ về — tồn tại nhưng không bind được.

    Đo được trên dataset thật: "Trang điểm mắt"/"Trang điểm mặt" chỉ khác nhau ở
    dấu, mà ``_fold`` bỏ dấu. Bind một trong hai là lọc thầm theo tên sai; chấm
    nó là vắng mặt (A-VALUE-NOT-FOUND) cũng sai vì giá trị CÓ THẬT. Lối đúng duy
    nhất là "biết nó tồn tại, từ chối chọn hộ".
    """
    return _payload().get("ambiguous") or {}


def is_ambiguous(ref: str, country: str, folded: str) -> bool:
    return folded in (_ambiguous().get(ref, {}).get(country) or {})


def index_is_available() -> bool:
    return bool(_index())


def index_dataset_version() -> str | None:
    """Chỉ mục này dựng cho dataset nào — để preflight so với repository."""
    version = _payload().get("dataset_version")
    return str(version) if version else None


def original_of(ref: str, country: str, folded: str) -> str | None:
    """Bản NGUYÊN VĂN trong dataset ứng với một khoá đã fold — API công khai.

    Thay cho ``lexicon._original_of`` từng đọc lại JSON: trong cùng một repo,
    một nhánh làm đúng còn nhánh kia làm sai — W1 hợp nhất chúng về đây.
    """
    return (_index().get(ref, {}).get(country) or {}).get(folded)



def assert_index_matches(repository_dataset_version: str) -> None:
    """Preflight lúc dựng runtime (§2.5): chỉ mục LỆCH thì phải nổ, THIẾU thì thôi.

    Thiếu chỉ mục là thiếu *thông tin* — vòng dò im lặng bỏ qua như hôm nay.
    Chỉ mục lệch phiên bản là thông tin *SAI*: nó sinh ra literal thuộc về một
    dataset khác, và mọi cờ "đã verified" từ nó đều vô nghĩa.
    """
    from gladiators.data.dataset_version import DatasetVersionError

    if not VALUE_INDEX_PATH.exists():
        return
    try:
        payload = json.loads(VALUE_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetVersionError(
            f"Không đọc được {VALUE_INDEX_PATH}: {exc}. Dựng lại bằng "
            "scripts/build_value_index.py."
        ) from exc
    schema = payload.get("schema_version")
    if schema != INDEX_SCHEMA_VERSION:
        raise DatasetVersionError(
            f"Chỉ mục giá trị mang schema {schema!r}, runtime cần "
            f"{INDEX_SCHEMA_VERSION!r}. Dựng lại bằng scripts/build_value_index.py."
        )
    index_version = payload.get("dataset_version")
    if index_version != repository_dataset_version:
        raise DatasetVersionError(
            f"Chỉ mục giá trị dựng cho dataset {index_version!r} nhưng repository "
            f"đang là {repository_dataset_version!r}. Dựng lại bằng "
            "scripts/build_value_index.py."
        )

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
        folded_value = _fold(value)
        if folded_value not in known and not is_ambiguous(ref, country, folded_value):
            missing.append((ref, value))
    return tuple(missing)


MIN_VALUE_LENGTH = 6


def bind_values(
    normalized_question: str, country: str | None,
    dimension_refs: frozenset[str] = frozenset(),
) -> tuple[tuple[str, str], ...]:
    """Giá trị có thật xuất hiện nguyên văn trong câu — trả **BẢN GỐC** (W1.1).

    Khớp CHÍNH XÁC theo token đã chuẩn hoá, không fuzzy (A4-R4).

    **Maximal span, không phải ``max(hits, key=len)``** (§2.3): giữ vị trí
    bắt đầu/kết thúc của từng khớp, bỏ khớp nằm TRỌN trong một khớp dài hơn, rồi
    chỉ bind khi còn đúng MỘT span cực đại. Hai span cực đại rời nhau (câu nêu
    hai brand để so sánh) ⇒ không chọn span dài hơn — chọn là âm thầm thu hẹp
    một câu hỏi nhiều thực thể thành một thực thể. Luật này vẫn cho
    ``Bibica Official Store`` thắng phần con ``Bibica``.
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
        mapping = per_country.get(country) or {}
        spans: list[tuple[int, int, str]] = []
        for name in mapping:
            if len(name) < MIN_VALUE_LENGTH:
                continue
            start = folded.find(f" {name} ")
            if start >= 0:
                spans.append((start + 1, start + 1 + len(name), name))
        # Bỏ span nằm trọn trong span khác dài hơn.
        maximal = [
            (start, end, name) for start, end, name in spans
            if not any(
                (o_start <= start and end <= o_end) and (o_start, o_end) != (start, end)
                for o_start, o_end, _ in spans
            )
        ]
        if len(maximal) != 1:
            continue
        original = mapping.get(maximal[0][2])
        if original is not None:
            bound.append((ref, original))
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
        known = index.get(ref, {}).get(country) or {}
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
                ambiguous_keys = _ambiguous().get(ref, {}).get(country) or {}
                if not any(candidate in name for name in known) and not any(
                    candidate in name for name in ambiguous_keys
                ):
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
