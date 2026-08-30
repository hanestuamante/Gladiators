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

import re

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
# W19: v3 thêm khối ``universe``. Loader v3 PHẢI từ chối payload v2 — luật W1.1
# đã học một lần: loader v2 đọc payload v1 (list) thành iterable ký tự và bind
# literal MỘT CHỮ CÁI. Cùng lớp lỗi lặp lại nếu v3 không kiểm ``schema_version``.
INDEX_SCHEMA_VERSION = "value-index.v3"

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


def _universe() -> dict[str, dict[str, dict]]:
    """``ref -> {folded: {original, countries}}`` — W19 schema v3.

    Giá trị CÓ trong dataset nhưng KHÔNG ở thị trường được hỏi là một trạng thái
    thứ ba, khác hẳn "người dùng gõ một tên không có thật". Nhập hai thứ này làm
    một tạo ra một lời từ chối NÓI SAI SỰ THẬT về dataset.
    """
    return _payload().get("universe") or {}


def in_market(ref: str, folded_name: str, country: str) -> bool:
    """Giá trị này có xuất hiện ở thị trường được hỏi không (W19)."""
    entry = (_universe().get(ref) or {}).get(folded_name)
    return bool(entry) and country in (entry.get("countries") or ())


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


# W18 — ``MIN_VALUE_LENGTH`` ĐÃ XOÁ.
#
# Nó sinh ra để chặn ``"gia"`` khớp trong ``"giá trị"``, và nó giải quyết đúng
# vấn đề bằng một tham số KHÔNG PHÂN BIỆT ĐƯỢC *chuỗi ngắn ngẫu nhiên* với *tên
# riêng ngắn*: `ORION` (5 ký tự) là một brand có thật và bị chặn cùng lúc.
#
# Thay bằng ba điều kiện CẤU TRÚC (Spec3008 §5.2). Điều kiện (1) là cái thay thế
# đúng cho ngưỡng: alias binder chạy TRƯỚC value binder trên cùng một lattice,
# nên ``gia`` trong ``gia tri`` đã bị tiêu thụ và không còn là span dư — nó chặn
# ĐÚNG LỚP mà ngưỡng nhắm tới, và không chặn tên riêng ngắn.


# Chiều mà giá trị CHỈ được bind khi câu đã NÊU TÊN chiều đó.
#
# Tên danh mục sàn là DANH TỪ CHUNG — chúng chính là từ chỉ loại hàng, nên chúng
# xuất hiện khắp nơi trong mô tả sản phẩm và trong tiếng Việt thường ngày. Bốn
# va chạm đo được trên chính bộ đề: ``Nấm``←"Nam" (trong "Việt Nam"),
# ``Thang``←"tháng", ``Giấm``←"giảm", ``Cua``←"của". Brand và tên shop là DANH
# TỪ RIÊNG và không có lớp va chạm đó — ``ORION``, ``Bibica``, ``Chupa Chups``
# không trùng từ thường nào.
#
# Ngoài ra bind một giá trị danh mục ép plan đi qua quan hệ
# ``in_platform_category``, và trên nhiều hình plan nó cho "Grain Join không
# khớp relation registry" — tức đổi một chỗ lọc-âm-thầm lấy một plan không chạy.
NAMED_ONLY_REFS = frozenset({"dim.platform_category_name"})


def _diacritics_match(raw_span: str, folded_name: str) -> bool:
    """Cụm trong câu có khớp giá trị KỂ CẢ DẤU không (không phân biệt hoa/thường)?

    So bản đã fold của hai bên là so hai thứ đã bị xoá mất phần phân biệt nghĩa.
    """
    return _diacritic_key(raw_span) == _diacritic_key(_original_of(folded_name))


def _diacritic_key(text: str) -> str:
    """Chữ thường, BỎ dấu câu, GIỮ dấu thanh.

    So nguyên văn không được: tên trong dữ liệu mang dấu câu của riêng nó
    (``"Richy - Chi nhánh Miền Nam"``) còn câu hỏi thì không nhất thiết. Bỏ dấu
    thanh cũng không được — đó chính là thứ phân biệt ``Giấm`` với ``giảm``.
    """
    return " ".join(re.sub(r"[^\w\s]", " ", text).casefold().split())


_ORIGINAL_CACHE: dict[str, str] = {}


