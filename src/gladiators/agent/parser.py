from __future__ import annotations

import re
import unicodedata

from gladiators.contracts import StructuredRequest
from gladiators.domain.column_semantics import classify_column_observation
from gladiators.domain.intent_registry import IntentRegistry
from gladiators.domain.relation_prose import STRUCTURE_CUES
from gladiators.planner.semantic_parser import (
    DeterministicSemanticParser,
    extract_date_range,
)
from gladiators.external.router import classify_external_need
from .entity_extract import extract_countries, extract_entities


def normalize_text(value: str) -> str:
    value = value.lower().replace("đ", "d")
    value = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s:/._-]", " ", value)).strip()


def normalize_date_range(values) -> list[str]:
    """Canonicalise a date range coming from *any* parser into ``[start, end]``.

    The deterministic parser already emits ISO dates, but the LLM parser fills
    ``StructuredRequest.date_range`` with whatever the model echoed -- e.g.
    ``["01/07"]``.  Left raw, that is neither ISO nor length-2, so every
    downstream date check silently no-ops and A22-ALIGN-DATE protects only the
    deterministic path.  Found by the DeepSeek smoke test.
    """
    return extract_date_range(normalize_text(" ".join(str(v) for v in values or ())))


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
    # W8.4: external nhận theo CẤU TRÚC ở router (_is_external_competitor_price)
    # — vòng UNSUPPORTED không giữ danh sách phrase thứ hai cho cùng khái niệm.
    "external": (),
    "orders": ("don hang", "order-level", "order level", "pesanan"),
    "category_type": ("category type", "category_type", "ma loai danh muc"),
    "price_reconstruction": (
        "tai tao gia cuoi", "gia goc tru voucher", "original price minus voucher",
        "rekonstruksi harga akhir",
    ),
}



def _schema_entities(normalized: str) -> tuple[str, ...]:
    """Tên entity (theo registry quan hệ) mà câu hỏi nhắc tới — WP-A7.2.

    Bind qua ``AliasIndex`` với ``kinds={"entity"}`` để dùng đúng một nguồn từ
    vựng, không dựng bảng từ khoá thứ hai.
    """
    from gladiators.domain.alias_index import default_alias_index
    from gladiators.domain.relation_prose import ENTITY_BY_REF

    found: list[str] = []
    for match in default_alias_index().find_in(normalized, kinds=frozenset({"entity"})):
        for ref in match.refs:
            name = ENTITY_BY_REF.get(ref)
            if name and name not in found:
                found.append(name)
    return tuple(found[:2])



# A13-R4: bộ tách mệnh đề DETERMINISTIC dùng chung. Trước WP-A13 nó nằm kẹt bên
# trong ``parse`` nên chỉ chạy được cho đúng một mục đích: tách phần vượt năng
# lực dataset. Nhánh trả lời từng phần cần chính bộ tách này — tách bằng LLM ở
# đây là để một lời gọi không xác định quyết định câu nào được trả lời.
_CLAUSE_SPLIT = re.compile(r"[;,?.]+|\s+(?:và|va|dan|juga)\s+", re.IGNORECASE)

# Dưới ba từ thì mệnh đề không đủ để mang một câu hỏi — nó là mảnh vụn của phép
# tách, và gate chạy trên mảnh vụn sẽ từ chối vì lý do sai.
MIN_CLAUSE_WORDS = 3


def split_clauses(text: str) -> tuple[str, ...]:
    return tuple(
        normalized for part in _CLAUSE_SPLIT.split(text)
        if (normalized := normalize_text(part))
    )


def substantive_clauses(text: str) -> tuple[str, ...]:
    """Mệnh đề đủ dài để đứng riêng thành một câu hỏi, giữ NGUYÊN VĂN.

    Trả bản đã chuẩn hoá ở đây là hỏng: chuẩn hoá bỏ dấu và bỏ viết hoa, mà viết
    hoa chính là tín hiệu vòng P dùng để phân biệt một TÊN RIÊNG với một từ mô
    tả. Cho ăn bản đã chuẩn hoá, "brand Khongtontai" thành "brand khongtontai"
    và mệnh đề lẽ ra bị chặn lại được cho qua.
    """
    return tuple(
        part.strip() for part in _CLAUSE_SPLIT.split(text)
        if (normalized := normalize_text(part))
        and len(normalized.split()) >= MIN_CLAUSE_WORDS
    )


