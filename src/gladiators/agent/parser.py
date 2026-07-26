from __future__ import annotations

import re
import unicodedata

from gladiators.contracts import StructuredRequest
from gladiators.domain.intent_registry import IntentRegistry
from gladiators.planner.semantic_parser import DeterministicSemanticParser
from gladiators.external.router import classify_external_need
from .entity_extract import extract_countries, extract_entities


def normalize_text(value: str) -> str:
    value = value.lower().replace("đ", "d")
    value = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s:/._-]", " ", value)).strip()


def strip_presentation_quotes(value: str) -> str:
    """Remove only a quote pair that wraps the entire user utterance."""
    candidate = value.strip().strip("*").strip()
    pairs = {'"': '"', "“": "”"}
    closing = pairs.get(candidate[:1])
    if closing and candidate.endswith(closing):
        inner = candidate[1:-1].strip().strip("*").strip()
        if inner:
            return inner
    return value


UNSUPPORTED = {
    "profit": ("loi nhuan", "profit", "laba", "margin"),
    "forecast": (
        "du bao", "du doan", "forecast", "ramalan", "seasonality",
        "tuan sau", "thang sau",
    ),
    "sku": ("sku", "bien the", "variasi"),
    "ads": ("quang cao", "ads", "iklan"),
    "inventory": ("ton kho", "inventory", "stok"),
    "conversion": ("chuyen doi", "conversion", "konversi"),
    "image_similarity": ("giong hinh", "giong nhau ve hinh", "image similarity", "kemiripan gambar"),
    "reference": ("ty gia", "exchange rate", "kurs vnd"),
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
        text = strip_presentation_quotes(text)
        n = normalize_text(text)
        quoted = re.findall(r'["“](.*?)["”]', text)
        language = "id" if any(x in n for x in ("produk", "penjualan", "mirip", "promosi")) else "vi"
        route = classify_external_need(text)
        countries = extract_countries(text, n)
        entities = extract_entities(text, n)

        # Explicit safe partial routes from the DR 26/07 contract.  These do
        # not pretend to answer the unsupported causal/forecast component;
        # they select a certified descriptive observation and preserve the
        # rejected component in sub_requests.
        has_conversion = any(term in n for term in ("conversion", "chuyen doi", "chot don"))
        if has_conversion and "voucher" in n:
            return StructuredRequest(
                intent="voucher_coverage",
                country=countries[0] if countries else None,
                countries=countries,
                entities=tuple(item.model_dump() for item in entities),
                language=language,
                slots={
                    "raw_text": text,
                    "sub_requests": (
                        {"sub_id": "sr1", "text": "structured voucher coverage", "capability": None, "answerable": True},
                        {"sub_id": "sr2", "text": "conversion effectiveness", "capability": "conversion", "answerable": False},
                    ),
                    "partial_unsupported": (
                        {"text": "conversion effectiveness", "capability": "conversion"},
                    ),
                },
                route_mode=route.mode,
                external_purpose=route.purpose,
                requested_variables=route.requested_variables,
            )
        if has_conversion and re.search(r"\bgiam gia\s+\d+\b", n):
            return StructuredRequest(
                intent="discount_bucket_observation",
                language=language,
                slots={
                    "raw_text": text,
                    "sub_requests": (
                        {"sub_id": "sr1", "text": "discount bucket observation", "capability": None, "answerable": True},
                        {"sub_id": "sr2", "text": "conversion causality", "capability": "conversion", "answerable": False},
                    ),
                    "partial_unsupported": (
                        {"text": "conversion causality", "capability": "conversion"},
                    ),
                },
                route_mode=route.mode,
                external_purpose=route.purpose,
                requested_variables=route.requested_variables,
            )
        if "du bao" in n and re.search(r"\bthang\s+\d", n):
            return StructuredRequest(
                intent="dataset_coverage",
                country=countries[0] if countries else None,
                countries=countries,
                language=language,
                slots={
                    "raw_text": text,
                    "sub_requests": (
                        {"sub_id": "sr1", "text": "dataset date coverage", "capability": None, "answerable": True},
                        {"sub_id": "sr2", "text": "forecast", "capability": "forecast", "answerable": False},
                    ),
                    "partial_unsupported": (
                        {"text": "forecast", "capability": "forecast"},
                    ),
                },
                route_mode=route.mode,
                external_purpose=route.purpose,
                requested_variables=route.requested_variables,
            )
        if any(term in n for term in ("du doan", "tuan sau", "thang sau")):
            return StructuredRequest(
                intent="unsupported:forecast",
                language=language,
                slots={"raw_text": text},
                route_mode=route.mode,
                external_purpose=route.purpose,
                requested_variables=route.requested_variables,
            )
        if (
            "voucher_discount" in n
            and "price" in n
            and any(term in n for term in (" tru ", "subtract", "minus"))
        ):
            return StructuredRequest(
                intent="unsupported:price_reconstruction",
                language=language,
                slots={"raw_text": text},
                route_mode=route.mode,
                external_purpose=route.purpose,
                requested_variables=route.requested_variables,
            )

        clauses = tuple(
            normalized for part in re.split(
                r"[;,?.]+|\s+(?:và|va|dan|juga)\s+",
                text,
                flags=re.IGNORECASE,
            )
            if (normalized := normalize_text(part))
        )
        clause_capabilities = tuple(
            (
                clause,
                next(
                    (capability for capability, words in UNSUPPORTED.items()
                     if any(word in clause for word in words)),
                    None,
                ),
            )
            for clause in clauses
        )
        supported_clauses = tuple(
            clause for clause, capability in clause_capabilities
            if capability is None and len(clause.split()) >= 3
        )
        unsupported_clauses = tuple(
            (clause, capability) for clause, capability in clause_capabilities
            if capability is not None
        )
        if unsupported_clauses and supported_clauses:
            supported_text = " ".join(supported_clauses)
            parsed = self.parse(supported_text, registry)
            full_countries = extract_countries(text, n)
            full_entities = extract_entities(text, n)
            sub_requests = tuple(
                {
                    "sub_id": f"sr{index}",
                    "text": clause,
                    "capability": capability,
                    "answerable": capability is None,
                }
                for index, (clause, capability) in enumerate(clause_capabilities, 1)
            )
            slots = {
                **parsed.slots,
                "raw_text": text,
                "sub_requests": sub_requests,
                "partial_unsupported": tuple(
                    {"text": clause, "capability": capability}
                    for clause, capability in unsupported_clauses
                ),
            }
            primary_entity = next(
                (item for item in full_entities
                 if item.kind in {"listing_key", "item_id", "name"}),
                None,
            )
            return parsed.model_copy(update={
                "entity_text": primary_entity.value if primary_entity else parsed.entity_text,
                "country": full_countries[0] if full_countries else parsed.country,
                "countries": full_countries or parsed.countries,
                "entities": tuple(item.model_dump() for item in full_entities) or parsed.entities,
                "slots": slots,
                "route_mode": route.mode,
                "external_purpose": route.purpose,
                "requested_variables": route.requested_variables,
            })
        for capability, words in UNSUPPORTED.items():
            if any(w in n for w in words):
                return StructuredRequest(
                    intent=f"unsupported:{capability}", language=language, slots={"raw_text": text},
                    route_mode=route.mode, external_purpose=route.purpose,
                    requested_variables=route.requested_variables,
                )
        if any(x in n for x in (
            "tuong tu", "tuong duong", "giong", "similar", "equivalent",
            "mirip", "serupa",
        )):
            intent = "similar_product"
        elif any(x in n for x in ("shop", "cua hang", "toko")) and any(
            x in n for x in ("voucher", "khuyen mai", "promosi")
        ) and any(x in n for x in ("hieu qua", "tot nhat", "chien luoc", "terbaik", "best")):
            # V2 §2.8: "shop nào có chiến lược voucher hiệu quả nhất" — L4 descriptive
            # ranking theo voucher_profile_rank_v1, KHÔNG phải câu promo hai-nhóm.
            intent = "voucher_profile_rank"
        elif any(x in n for x in ("voucher", "khuyen mai", "promotion", "promosi", "promo")):
            intent = "promotion_effectiveness"
        elif any(x in n for x in ("gia thay doi", "bien dong gia", "price change", "perubahan harga")):
            intent = "analytical_query"
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
        elif quoted or any(x in n for x in ("doanh so", "sales decline", "bien dong ban", "tinh hinh ban", "cek penjualan", "analisis penjualan")) or (
            "luot ban" in n and any(x in n for x in ("giam", "tang", "thay doi"))
        ):
            intent = "sales_decline"
        else:
            intent = "open_analytical"
        if route.mode == "external_only":
            intent = "external_context"
        country = countries[0] if countries else None
        primary_entity = next(
            (item for item in entities if item.kind in {"listing_key", "item_id", "name"}),
            None,
        )
        entity = primary_entity.value if primary_entity else quoted[0].strip() if quoted else None
        slots = {"raw_text": text}
        qualifiers: list[str] = []
        if any(item.kind == "promotion_id" for item in entities):
            qualifiers.append("promotion_id_filter")
        if (
            any(term in n for term in (
                "khong promo", "khong khuyen mai", "no promo", "tanpa promo",
            ))
            or re.search(
                r"\bkhong co\b.{0,48}\b(?:promo|khuyen mai|giam gia truc tiep)\b",
                n,
            )
        ):
            qualifiers.append("no_promo_segment")
        if any(term in n for term in ("doanh thu", "revenue", "pendapatan")):
            qualifiers.append("revenue_measure")
        if any(term in n for term in ("trung binh", "mean", "average", "rata rata")):
            qualifiers.append("mean_requested")
        if any(term in n for term in ("discount bucket", "nhom giam gia", "muc giam", "bucket")):
            qualifiers.append("discount_bucket")
        if qualifiers:
            slots["qualifiers"] = tuple(dict.fromkeys(qualifiers))
        if route.purpose:
            slots["external_purpose"] = route.purpose
        if intent == "analytical_query":
            if any(x in n for x in ("gia thay doi", "bien dong gia", "price change", "perubahan harga")):
                slots["analytical_kind"] = "price_change_by_date"
            elif any(x in n for x in ("doanh thu", "revenue", "pendapatan")):
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
        if not intent.startswith("unsupported:") and intent != "external_context":
            analytical = DeterministicSemanticParser().parse(text, language, country).model_dump(mode="json")
        return StructuredRequest(
            intent=intent, entity_text=entity, country=country, countries=countries,
            entities=tuple(item.model_dump() for item in entities), language=language,
            slots=slots, analytical=analytical, route_mode=route.mode,
            external_purpose=route.purpose, requested_variables=route.requested_variables,
        )