def _original_of(folded_name: str) -> str:
    """Bản gốc (còn dấu) của một khoá đã fold, tra qua ``universe``."""
    if not _ORIGINAL_CACHE:
        for entries in _universe().values():
            for folded, entry in entries.items():
                _ORIGINAL_CACHE.setdefault(folded, str(entry["original"]))
    return _ORIGINAL_CACHE.get(folded_name, folded_name)


def token_key(text: str) -> str:
    """Chuỗi đã fold theo TOKEN, bỏ dấu câu — MỘT cách biểu diễn duy nhất.

    Khoá chỉ mục giữ nguyên dấu câu của dữ liệu (``"richy - chi nhanh mien
    nam"``) còn lattice sinh token không mang dấu câu, nên so trực tiếp hai bên
    là so hai CÁCH BIỂU DIỄN KHÁC NHAU của cùng một chuỗi: tên shop không bao
    giờ khớp phần dư, và span con ``"richy"`` của nó thì khớp — hệ lọc theo một
    brand người dùng không nêu.
    """
    from gladiators.planner.spans import tokenize

    return " ".join(t.normalized for t in tokenize(text) if not t.is_punct)


def _all_function_words(folded_name: str) -> bool:
    from gladiators.domain.function_words import is_function_word

    parts = folded_name.split()
    return bool(parts) and all(is_function_word(part) for part in parts)


def free_spans(ledger) -> dict[str, str]:
    """Cụm CÒN DƯ trên lattice — ứng viên giá trị của W18 (điều kiện 1).

    Điều kiện 2 của spec là *hình dạng tên riêng **hoặc** khớp nguyên văn một
    khoá chỉ mục*; vế thứ hai là cái cho phép ``bibica`` viết thường vẫn bind, và
    phép khớp CHÍNH XÁC ở điều kiện 3 đã thi hành nó. Nên chỗ này chỉ còn lọc
    theo "còn dư", và đó mới là điều kiện làm việc thật.

    Ca đo được cho thấy vì sao "còn dư" là điều kiện QUYẾT ĐỊNH, không phải hình
    dạng: ``"Giá trung vị tại Việt Nam"`` có ``Việt``/``Nam`` viết hoa, nên một
    guard chỉ-hình-dạng cho qua, và ``Nấm`` (fold thành ``nam``) khớp bên trong
    TÊN NƯỚC — câu bị lọc theo một danh mục người dùng chưa bao giờ nhắc tới.
    Country binder đã claim span đó trước (thứ tự §3.3) nên nó không còn dư, và
    lớp lỗi này đóng lại vì cấu trúc chứ không vì một heuristic.
    """
    # Một vùng TRONG NGOẶC KÉP là MỘT thực thể người dùng nêu, không phải một
    # túi từ để nhặt. Đo được: `"Scora Phytobright Gentle Low pH Cleanser
    # 100ml"` là tên một sản phẩm cụ thể, nhưng `SCORA` là một brand có thật nằm
    # trong đó — bind nó nới câu hỏi từ MỘT listing thành CẢ BRAND, một con số
    # rộng hơn câu hỏi và không lớp nào phía sau phát hiện được.
    quoted = {token.index for token in ledger.tokens if token.quoted}
    out: dict[str, str] = {}
    for span in ledger.free_spans(max_len=6):
        window = ledger.tokens[span.start:span.end]
        if any(token.is_punct for token in window):
            continue
        covered = {token.index for token in window}
        if quoted and (covered & quoted) and not quoted.issubset(covered):
            continue    # nằm TRONG một vùng ngoặc kép mà không phủ hết nó
        out.setdefault(span.normalized, " ".join(token.raw for token in window))
    return out


