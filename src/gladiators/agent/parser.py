from __future__ import annotations

import re
import unicodedata

from gladiators.contracts import StructuredRequest
from gladiators.domain.intent_registry import IntentRegistry


def normalize_text(value: str) -> str:
    value = value.lower().replace("đ", "d")
    value = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s:/._-]", " ", value)).strip()


UNSUPPORTED = {
    "profit": ("loi nhuan", "profit", "laba", "margin"),
    "forecast": ("du bao", "forecast", "ramalan", "seasonality"),
    "sku": ("sku", "bien the", "variasi"),
    "ads": ("quang cao", "ads", "iklan"),
    "inventory": ("ton kho", "inventory", "stok"),
    "conversion": ("chuyen doi", "conversion", "konversi"),
    "image_similarity": ("giong hinh", "giong nhau ve hinh", "image similarity", "kemiripan gambar"),
}


class MultilingualIntentParser:
    def parse(self, text: str, registry: IntentRegistry) -> StructuredRequest:
        n = normalize_text(text)
        language = "id" if any(x in n for x in ("produk", "penjualan", "mirip", "promosi")) else "vi"
        for capability, words in UNSUPPORTED.items():
            if any(w in n for w in words):
                return StructuredRequest(intent=f"unsupported:{capability}", language=language, slots={"raw_text": text})
        if any(x in n for x in ("tuong tu", "giong", "similar", "mirip", "serupa")):
            intent = "similar_product"
        elif any(x in n for x in ("voucher", "khuyen mai", "promotion", "promosi", "promo")):
            intent = "promotion_effectiveness"
        else:
            intent = "sales_decline"
        country = "id" if re.search(r"\b(id|indonesia)\b", n) else "vn" if re.search(r"\b(vn|viet nam|vietnam)\b", n) else None
        quoted = re.findall(r'["“](.*?)["”]', text)
        entity = quoted[0].strip() if quoted else None
        return StructuredRequest(intent=intent, entity_text=entity, country=country, language=language, slots={"raw_text": text})
