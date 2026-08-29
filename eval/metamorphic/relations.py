"""Approved DR2607 metamorphic relations.

Every transform preserves language, market, date and currency.  Cross-language,
cross-market and unit/date changes are intentionally absent because they do not
preserve denotation.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Literal


# WP-B7.1 — additive. Bốn quan hệ cũ giữ nguyên ``kind="invariant"``, nên phân
# loại mới không đổi hành vi của bất kỳ phép kiểm nào đã có.
#
# ``directional`` và ``disjoint`` KHÔNG bảo toàn nghĩa — chúng cố ý đổi câu hỏi,
# nhưng đổi theo một chiều **dự đoán được**. Đó là cách kiểm tính đúng đắn khi
# không có đáp án chuẩn: quan hệ GIỮA hai câu trả lời vẫn kiểm được kể cả khi
# không ai biết câu trả lời đúng là gì.
RelationKind = Literal["invariant", "directional", "disjoint"]


@dataclass(frozen=True)
class MetamorphicRelation:
    relation_id: str
    transform: Callable[..., str]
    proof: str
    kind: RelationKind = "invariant"
    expectation: str | None = None
    changes_language: bool = False
    changes_country: bool = False
    changes_date: bool = False
    changes_currency: bool = False
    # W9.2: số ca tối thiểu để tỷ lệ của quan hệ này CÓ NGHĨA. Dưới ngưỡng ⇒
    # status "not_measured" và bị loại khỏi mẫu số của
    # metamorphic_consistency_rate — một tỷ lệ tính trên các quan hệ chưa từng
    # chạy là một tỷ lệ che đúng thứ cần xem (174/308 = 56,5% từng bị bỏ qua).
    min_applicable: int = 1


def quote_entity(question: str, entity: str) -> str:
    """Quotation only marks an existing entity span; it changes no operand."""
    if entity not in question:
        raise ValueError("entity không tồn tại nguyên văn trong question")
    return question.replace(entity, f'"{entity}"', 1)


def remove_vietnamese_diacritics(question: str) -> str:
    """ASCII folding preserves Vietnamese lexical content for parser robustness."""
    folded = question.replace("đ", "d").replace("Đ", "D")
    return "".join(
        char for char in unicodedata.normalize("NFD", folded)
        if unicodedata.category(char) != "Mn"
    )


def add_layout_noise(question: str) -> str:
    """Whitespace/newline/emoji are non-semantic presentation noise."""
    words = re.split(r"\s+", question.strip())
    return "  ".join(words[: max(1, len(words) // 2)]) + "\n🙂 " + " ".join(
        words[max(1, len(words) // 2):]
    )


def approved_same_language_paraphrase(question: str) -> str:
    """Only reviewed within-language synonyms are substituted.

    ``bao nhiêu`` KHÔNG được thay thẳng bằng ``số lượng``: trong khung phổ biến
    nhất — ``Có bao nhiêu X?`` — phép thay đó cho ra ``Có số lượng X?``, một câu
    không phải tiếng Việt đúng. Đo được: 24/40 phép kiểm áp dụng được của MR-1
    "hỏng", trong khi ``Số lượng X … là bao nhiêu?`` (paraphrase ĐÚNG ngữ pháp)
    được trả lời bình thường. Nghĩa là phép biến đổi sinh ra câu hỏi hỏng, chứ
    không phải hệ thống mong manh — và một phép biến đổi sinh input không hợp lệ
    thì mọi con số nó tạo ra đều vô nghĩa.

    Khung ``Có bao nhiêu X …?`` vì vậy được viết lại NGUYÊN KHUNG.
    """
    frame = re.match(
        r"^\s*Có bao nhiêu\s+(.+?)\s*\?\s*$",
        question, flags=re.IGNORECASE,
    )
    if frame:
        question = f"Số lượng {frame.group(1)} là bao nhiêu?"
    replacements = (
        (r"\bsản phẩm\b", "listing"),
        (r"\bcửa hàng\b", "shop"),
        (r"\bberapa\b", "jumlah"),
        (r"\bproduk\b", "listing"),
        (r"\btoko\b", "shop"),
    )
    result = question
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result

# --- B7.2: ba quan hệ KHÔNG bảo toàn, nhưng đổi theo chiều dự đoán được -------

def add_narrowing_filter(question: str) -> str:
    """Thêm một điều kiện lọc ĐÃ BIND ĐƯỢC ⇒ tập kết quả chỉ có thể nhỏ đi.

    Dùng đúng cụm đã có trong ``domain/qualifiers.py`` (WP-A4), không tự nghĩ từ
    mới: một cụm hệ thống không bind được sẽ bị bỏ âm thầm, và phép kiểm sẽ so
    hai câu hỏi giống hệt nhau rồi kết luận "đạt".
    """
    # W9.2: đổi từ "có voucher" sang "của shop chính hãng" — sau W8.3 cụm
    # voucher thành mơ hồ (hai khái niệm, hai ref) và biến thể sẽ clarify ⇒
    # skip vĩnh viễn. "chính hãng" là qualifier ĐÃ BIND (dim.shop_official).
    if "?" in question:
        return question.replace("?", " của shop chính hãng?", 1)
    return question + " của shop chính hãng"


def swap_to_other_market(question: str) -> str:
    """Đổi thị trường. Hai thị trường khác nhau thì kết quả KHÔNG được bằng nhau.

    Bằng nhau là dấu hiệu mạnh rằng phạm vi bị bỏ qua — đúng lớp lỗi mà
    ``p0-scope-dropped-vn-id`` khoá lại.
    """
    swaps = (
        ("Việt Nam", "Indonesia"), ("việt nam", "Indonesia"),
        ("VN", "Indonesia"), ("vn", "Indonesia"),
    )
    for source, target in swaps:
        if source in question:
            return question.replace(source, target, 1)
    for source, target in (("Indonesia", "Việt Nam"), ("ID", "Việt Nam")):
        if source in question:
            return question.replace(source, target, 1)
    raise ValueError("câu hỏi không nêu thị trường nào để đổi")


def flip_extremum(question: str) -> str:
    """Đổi "cao nhất" ↔ "thấp nhất". Hai đầu của một thang không được trùng dòng."""
    swaps = (
        ("cao nhất", "thấp nhất"), ("thấp nhất", "cao nhất"),
        ("nhiều nhất", "ít nhất"), ("ít nhất", "nhiều nhất"),
        ("tertinggi", "terendah"), ("terendah", "tertinggi"),
    )
    for source, target in swaps:
        if source in question:
            return question.replace(source, target, 1)
    raise ValueError("câu hỏi không nêu cực trị nào để đảo")


RELATIONS = (
    MetamorphicRelation("MR-1", approved_same_language_paraphrase, "Approved synonyms preserve operands."),
    MetamorphicRelation("MR-3", quote_entity, "Quotes only mark the same entity span.",
                        min_applicable=10),
    MetamorphicRelation("MR-4", remove_vietnamese_diacritics, "Diacritic folding preserves lexical meaning."),
    MetamorphicRelation("MR-5", add_layout_noise, "Layout noise changes no semantic operand."),
    MetamorphicRelation(
        "MR-6", add_narrowing_filter,
        "Thêm một điều kiện lọc chỉ có thể làm tập kết quả nhỏ đi, không lớn lên.",
        kind="directional", expectation="count_not_greater",
    ),
    MetamorphicRelation(
        "MR-7", swap_to_other_market,
        "Hai thị trường có tập listing rời nhau; kết quả bằng nhau nghĩa là phạm "
        "vi đã bị bỏ qua.",
        # W9.3: "hai phạm vi khác nhau phải cho SỐ khác nhau" là một đòi hỏi
        # sai về nguyên tắc — dữ liệu có đúng 10 shop ở MỖI thị trường, nên
        # bằng nhau là ĐÚNG. Kiểm CƠ CHẾ (scope thật sự đổi), không kiểm kết
        # quả; "suspect" biến mất khỏi từ vựng của MR-7.
        kind="disjoint", expectation="scope_actually_changed", changes_country=True,
    ),
    MetamorphicRelation(
        "MR-8", flip_extremum,  # min_applicable dưới
        "Hai đầu của một thang không thể cùng trỏ vào một dòng, trừ khi tập chỉ "
        "có đúng một dòng.",
        kind="disjoint", expectation="values_differ",
        min_applicable=10,
    ),
)


def validate_relations() -> None:
    """Quan hệ ``invariant`` phải bảo toàn ngôn ngữ/scope/unit. Quan hệ khác thì
    KHÔNG — chúng cố ý đổi, và ``expectation`` là thứ nói chúng đổi ra sao.

    B7-R2: mọi quan hệ phải mang ``proof``. Một biến đổi không giải thích được vì
    sao nó bảo toàn (hoặc đổi theo chiều nào) là một biến đổi không kiểm lại được.
    """
    for relation in RELATIONS:
        if not relation.proof.strip():
            raise ValueError(f"{relation.relation_id}: thiếu proof")
        if relation.kind == "invariant":
            if (
                relation.changes_language or relation.changes_country
                or relation.changes_date or relation.changes_currency
            ):
                raise ValueError(
                    f"{relation.relation_id}: quan hệ invariant không được đổi "
                    "ngôn ngữ/scope/unit.",
                )
        elif not relation.expectation:
            raise ValueError(
                f"{relation.relation_id}: quan hệ {relation.kind} phải khai "
                "expectation.",
            )