def bind_values(
    normalized_question: str, country: str | None,
    dimension_refs: frozenset[str] = frozenset(),
    ledger=None,
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
    # Một cách biểu diễn cho cả câu lẫn khoá chỉ mục (xem ``token_key``).
    folded = f" {token_key(normalized_question)} "
    candidates = free_spans(ledger) if ledger is not None else {}
    universe = _universe()

    # Gom span của MỌI ref trước, lọc cực đại sau. Lọc trong từng ref là chưa đủ:
    # "Richy" là một brand THẬT và cũng là phần đầu của tên shop "Richy - Chi
    # nhánh Miền Nam", nên mỗi ref tự thấy đúng một span cực đại của mình và cả
    # hai cùng bind — câu bị lọc theo một brand người dùng không nêu.
    per_ref: dict[str, list[tuple[int, int, str]]] = {}
    originals: dict[tuple[str, str], str] = {}
    for ref, per_country in index.items():
        if ledger is None and ref not in dimension_refs:
            # Không có lattice (caller cũ) ⇒ giữ nguyên hành vi trước W18: chỉ
            # bind cho chiều mà câu đã nêu tên.
            continue
        if ref in NAMED_ONLY_REFS and ref not in dimension_refs:
            continue
        mapping = dict(per_country.get(country) or {})
        # W19: giá trị CÓ trong dataset nhưng không ở thị trường được hỏi vẫn
        # bind — đáp án là 0, một kết quả rỗng hợp lệ.
        for name, entry in (universe.get(ref) or {}).items():
            mapping.setdefault(name, entry["original"])
        spans: list[tuple[int, int, str]] = []
        for name in mapping:
            key = token_key(name)
            if not key:
                continue
            if ledger is not None and key not in candidates:
                continue
            if ledger is not None and ref not in dimension_refs and not _diacritics_match(
                candidates[key], name,
            ):
                # Fold bỏ dấu, và tiếng Việt phân biệt nghĩa BẰNG dấu: `tháng`
                # fold thành `thang` và khớp danh mục **Thang**; `giảm` fold
                # thành `giam` và khớp **Giấm**. Câu bị lọc theo một danh mục
                # người dùng chưa bao giờ nhắc tới — cùng lớp với
                # `"giá trị"`→`measure.price` ở CLAUDE.md §3.1.
                #
                # ``Token.raw`` của W16 còn giữ nguyên dấu, nên phép kiểm này
                # làm được: khi câu KHÔNG nêu tên chiều, giá trị phải khớp cả
                # dấu. Câu ĐÃ nêu tên chiều thì không cần — người dùng đã nói rõ
                # họ đang lọc theo chiều nào.
                continue
            if _all_function_words(key):
                # "của" fold thành "cua" và khớp danh mục "Cua"; "Nam" trong
                # "Miền Nam" khớp "Nấm". Một cụm toàn từ chức năng KHÔNG BAO GIỜ
                # là một giá trị người dùng nêu — nó lọt vào phần dư chỉ vì chưa
                # binder nào cần nó.
                continue
            start = folded.find(f" {key} ")
            if start >= 0:
                spans.append((start + 1, start + 1 + len(key), key))
                originals[(ref, key)] = mapping[name]
        if spans:
            per_ref[ref] = spans

    every_span = [span for spans in per_ref.values() for span in spans]

    # W18-R1 — một span khớp ≥2 CHIỀU là một mơ hồ, không phải một lựa chọn.
    # ``Glad2Glow`` vừa là brand vừa là tên shop; chọn hộ là lọc thầm theo chiều
    # SAI. Khi câu đã NÊU TÊN một trong hai chiều thì người dùng đã tự phân
    # giải — dùng chiều đó và bỏ chiều kia. Không chiều nào được nêu ⇒ bỏ cả
    # hai, fail-closed.
    by_key: dict[str, list[str]] = {}
    for ref, spans in per_ref.items():
        for _, _, key in spans:
            by_key.setdefault(key, []).append(ref)
    dropped: set[tuple[str, str]] = set()
    for key, refs in by_key.items():
        if len(refs) < 2:
            continue
        named = [ref for ref in refs if ref in dimension_refs]
        winners = set(named) if len(named) == 1 else set()
        for ref in refs:
            if ref not in winners:
                dropped.add((ref, key))

    bound: list[tuple[str, str]] = []
    for ref, spans in per_ref.items():
        spans = [item for item in spans if (ref, item[2]) not in dropped]
        if not spans:
            continue
        maximal = [
            (start, end, name) for start, end, name in spans
            if not any(
                (o_start <= start and end <= o_end) and (o_end - o_start) > (end - start)
                for o_start, o_end, _ in every_span
            )
        ]
        if len(maximal) != 1:
            # W18-R2: hai span cực đại RỜI NHAU cùng chiều là một câu so sánh —
            # W17-R5 xử lý. Ở đây giữ hành vi cũ: không chọn hộ một trong hai.
            continue
        original = originals.get((ref, maximal[0][2]))
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
