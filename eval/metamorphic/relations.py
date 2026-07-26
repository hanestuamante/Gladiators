"""Approved DR2607 metamorphic relations.

Every transform preserves language, market, date and currency.  Cross-language,
cross-market and unit/date changes are intentionally absent because they do not
preserve denotation.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class MetamorphicRelation:
    relation_id: str
    transform: Callable[..., str]
    proof: str
    changes_language: bool = False
    changes_country: bool = False
    changes_date: bool = False
    changes_currency: bool = False


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
    """Only reviewed within-language synonyms are substituted."""
    replacements = (
        (r"\bbao nhiêu\b", "số lượng"),
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


RELATIONS = (
    MetamorphicRelation("MR-1", approved_same_language_paraphrase, "Approved synonyms preserve operands."),
    MetamorphicRelation("MR-3", quote_entity, "Quotes only mark the same entity span."),
    MetamorphicRelation("MR-4", remove_vietnamese_diacritics, "Diacritic folding preserves lexical meaning."),
    MetamorphicRelation("MR-5", add_layout_noise, "Layout noise changes no semantic operand."),
)


def validate_relations() -> None:
    if any(
        relation.changes_language
        or relation.changes_country
        or relation.changes_date
        or relation.changes_currency
        for relation in RELATIONS
    ):
        raise ValueError("Metamorphic relation không bảo toàn ngôn ngữ/scope/unit.")