# Dấu tự hỏi. Một mệnh đề KHÔNG mang dấu nào trong đây là một tiền đề, không phải
# một câu hỏi riêng — và tách nó ra thành "một phần chưa trả lời được" là bịa ra
# một câu hỏi người dùng chưa từng đặt.
_INTERROGATIVE = (
    "bao nhieu", "la gi", "the nao", "nhu the nao", "co bao", "may",
    "berapa", "apa", "bagaimana",
    "how many", "how much", "what", "which",
)


def question_clauses(text: str) -> tuple[str, ...]:
    """Mệnh đề tự nó đã là một câu hỏi, giữ nguyên văn.

    Điều kiện này hẹp hơn ``substantive_clauses`` và cố ý như vậy. Câu
    "Với đà giảm doanh số như 3 ngày qua của sản phẩm X, dự đoán tuần sau giảm
    thêm bao nhiêu?" tách ra hai mệnh đề đủ dài, nhưng mệnh đề đầu là **tiền đề**
    của mệnh đề sau. Coi nó là một câu hỏi riêng làm một câu phải bị từ chối
    (dự báo) biến thành một câu trả lời một phần — đúng thứ ``dr2607`` khoá lại.
    """
    return tuple(
        clause for clause in substantive_clauses(text)
        if any(marker in normalize_text(clause) for marker in _INTERROGATIVE)
    )


