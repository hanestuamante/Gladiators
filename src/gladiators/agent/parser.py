from __future__ import annotations

import re
import unicodedata

from gladiators.contracts import StructuredRequest
from gladiators.domain.intent_registry import IntentRegistry
from gladiators.planner.semantic_parser import DeterministicSemanticParser


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
    "reference": ("ty gia", "exchange rate", "kurs vnd", "lich 7.7", "calendar context"),
    "external": ("gia doi thu", "competitor price", "market price", "harga pesaing"),
    "orders": ("don hang", "order-level", "order level", "pesanan"),
    "category_type": ("category type", "category_type", "ma loai danh muc"),
    "price_reconstruction": (
        "tai tao gia cuoi", "gia goc tru voucher", "original price minus voucher",
        "rekonstruksi harga akhir",
    ),
}


class MultilingualIntentParser:
    def parse(self, text: str, registry: IntentRegistry) -> StructuredRequest:
        n = normalize_text(text)
        quoted = re.findall(r'["“](.*?)["”]', text)
        language = "id" if any(x in n for x in ("produk", "penjualan", "mirip", "promosi")) else "vi"
        for capability, words in UNSUPPORTED.items():
            if any(w in n for w in words):
                return StructuredRequest(intent=f"unsupported:{capability}", language=language, slots={"raw_text": text})
        if any(x in n for x in ("tuong tu", "giong", "similar", "mirip", "serupa")):
            intent = "similar_product"
        elif any(x in n for x in ("voucher", "khuyen mai", "promotion", "promosi", "promo")):
            intent = "promotion_effectiveness"
        elif any(x in n for x in ("doanh thu", "revenue", "pendapatan")) and any(
            x in n for x in ("cao nhat", "lon nhat", "highest", "tertinggi")
        ) and any(x in n for x in ("ngay", "date", "tanggal")):
            intent = "analytical_query"
        elif any(x in n for x in ("bao nhieu", "how many", "berapa")) and any(
            x in n for x in ("listing", "san pham", "product", "produk")
        ):
            intent = "analytical_query"
        elif any(x in n for x in ("cao nhat", "dat nhat", "highest", "tertinggi")) and any(
            x in n for x in ("gia", "price", "harga")
        ):
            intent = "analytical_query"
        elif any(x in n for x in ("cao nhat", "nhieu nhat", "highest", "tertinggi")) and any(
            x in n for x in ("luot ban", "monthly sold", "penjualan")
        ):
            intent = "analytical_query"
        elif any(x in n for x in ("shop", "cua hang", "toko")) and any(
            x in n for x in ("nhieu listing nhat", "nhieu san pham nhat", "most listings", "listing terbanyak")
        ):
            intent = "analytical_query"
        elif quoted or any(x in n for x in ("doanh so", "sales decline", "bien dong ban", "tinh hinh ban", "cek penjualan", "analisis penjualan")):
            intent = "sales_decline"
        else:
            intent = "open_analytical"
        country = "id" if re.search(r"\b(id|indonesia)\b", n) else "vn" if re.search(r"\b(vn|viet nam|vietnam)\b", n) else None
        entity = quoted[0].strip() if quoted else None
        slots = {"raw_text": text}
        if intent == "analytical_query":
            if any(x in n for x in ("doanh thu", "revenue", "pendapatan")):
                slots["analytical_kind"] = "highest_revenue_day"
            elif any(x in n for x in ("bao nhieu", "how many", "berapa")):
                slots["analytical_kind"] = "listing_count"
            elif any(x in n for x in ("gia", "price", "harga")):
                slots["analytical_kind"] = "highest_price_listing"
            elif any(x in n for x in ("shop", "cua hang", "toko")):
                slots["analytical_kind"] = "top_shop_by_listing_count"
            else:
                slots["analytical_kind"] = "highest_monthly_sold_listing"
        analytical = None
        if intent == "open_analytical":
            analytical = DeterministicSemanticParser().parse(text, language, country).model_dump(mode="json")
        return StructuredRequest(
            intent=intent, entity_text=entity, country=country, language=language,
            slots=slots, analytical=analytical,
        )
