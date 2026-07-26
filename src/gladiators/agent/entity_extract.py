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
    if re.search(r"\b(viet nam|vietnam|vn)\b", normalized):
        found.append("vn")
    for match in re.finditer(r"\b(indonesia|indo|id)\b", normalized):
        token = match.group(1)
        if token == "id":
            prefix = normalized[max(0, match.start() - 40):match.start()]
            nearby = prefix[-24:]
            if any(
                re.search(rf"\b{re.escape(noun)}\s*$", nearby)
                for nouns in _ID_NOUNS.values() for noun in nouns
            ):
                continue
            market_context = any(
                re.search(rf"\b{re.escape(ctx)}\s*$", prefix[-16:])
                for ctx in _MARKET_CONTEXT
            )
            legacy_voucher_market = bool(re.search(r"\bvoucher\s*$", prefix[-16:]))
            if not (
                re.search(r"\(\s*id\s*\)", text, re.IGNORECASE)
                or market_context
                or legacy_voucher_market
            ):
                continue
        found.append("id")
        break
    return tuple(dict.fromkeys(found))


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
        r"(?:luot ban cua)\s+(.+?)\s+(?:giam|tang|thay doi)\b",
    )
    if not any(item.kind in {"listing_key", "item_id", "name"} for item in entities):
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if not match:
                continue
            value = match.group(1).strip(" .,:;-")
            generic_question = bool(re.match(
                r"^(?:nao|gi|mana|which|apa|di|dengan|yang|nhat|ini|this|"
                r"tertinggi|terendah|co|có)\b",
                value,
            ))
            if value and not generic_question and not re.fullmatch(r"\d+", value):
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
        ):
            entities.append(ExtractedEntity("name", candidate, candidate, "low"))

    unique: dict[tuple[str, str], ExtractedEntity] = {}
    for item in entities:
        unique.setdefault((item.kind, item.value.casefold()), item)
    return tuple(unique.values())
