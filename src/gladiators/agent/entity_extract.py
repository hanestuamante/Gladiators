"""Deterministic ID-first entity and market extraction."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal

LISTING_KEY = re.compile(r"\b(vn|id):(\d{6,12}):(\d{6,14})\b", re.IGNORECASE)

_ID_NOUNS = {
    "item": ("item", "san pham", "listing", "produk", "ma san pham", "ma id", "id"),
    "shop": ("shop id", "shop", "cua hang", "toko", "gian hang"),
    "promotion": ("promotion id", "promotion", "khuyen mai", "promo", "promosi", "chuong trinh"),
    "category": ("category id", "category", "danh muc", "kategori", "catid", "nganh hang"),
}
_KIND_FOR_NOUN = {
    "item": "item_id",
    "shop": "shop_id",
    "promotion": "promotion_id",
    "category": "category_id",
}
_MARKET_CONTEXT = ("thi truong", "market", "o", "tai", "ben", "negara", "pasar")


@dataclass(frozen=True)
class ExtractedEntity:
    kind: Literal[
        "listing_key", "item_id", "shop_id", "promotion_id", "category_id", "name"
    ]
    value: str
    surface: str
    confidence: Literal["exact", "high", "low"]

    def model_dump(self) -> dict[str, str]:
        return asdict(self)


def extract_countries(text: str, normalized: str) -> tuple[str, ...]:
    found: list[str] = []
    from gladiators.domain.markets import (
        AMBIGUOUS_SURFACES, markets, surface_pattern,
    )

    # Lặp qua MỌI thị trường đã khai. Bản cũ có đúng hai nhánh viết tay, nên
    # một thị trường thứ ba khai trong catalog sẽ KHÔNG BAO GIỜ được nhận ra từ
    # câu hỏi — im lặng, và mọi câu về nó rơi vào "thiếu country".
    for market in markets():
        if not re.search(surface_pattern(market), normalized):
            continue
        if not (AMBIGUOUS_SURFACES & set(_SURFACES_OF(market))):
            found.append(market)
            continue
        if _market_surface_is_meant(text, normalized, market):
            found.append(market)
    return tuple(dict.fromkeys(found))


def _SURFACES_OF(market: str) -> tuple[str, ...]:
    from gladiators.domain.markets import SURFACES_BY_MARKET

    return SURFACES_BY_MARKET.get(market, ())


def _market_surface_is_meant(text: str, normalized: str, market: str) -> bool:
    """Cách gọi trùng một từ thường có thật sự đang nói về thị trường không.

    Luật GIỮ NGUYÊN từ bản cũ — nó là một bẫy có chủ đích, không phải một bản
    sao của khai báo: chữ `"id"` cũng là "id" trong "mã id", "shop id",
    "promotion id".
    """
    from gladiators.domain.markets import AMBIGUOUS_SURFACES

    unambiguous = [s for s in _SURFACES_OF(market) if s not in AMBIGUOUS_SURFACES]
    if unambiguous and re.search(
        r"\b(" + "|".join(re.escape(s) for s in unambiguous) + r")\b", normalized,
    ):
        return True
    for match in re.finditer(
        r"\b(" + "|".join(
            re.escape(s) for s in _SURFACES_OF(market) if s in AMBIGUOUS_SURFACES
        ) + r")\b",
        normalized,
    ):
        token = match.group(1)
        prefix = normalized[max(0, match.start() - 40):match.start()]
        # Đứng ngay sau một danh từ định danh ("mã id", "shop id") ⇒ đây là chữ
        # "id", không phải thị trường.
        if any(
            re.search(rf"\b{re.escape(noun)}\s*$", prefix[-24:])
            for nouns in _ID_NOUNS.values() for noun in nouns
        ):
            continue
        market_context = any(
            re.search(rf"\b{re.escape(ctx)}\s*$", prefix[-16:])
            for ctx in _MARKET_CONTEXT
        )
        legacy_voucher_market = bool(re.search(r"\bvoucher\s*$", prefix[-16:]))
        if (
            re.search(rf"\(\s*{re.escape(token)}\s*\)", text, re.IGNORECASE)
            or market_context
            or legacy_voucher_market
        ):
            return True
    return False


def _value_is_name_shaped(text: str, value: str) -> bool:
    """LUẬT W28-B — CHÍNH GIÁ TRỊ được trích phải có hình dạng tên riêng.

    Kiểm cả câu là quá thô: "Trung bình mỗi sản phẩm tại **Indonesia** … so với
    **Việt Nam**" có token viết hoa, nên một guard mức-câu vẫn cho qua và bộ
    trích vẫn dựng entity ``"tai"`` từ một mệnh đề chung. Điều luật đòi là span
    SINH RA entity phải mang hình dạng đó.

    Dùng chính lattice của W16 nên câu hỏi "token này viết hoa giữa câu chưa?"
    được trả lời ở đúng một chỗ — trước W16 mỗi consumer tự quét lại câu gốc
    bằng một regex riêng, và hai bản của một luật là cách chúng lệch nhau.
    """
    from gladiators.planner.spans import fold, tokenize

    wanted = fold(value).split()
    if not wanted:
        return False
    tokens = tokenize(text)
    words = [token.normalized for token in tokens]
    for start in range(len(words) - len(wanted) + 1):
        if words[start:start + len(wanted)] != wanted:
            continue
        window = tokens[start:start + len(wanted)]
        if any(
            token.name_shaped or (token.numeric and len(token.normalized) >= 8)
            for token in window
        ):
            return True
    return False



# Cụm chỉ LOẠI đối tượng, không phải một phần của tên. Chính các pattern ở trên
# đã coi "cua shop" là RANH GIỚI (nó nằm trong lookahead), nên cắt nó khi nó rơi
# vào đầu span là nhất quán với chính chúng, không phải một luật mới.
_UNIT_PREFIXES = (
    "cua shop", "cua cua hang", "cua thuong hieu", "cua nhan hang",
    "shop", "cua hang", "thuong hieu", "nhan hang", "toko", "cua",
)


def _without_unit_prefix(value: str) -> str:
    """Bỏ cụm chỉ loại đối tượng ở ĐẦU một tên trích được.

    Đo được: câu "Có bao nhiêu sản phẩm của shop Bibica Official Store ở VN
    ngày 21/7" (không ngoặc kép) trích ra ``"cua shop bibica official store"``.
    Plan bind ĐÚNG ``dim.shop_name = "Bibica Official Store"``, nhưng A22 so
    `entity_text` với thứ plan đã bind, thấy hai chuỗi khác nhau, và kết luận
    "entity trong câu hỏi không được bind vào plan" — một lời từ chối nói về
    một khoảng cách do chính bộ trích tạo ra. Cùng câu đó CÓ ngoặc kép thì
    trích đúng ``"Bibica Official Store"`` và trả 92.

    Cắt lặp: "của cửa hàng" đứng trước "shop" trong vài cách nói.
    """
    out = value.strip()
    changed = True
    while changed:
        changed = False
        for prefix in _UNIT_PREFIXES:
            if out.lower().startswith(prefix + " "):
                out = out[len(prefix) + 1:].strip()
                changed = True
                break
    return out or value


def _grown_to_known_value(value: str, normalized: str) -> str:
    """Nới tên đã trích ra thành TÊN ĐẦY ĐỦ nếu nó là phần đầu của một tên có thật.

    Các pattern ở trên dừng span tại những mốc như tên nước, nên một tên riêng
    CÓ CHỨA tên nước bị cắt cụt. Đo được: "Có bao nhiêu sản phẩm của shop Orion
    VN Official Store ở VN ngày 21/7" trích ra ``"orion"``, trong khi plan bind
    ĐÚNG ``dim.shop_name = "Orion VN Official Store"``. A22 đòi giá trị plan
    bind phải nằm trong `entity_text`, mà chuỗi dài không nằm trong chuỗi ngắn —
    nên câu bị từ chối vì một khoảng cách do chính bộ trích tạo ra.

    Nới bằng CHỈ MỤC, không bằng suy đoán: chỉ nhận khi cụm dài hơn thật sự có
    mặt nguyên văn trong câu VÀ là một giá trị có thật. Không có chỉ mục (hoặc
    không biết thị trường) thì giữ nguyên hành vi cũ — thiếu chỉ mục là thiếu
    thông tin để kết luận, không phải bằng chứng rằng tên đó sai.
    """
    if not value:
        return value
    try:
        from gladiators.agent.value_probe import literal_value_spans
    except Exception:                              # noqa: BLE001
        return value
    best = value
    from gladiators.domain.markets import markets as _markets

    for country in _markets():
        for candidate in literal_value_spans(normalized, country):
            if (
                candidate.startswith(value)
                and len(candidate) > len(best)
                and candidate in normalized
            ):
                best = candidate
    return best

def extract_entities(text: str, normalized: str) -> tuple[ExtractedEntity, ...]:
    entities: list[ExtractedEntity] = []
    occupied: list[tuple[int, int]] = []
    listing_numbers: set[str] = set()
    for match in LISTING_KEY.finditer(text):
        entities.append(ExtractedEntity(
            "listing_key", match.group(0).lower(), match.group(0), "exact",
        ))
        occupied.append(match.span())
        listing_numbers.update((match.group(2), match.group(3)))

    # Sentinel promotion IDs may legally be short (notably promotion_id=0), so
    # they cannot use the generic 6–14 digit item/category extractor below.
    for match in re.finditer(
        r"\bpromotion[_\s-]*id\s*(?:=|:)?\s*['\"]?(\d{1,18})['\"]?",
        normalized,
    ):
        entities.append(ExtractedEntity(
            "promotion_id", match.group(1), match.group(0), "exact",
        ))
        occupied.append(match.span(1))

    noun_terms = sorted(
        ((noun, namespace) for namespace, nouns in _ID_NOUNS.items() for noun in nouns),
        key=lambda item: -len(item[0]),
    )
    for number in re.finditer(r"\b\d{6,14}\b", normalized):
        if number.group(0) in listing_numbers:
            continue
        if any(left <= number.start() < right for left, right in occupied):
            continue
        prefix = normalized[max(0, number.start() - 48):number.start()]
        namespace = next(
            (kind for noun, kind in noun_terms
             if re.search(rf"\b{re.escape(noun)}\s*$", prefix)),
            None,
        )
        if namespace:
            entities.append(ExtractedEntity(
                _KIND_FOR_NOUN[namespace], number.group(0), number.group(0), "exact",
            ))
            continue
        if len(number.group(0)) >= 9:
            entities.append(ExtractedEntity(
                "item_id", number.group(0), number.group(0), "high",
            ))

    for match in re.finditer(r'["“”]([^"“”]+)["“”]', text):
        value = match.group(1).strip()
        if value and not value.isdigit() and not LISTING_KEY.fullmatch(value):
            entities.append(ExtractedEntity("name", value, match.group(0), "high"))

    # Conservative unquoted product-name extraction.  It only fires after an
    # explicit product/sales/similarity cue and stops at market/date qualifiers.
    patterns = (
        r"(?:san pham|product|produk)\s+(.+?)(?=\s+(?:o|tai|thi truong|vn|viet nam|indonesia|indo|dang thuoc)\b|$)",
        r"(?:tinh hinh ban|doanh so|sales decline|cek penjualan|san pham tuong tu|similar to)\s+(.+?)(?=\s+(?:o|tai|thi truong|vn|viet nam|indonesia|indo)\b|$)",
        # The scope boundary matters as much here as in the two patterns above.
        # Without it "lượt bán của kẹo dẻo Chupa Chups TẠI SHOP Perfetti Van
        # Melle Vietnam lại giảm" yielded a product name carrying the shop
        # clause, and the resolver then scored on the words the shop and the
        # category share -- handing back a shortlist of a different brand.
        r"(?:luot ban cua)\s+(.+?)(?=\s+(?:o|tai|cua shop|thi truong)\b|\s+(?:giam|tang|thay doi)\b)",
    )
    # LUẬT W28-B (Spec3008 §15.2) — entity chỉ được trích từ một span mà ledger
    # đánh dấu `quoted`, `capitalized` (giữa câu) hoặc `entity_id`.
    #
    # Đo được: "Doanh số thay đổi thế nào?" nhận `A-ENTITY-NOT-FOUND` *"Không
    # tìm thấy listing nào khớp phần mô tả sản phẩm"* — hệ dựng một entity từ
    # một mệnh đề CHUNG rồi không tìm được nó. Không span hình-dạng-tên nào ⇒
    # KHÔNG entity ⇒ câu rơi về clarify thiếu measure/scope mà nó đáng nhận,
    # thay vì một lời từ chối nói về một sản phẩm người dùng chưa hề nêu.
    if not any(item.kind in {"listing_key", "item_id", "name"} for item in entities):
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if not match:
                continue
            value = _grown_to_known_value(
                _without_unit_prefix(match.group(1).strip(" .,:;-")), normalized,
            )
            generic_question = bool(re.match(
                r"^(?:nao|gi|mana|which|apa|di|dengan|yang|nhat|ini|this|"
                r"tertinggi|terendah|co|có)\b",
                value,
            ))
            if (
                value and not generic_question and not re.fullmatch(r"\d+", value)
                and _value_is_name_shaped(text, value)
            ):
                entities.append(ExtractedEntity("name", value, value, "low"))
                break
    if not any(item.kind in {"listing_key", "item_id", "name"} for item in entities):
        candidate = re.sub(
            r"\s+(?:o|tai|thi truong|market)\s+(?:vn|viet nam|vietnam|id|indo|indonesia)\s*$",
            "",
            normalized,
        ).strip()
        question_terms = (
            "nao", "bao nhieu", "cao nhat", "thap nhat", "so sanh",
            "phan tich", "how many", "which", "compare",
        )
        original_candidate = re.sub(
            r"\s+(?:ở|o|tại|tai|thị trường|thi truong|market)\s+(?:vn|việt nam|viet nam|vietnam|id|indo|indonesia)\s*$",
            "",
            text.strip(),
            flags=re.IGNORECASE,
        ).strip(" \"“”")
        original_tokens = original_candidate.split()
        title_like = (
            len(original_tokens) >= 2
            and all(token[:1].isupper() for token in original_tokens[:2])
        )
        if (
            2 <= len(candidate.split()) <= 8
            and title_like
            and not any(term in candidate for term in question_terms)
            and not re.search(r"\d{6,}", candidate)
            and _value_is_name_shaped(text, candidate)
        ):
            entities.append(ExtractedEntity("name", candidate, candidate, "low"))

    unique: dict[tuple[str, str], ExtractedEntity] = {}
    for item in entities:
        unique.setdefault((item.kind, item.value.casefold()), item)
    return tuple(unique.values())