class MultilingualIntentParser:
    def parse(self, text: str, registry: IntentRegistry) -> StructuredRequest:
        text = strip_presentation_quotes(text)
        n = normalize_text(text)
        quoted = re.findall(r'["“](.*?)["”]', text)
        # Câu có nêu một ĐỊNH DANH listing không — quét CẢ CÂU, không quét
        # riêng phần trong ngoặc: `strip_presentation_quotes` chạy trước dòng
        # này và bỏ ngoặc ở một số dạng câu, nên `quoted` đôi khi rỗng dù câu
        # có nêu mã. Mã listing tự nó đã không mơ hồ; nó không cần ngoặc.
        names_a_listing_key = bool(
            re.search(r"(?:vn|id):\d{6,12}:\d{6,14}", text, re.IGNORECASE),
        )
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
        # Câu hỏi về CHÍNH BỘ DỮ LIỆU, không phải về hàng hoá trong đó.
        #
        # Macro `dataset_coverage` đã trả sẵn ngày đầu / ngày cuối / số đợt thu,
        # nhưng cửa vào duy nhất của nó là nhánh "dự báo tháng N" ngay dưới —
        # tức hệ chỉ nói ra lịch dữ liệu khi nó đang TỪ CHỐI một câu hỏi khác.
        # Hỏi thẳng thì rơi vào đường analytical và nhận "Thiếu country để khóa
        # scope VN hoặc ID", một đòi hỏi SAI: lịch đợt thu giống hệt nhau ở cả
        # hai thị trường (đo được: 20 ngày 01–21/07 cho cả vn lẫn id), nên
        # country không đổi câu trả lời. Hệ từ chối một thứ nó biết chắc chắn,
        # và đó thường là câu đầu tiên người ta hỏi khi tìm hiểu dữ liệu.
        #
        # Điều kiện HAI VẾ, và vế thứ nhất là thứ giữ cho luật này hẹp: câu phải
        # gọi tên chính bộ dữ liệu, VÀ phải hỏi về bề rộng thời gian. "Có bao
        # nhiêu shop trong dữ liệu ở VN?" gọi tên dữ liệu nhưng hỏi về shop —
        # nó đi đường analytical như cũ và vẫn trả 10.
        names_the_dataset = any(
            term in n for term in
            ("du lieu", "dataset", "snapshot", "dot thu", "bo so lieu")
        )
        asks_time_extent = any(
            term in n for term in (
                "bao nhieu ngay", "bao nhieu snapshot", "bao nhieu dot",
                "nhung ngay nao", "ngay nao den ngay nao", "tu ngay nao",
                "khoang thoi gian", "pham vi thoi gian", "bao phu",
                "gom nhung ngay", "co nhung ngay", "berapa hari",
                "how many days",
            )
        )
        if names_the_dataset and asks_time_extent:
            return StructuredRequest(
                intent="dataset_coverage",
                country=countries[0] if countries else None,
                countries=countries,
                language=language,
                slots={
                    "raw_text": text,
                    "sub_requests": (
                        {"sub_id": "sr1", "text": "dataset date coverage",
                         "capability": None, "answerable": True},
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

        clauses = split_clauses(text)
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
        # W8.2: đường gọi DUY NHẤT của registry ngữ nghĩa quan sát, TRƯỚC vòng
        # UNSUPPORTED. unknown ⇒ None ⇒ đường từ chối hiện hành giữ nguyên;
        # not_collected ⇒ A-DATA-ABSENT với lý do nêu ĐÚNG (cột không được thu
        # thập, không phải "dataset không có khái niệm này"); observed để
        # catalog/qualifier phát hành ref và parser bind theo đường chuẩn.
        observation = classify_column_observation(n)
        if observation is not None and observation.semantics == "not_collected":
            return StructuredRequest(
                intent="unsupported:column_not_collected", language=language,
                slots={"raw_text": text,
                       "column_observation": {
                           "column": observation.column,
                           "semantics": observation.semantics,
                           "caveat_key": observation.caveat_key,
                       }},
                route_mode=route.mode, external_purpose=route.purpose,
                requested_variables=route.requested_variables,
            )
        from gladiators.external.router import _is_external_competitor_price

        if _is_external_competitor_price(n):
            return StructuredRequest(
                intent="unsupported:external", language=language, slots={"raw_text": text},
                route_mode=route.mode, external_purpose=route.purpose,
                requested_variables=route.requested_variables,
            )
        for capability, words in UNSUPPORTED.items():
            if any(w in n for w in words):
                return StructuredRequest(
                    intent=f"unsupported:{capability}", language=language, slots={"raw_text": text},
                    route_mode=route.mode, external_purpose=route.purpose,
                    requested_variables=route.requested_variables,
                )
        # WP-A7: câu hỏi về CẤU TRÚC dữ liệu, không phải về số liệu. Đặt trước
        # nhánh analytical vì "shop và listing liên quan thế nào" chứa cả tên
        # entity lẫn từ khoá của các nhánh dưới, và nó không hỏi một con số nào.
        # Không bind được entity nào ⇒ KHÔNG vào intent này (rơi về luồng cũ).
        schema_entities = _schema_entities(n)
        if any(cue in n for cue in STRUCTURE_CUES) and schema_entities:
            intent = "schema_relation_explain"
        elif any(x in n for x in (
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
        elif any(x in n for x in ("voucher", "khuyen mai", "promotion", "promosi", "promo")) and (
            # "giá trước KHUYẾN MÃI" là tên một CỘT GIÁ, không phải một câu hỏi
            # về khuyến mãi. Cụm "khuyen mai" nằm trong chính tên measure, và
            # nhánh này đọc nó thành ý định promo rồi đẩy câu vào macro hai
            # nhóm — `mode=certified_macro`, rồi `A-NO-EVIDENCE`, trong khi
            # synthesize dựng plan cho nó không một lời phàn nàn.
            #
            # Cùng lớp với `("gia tri", "gia")` ở `_COMPOUND_TRAPS`: một cụm dài
            # có nghĩa riêng, và cụm ngắn bên trong nó không được nói thay.
            "gia truoc khuyen mai" not in n
            and "gia truoc giam" not in n
        ) and not ("voucher" in n and re.search(
            # Chỉ chuyển hướng khi câu ĐẾM MỘT ĐƠN VỊ VÀ nói về VOUCHER — đếm
            # theo khuyến mãi/promotion (tc30) vẫn thuộc macro như trước W8.3.
            # "voucher" nằm trong danh sách này vì "bao nhiêu VOUCHER" là một câu
            # ĐẾM, y hệt "bao nhiêu listing" — chú thích W8.3 ngay dưới đã nói
            # đúng nguyên tắc, chỉ thiếu chính đơn vị mà cả nhánh nói về. Hệ quả
            # đo được: "Shop X có bao nhiêu voucher ngày 03/07" rơi vào macro
            # promo hai-nhóm rồi trả `A-NO-EVIDENCE` — một lời từ chối nói SAI
            # trở ngại, vì mơ hồ CÓ được ghi đúng ở tầng dưới ("voucher có cấu
            # trúc" so với "nhãn voucher") mà không lớp nào dùng tới nó.
            r"(?:bao nhieu|so luong|berapa|how many)\s+"
            r"(?:listing|san pham|mat hang|hang hoa|shop|item|produk|voucher|ma voucher|ma giam gia)",
            n,
        )):
            # W8.3: câu ĐẾM có từ voucher không phải câu promo hai-nhóm — nó đi
            # đường analytical, nơi qualifier tường minh bind được predicate và
            # cụm "có voucher" trần fail-closed bằng ambiguity (hai khái niệm:
            # structured 0/474 trên ID so với nhãn hiển thị 210/474).
            intent = "promotion_effectiveness"
        elif any(x in n for x in ("gia thay doi", "bien dong gia", "price change", "perubahan harga")):
            intent = "analytical_query"
        elif any(x in n for x in ("doanh thu", "revenue", "pendapatan")) and any(
            x in n for x in ("cao nhat", "lon nhat", "highest", "tertinggi")
        ) and any(x in n for x in ("ngay", "date", "tanggal")):
            intent = "analytical_query"
        elif any(x in n for x in ("bao nhieu", "how many", "berapa")) and any(
            # CHỈ thêm đơn vị mà lỗi quan sát được đòi hỏi. Bản đầu của tôi
            # thêm cả `shop`/`thuong hieu`/`brand`, và nó đổi định tuyến của
            # "Có bao nhiêu shop ở Việt Nam?" — một câu vốn đi `open_analytical`
            # và trả lời đúng — nên hai test hợp đồng của intent arbiter đỏ.
            # Sửa một lỗi bằng cách đổi đường của những câu KHÔNG hỏng là mở
            # rộng phạm vi, không phải sửa lỗi.
            x in n for x in ("listing", "san pham", "mat hang", "hang hoa",
                             "product", "produk", "voucher")
        ):
            # Danh sách đơn vị đếm phải ĐỦ, vì nhánh `quoted` phía dưới bắt mọi
            # câu có ngoặc kép và biến nó thành `sales_decline`. Đo được:
            # *Shop "Richy - Chi nhánh Miền Nam" có bao nhiêu voucher ngày
            # 03/07* rơi vào sales_decline rồi trả `A-ENTITY-NOT-FOUND` *"không
            # tìm thấy LISTING nào khớp"* — trong khi tầng ngữ nghĩa đã bind
            # đúng `dim.shop_name` và `expected_entity_types` đã trả `('shop',)`.
            # Lời từ chối nói về một loại thực thể mà không lớp nào đang tìm.
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
        elif (
            # NGOẶC KÉP KHÔNG PHẢI MỘT Ý ĐỊNH. Nhánh này từng nhận `quoted` trần,
            # nên MỌI câu có tên trong ngoặc đều thành phân tích biến động doanh
            # số — kể cả khi nó hỏi chuyện khác hẳn. Đo được, cùng một tên shop
            # trong ngoặc:
            #
            #   "Liệt kê sản phẩm của shop X"     → sales_decline → A-ENTITY-NOT-FOUND
            #   "Giá trung bình của shop X"       → sales_decline → A-ENTITY-NOT-FOUND
            #   "Khoảng tứ phân vị giá shop X"    → sales_decline → A-ENTITY-NOT-FOUND
            #
            # Và lời từ chối nói *"không tìm thấy LISTING nào khớp"* trong khi
            # `expected_entity_types` đã trả `('shop',)` và `dim.shop_name` đã
            # bind đúng — ba câu khác nhau, một nguyên nhân, và nguyên nhân đó
            # nằm ở tầng định tuyến chứ không ở tầng phân giải.
            #
            # Thứ ĐƯỢC giữ: một **listing key** trong ngoặc. Nó định danh đúng
            # một listing, tức đúng grain mà macro biến động doanh số làm việc
            # trên đó — `Kiểm tra lượt bán "id:1112776376:46456356622"` vẫn phải
            # vào đây. Một TÊN trong ngoặc thì không: nó có thể là shop, brand,
            # hay sản phẩm, và đoán bừa là chọn hộ người dùng một grain.
            (names_a_listing_key and "luot ban" in n)
            or any(x in n for x in ("doanh so", "sales decline", "bien dong ban",
                                 "tinh hinh ban", "cek penjualan", "analisis penjualan"))
            or ("luot ban" in n and any(x in n for x in ("giam", "tang", "thay doi")))
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
        if intent == "schema_relation_explain":
            slots["relation_entities"] = list(schema_entities)
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
        date_range = extract_date_range(n)
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
            date_range=date_range, slots=slots, analytical=analytical,
            route_mode=route.mode,
            external_purpose=route.purpose, requested_variables=route.requested_variables,
        )
