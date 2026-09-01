"""P7 AnalyticalRequest contract, catalog slicing và deterministic fallback."""
from __future__ import annotations

from .predicate_ops import ExecutablePredicateOp, canonicalize_predicate_op
from .query_ir import Aggregation

import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from rapidfuzz import fuzz

from gladiators.domain.alias_index import (
    PREFERRED_REF_BY_SURFACE,
    compound_shadowed,
    default_alias_index,
)
from gladiators.domain.catalog import CATALOG, CatalogObject, COUNT_METRIC_BY_SURFACE_REF
from gladiators.domain.qualifiers import match as qualifier_match

from .frames import frame_hits, resolve_frames, singularize_unmatched
from .term_resolver import RESOLVABLE_KINDS, resolve_terms as resolve_llm_terms

# Wordings that make the noun beside them the thing being counted rather than a
# key to group by.
_COUNTING_CUES = ("nhieu nhat", "terbanyak", "most", "bao nhieu", "nhieu san pham", "berapa")

_DATE_ISO = re.compile(r"2026-07-0[1-3]")
_DATE_DAY_MONTH = re.compile(r"(?<![0-9])0?([123])\s*/\s*0?7(?![0-9])")


def _literal_token_indices(builder, country: str | None = None) -> frozenset[int]:
    """Token thuộc một cụm phải ĐỌC NGUYÊN VĂN — trong ngoặc, hoặc là tên có thật.

    Hai nguồn, cùng một nghĩa. Dấu ngoặc kép là người dùng NÓI ra rằng đây là
    một tên; một cụm khớp nguyên văn giá trị trong chỉ mục thì là một tên dù
    người dùng có nói hay không, và chỉ mục là sự thật về dữ liệu chứ không phải
    một phỏng đoán về câu chữ.

    Vì sao vế thứ hai cần có: câu "cửa hàng Mars Snacking VN ở VN ngày 21/7"
    (không ngoặc) có hai lần "vn", và country binder claim lần ĐẦU — lần nằm
    trong chính tên shop. Tên mất một token, không còn là cụm dư liền mạch, nên
    `dim.shop_name` không bind được và plan chạy KHÔNG có bộ lọc shop. Cùng câu
    đó CÓ ngoặc thì đúng, vì luật tránh trước đây chỉ áp cho vùng trong ngoặc.

    Đọc `raw_question` của chính builder thay vì nhận từ ngoài: hai nguồn cho
    cùng một sự thật là hai chỗ để chúng lệch nhau, và cái lệch ở đây im lặng —
    nó chỉ hiện ra thành một bộ lọc biến mất.
    """
    from .spans import fold

    raw = getattr(builder, "raw_question", "") or ""
    literals = [fold(inner) for inner in _QUOTED_RAW.findall(raw)]
    if country:
        # Import trễ: `agent/` phụ thuộc `planner/`, nên import ở đầu file tạo
        # vòng qua analytics/tools.py.
        from gladiators.agent.value_probe import literal_value_spans

        literals.extend(literal_value_spans(fold(raw), country))
    inside: set[int] = set()
    for literal in literals:
        want = literal.split()
        if not want:
            continue
        size = len(want)
        for i in range(len(builder.tokens) - size + 1):
            window = builder.tokens[i:i + size]
            if [tok.normalized for tok in window] == want:
                inside.update(range(i, i + size))
    return frozenset(inside)


def _ledger_of(
    text: str,
    *,
    country: str | None,
    dates: tuple[str, ...],
    surfaces: tuple[tuple[str, str | None, str], ...],
) -> "BindingLedger":
    """Dựng ledger bằng cách REPLAY claim của từng binder, theo thứ tự W16 §3.3.

    Thứ tự là một QUYẾT ĐỊNH, không phải mặc định thuật toán: value binding chạy
    sau alias là điều làm việc xoá ``MIN_VALUE_LENGTH`` an toàn — ``gia`` trong
    ``gia tri`` đã bị alias tiêu thụ và không còn là span dư.
    """
    from .spans import LedgerBuilder, fold

    builder = LedgerBuilder(text)
    # Token nằm TRONG ngoặc kép. Đo được: câu 'shop "Mars Snacking VN" ở VN
    # ngày 21/7' có hai lần "vn", và country binder lấy lần ĐẦU — tức lần nằm
    # trong chính tên shop. Tên shop mất một token, không còn là một cụm dư liền
    # mạch, nên value binder không bind được `dim.shop_name` và plan chạy KHÔNG
    # có bộ lọc shop. Ba trong bốn ca hỏng còn lại của lượt quét 20 shop đều
    # đúng hình dạng đó: "Mars Snacking VN", "Orion VN Official Store",
    # "Perfetti Van Melle Vietnam".
    quoted = _literal_token_indices(builder, country)
    # 2. entity_id — chuỗi ≥8 chữ số
    for token in builder.tokens:
        if token.numeric and len(token.normalized) >= 8:
            builder.claim(token.index, token.index + 1, "entity_id", payload=token.normalized)
    # 3. date — token số thuộc một cụm ngày đã phân giải
    if dates:
        for token in builder.tokens:
            if token.numeric and len(token.normalized) <= 4:
                builder.claim(token.index, token.index + 1, "date", payload=dates)
    # 4. country
    if country:
        # HAI LƯỢT, và thứ tự là điểm chính. Lượt một chỉ nhận vị trí NGOÀI
        # ngoặc; chỉ khi cả lượt một không tìm được gì thì mới cho phép lùi vào
        # trong ngoặc.
        #
        # Fallback theo từng surface là sai, và sai im lặng: câu
        # 'shop "Perfetti Van Melle Vietnam" ở VN' có `vietnam` khớp trong
        # ngoặc và `vn` khớp ngoài ngoặc. Xét từng surface một thì `vietnam`
        # lùi vào trong ngoặc TRƯỚC khi `vn` ngoài ngoặc kịp được thử — tên shop
        # mất một token và bộ lọc shop biến mất, dù đã có luật tránh.
        claimed = False
        for surface in _COUNTRY_SURFACES.get(country, ()):  # noqa: SIM118
            pos = builder.find_free(fold(surface), avoid=quoted)
            if pos and not any(index in quoted for index in range(*pos)):
                builder.claim(*pos, "country", ref="dim.country", payload=country)
                claimed = True
        if not claimed:
            for surface in _COUNTRY_SURFACES.get(country, ()):  # noqa: SIM118
                pos = builder.find_free(fold(surface))
                if pos:
                    builder.claim(*pos, "country", ref="dim.country",
                                  payload=country)
                    break
    # 5-7. alias / qualifier / value — theo đúng thứ tự caller truyền vào
    for producer, ref, surface in surfaces:
        pos = builder.find_free(fold(surface))
        if pos:
            builder.claim(*pos, producer, ref=ref, payload=surface)
    # 9. number — số còn lại
    for token in builder.tokens:
        if token.numeric:
            builder.claim(token.index, token.index + 1, "number", payload=token.normalized)
    return builder.build()


# Cách gọi một thị trường trong ba ngôn ngữ. Country binder của parser suy country
# từ ngoài (workflow truyền vào), nên ledger phải tự tìm span tương ứng để token
# tên nước không bị chấm là ``unknown_concept``.
_COUNTRY_SURFACES: dict[str, tuple[str, ...]] = {
    "vn": ("việt nam", "viet nam", "vietnam", "vn"),
    "id": ("indonesia", "indo", "id"),
}


def extract_date_range(normalized: str) -> list[str]:
    """Return ``[start, end]`` for the snapshot dates named in a normalised text.

    The dataset holds only 2026-07-01..03, so ``2026-07-01`` and the colloquial
    ``01/07`` denote the same snapshot.  A single named date yields ``[d, d]``:
    asking for 01/07 and being handed the 03/07 snapshot is a wrong answer, not
    a defensible default.  Lives here rather than in ``agent.parser`` so both the
    intent parser and the plan synthesizer read dates the same way.
    """
    # Đọc ngày bằng BỘ ĐỌC CỦA LỊCH, không bằng một regex thứ hai.
    #
    # Bản cũ ở đây là `_DATE_ISO = r"2026-07-0[1-3]"` cộng một regex chỉ khớp
    # `1/7`, `2/7`, `3/7`, và nó ghép chuỗi `f"2026-07-0{day}"` — cứng tháng 7,
    # cứng một chữ số. Nó ĐÚNG cho bộ đóng băng 3 ngày mà docstring này được
    # viết trên đó, và trên bộ 20 ngày đang phục vụ thì nó KHÔNG NHÌN THẤY bất
    # kỳ ngày nào sau 03/07.
    #
    # Hậu quả không nằm ở chỗ mất một ngày. `StructuredRequest.date_range` là
    # thứ A22 dùng làm "phạm vi người dùng đã hỏi", nên câu "từ ngày 1/7 đến
    # ngày 5/7" co lại thành `[01/07, 01/07]` và lời từ chối sinh ra nói
    # *"Evidence quan sát ngày 2026-07-05 ngoài phạm vi 2026-07-01→2026-07-01
    # đã hỏi"* — một câu nói về một phạm vi người dùng chưa bao giờ nêu.
    #
    # Bộ kiểm không bắt được vì `tests/conftest.py` ghim vào chính bộ 3 ngày,
    # nơi hai bộ đọc trùng nhau. Đây đúng là lớp lỗi "hai bản của một luật là
    # cách chúng lệch nhau" — nên cách sửa là XOÁ bản thứ hai, không vá nó.
    from gladiators.domain.calendar import default_calendar

    from .dates import parse_date_expressions

    request = parse_date_expressions(normalized, default_calendar())
    seen = sorted(dict.fromkeys(
        request.dates + request.missing_snapshot + request.out_of_window,
    ))
    return [seen[0], seen[-1]] if seen else []


def normalize(value: str) -> str:
    value = value.lower().replace("đ", "d")
    value = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s:/._-]", " ", value)).strip()


class SemanticBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    surface_text: str
    ref: str | None = None
    unresolved: bool = False
    reason: Literal["catalog_gap", "metric_ungoverned", "data_absent", "unknown"] | None = None


class EntityBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    surface_text: str
    entity_type: Literal["listing", "shop", "brand", "category", "shelf"]
    resolved_key: str | None = None
    candidates: tuple[str, ...] = ()
    status: Literal["resolved", "ambiguous", "unresolved"] = "unresolved"


class SemanticAmbiguity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["alias_collision"]
    surface: str
    candidate_refs: tuple[str, ...]


class AnalyticalPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_ref: str
    # W11.1: dùng CHUẨN chung với IR và catalog. ``le/ge`` từ payload cũ được
    # canonicalize ở biên; ``between``/``isnull`` không còn là op của model —
    # between phải tách gte+lte trước khi dựng, isnull đi lối A19-OP.
    op: ExecutablePredicateOp
    value_binding: Any

    @field_validator("op", mode="before")
    @classmethod
    def _canonicalize(cls, value: str) -> str:
        return canonicalize_predicate_op(str(value))


class AnalyticalTimeScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dates: tuple[str, ...]
    mode: Literal["single_snapshot", "transition", "all_with_caveat"]


class AnalyticalRanking(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_by: str
    direction: Literal["asc", "desc"] = "desc"
    top_k: int = Field(default=5, ge=1, le=10)


class AnalyticalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    normalized_question: str
    language: Literal["vi", "id", "unknown"]
    resolved_entities: tuple[EntityBinding, ...] = ()
    requested_measures: tuple[SemanticBinding, ...] = ()
    requested_dimensions: tuple[SemanticBinding, ...] = ()
    filters: tuple[AnalyticalPredicate, ...] = ()
    time_scope: AnalyticalTimeScope
    grouping: tuple[str, ...] = ()
    comparison: dict[str, Any] | None = None
    ranking: AnalyticalRanking | None = None
    requested_grain: Literal["listing", "listing_snapshot", "shop", "shelf", "category", "country", "group"]
    analytical_operators: tuple[str, ...] = ()
    answerability_class: Literal["C1", "C2", "C3", "C4"] = "C1"
    ambiguities: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    requested_output_shape: Literal["scalar", "table", "ranking", "comparison"]
    unsupported_operators: tuple[str, ...] = ()
    # W5.1: phép tổng hợp mà câu hỏi nêu TƯỜNG MINH. Dùng chính kiểu Aggregation
    # của IR thay vì chép một Literal thứ hai — hai danh sách là hai chỗ để
    # chúng lệch nhau. Additive, mặc định None ⇒ fixture cũ không hỏng.
    requested_aggregation: Aggregation | None = None
    # W8.3: alias collision không có quyết định ưu tiên — có kiểu, và mọi
    # collision đều fail-closed qua classify_a19, không chỉ voucher. Field
    # `ambiguities` chuỗi cũ giữ đọc một release cho tương thích payload.
    semantic_ambiguities: tuple[SemanticAmbiguity, ...] = ()
    # W16: bản model hoá được của BindingLedger. Mặc định rỗng ⇒ payload cũ vẫn
    # validate. `unbound_spans` giữ phẳng vì RequestDigest và trace đọc nó nhiều
    # nhất — đây là ĐƯỜNG để A22 và gate thấy được phần dư, thứ mà trước W16
    # không lớp nào phía sau trả lời được ("một ràng buộc có mặt trong câu hỏi
    # đã được biểu diễn hay đã bị bỏ rơi?").
    # W20: năm ô của DateRequest, phẳng hoá để gate và A22 đọc được.
    date_request: dict[str, Any] = Field(default_factory=dict)
    binding_ledger: dict[str, Any] = Field(default_factory=dict)
    unbound_spans: tuple[tuple[str, str], ...] = ()
    # W32: số đo của vòng ánh xạ LLM. Rỗng mang HAI nghĩa khác nhau và chúng
    # phải phân biệt được: không có proposer (`llm_terms_called=False`) khác hẳn
    # có proposer nhưng model trả null (`called=True, accepted=0`). Thiếu khoá
    # này thì "đã đo" và "đã chạy" trông giống nhau — đúng lỗi WP-A11 đã mắc,
    # nơi một nhánh chết vẫn trông như một nhánh hoà (CLAUDE.md §5.1).
    llm_terms: dict[str, Any] = Field(default_factory=dict)



# W5.1 — cụm nêu TƯỜNG MINH một phép tổng hợp. Hai cue khác nhau cùng xuất hiện
# ⇒ ghi ambiguity và KHÔNG chọn theo thứ tự bảng: chọn theo thứ tự bảng là để
# thứ tự khai báo trả lời hộ một câu hỏi mơ hồ.
_AGGREGATION_CUES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("trung vi", "median"), "median"),
    (("trung binh", "binh quan", "rata rata", "average", "mean"), "mean"),
    (("tong cong", "cong lai", "tong ", "total", "sum"), "sum"),
    # CHỆCH KHỎI SPEC CÓ CHỦ ĐÍCH: bảng §6.2 liệt cả `max`/`min` trần. Đo trên
    # bộ đề thật thì `"max"` trần khớp "iPhone 15 Pro Max" trong dr2607:tc35 và
    # biến một câu phân tích doanh số thành một câu hỏi cực trị — đúng lớp lỗi
    # "$7.7 billion → anchor chiến dịch 7.7" ở CLAUDE.md §3.1. Cụm tiếng Việt và
    # `maximum`/`minimum` không có hình thái đó nên được giữ.
    (("cao nhat", "lon nhat", "toi da", "maximum"), "max"),
    (("thap nhat", "nho nhat", "toi thieu", "minimum"), "min"),
)

# Cực trị chỉ là một CON SỐ khi câu hỏi hỏi một con số. "Price original cao nhất
# tại VN" hôm nay trả về các DÒNG đã xếp hạng và 58 plan bị khoá phụ thuộc điều
# đó; "Giá cao nhất tại Indonesia LÀ BAO NHIÊU" mới là câu hỏi vô hướng. Thiếu
# điều kiện này, năm entry baseline đổi hình mà không câu hỏi nào đổi nghĩa.
_SCALAR_INTERROGATIVE = ("bao nhieu", "berapa", "la bao nhieu", "how much")
# "cao nhất/thấp nhất" chỉ là scalar aggregate khi câu KHÔNG hỏi một chủ thể
# xếp hạng: "listing nào có giá cao nhất" hỏi một DÒNG, còn "giá cao nhất là
# bao nhiêu" hỏi một CON SỐ. Không dùng `ranking is not None` làm dấu hiệu —
# parser suy ranking từ chính cụm so sánh, nên mọi câu có "cao nhất" đều có
# ranking và điều kiện sẽ luôn đúng, tức luật không bao giờ bắn.
_EXTREMUM_AGGREGATIONS = frozenset({"max", "min"})
_RANKING_SUBJECT = re.compile(
    r"\b(listing|san pham|mat hang|hang hoa|shop|cua hang|thuong hieu|brand|"
    r"danh muc|toko|produk|merek|kategori)\b[^?]{0,24}?\b(nao|mana|dengan)\b",
)


def _names_a_ranking_subject(normalized: str) -> bool:
    return bool(_RANKING_SUBJECT.search(normalized))


def _detect_requested_aggregation(
    normalized: str, has_ranking_subject: bool, asks_for_a_number: bool,
) -> tuple[str | None, str | None]:
    """``(aggregation, ambiguity)`` — phép tổng hợp câu hỏi NÊU RA, nếu có."""
    hits: list[str] = []
    for terms, aggregation in _AGGREGATION_CUES:
        if any(term in normalized for term in terms) and aggregation not in hits:
            hits.append(aggregation)
    if has_ranking_subject or not asks_for_a_number:
        hits = [item for item in hits if item not in _EXTREMUM_AGGREGATIONS]
    if not hits:
        return None, None
    if len(hits) > 1:
        return None, (
            "Câu hỏi nêu nhiều phép tổng hợp khác nhau: "
            + ", ".join(hits) + "; không chọn hộ một trong số đó."
        )
    return hits[0], None


# W11.1 — một measure đứng cạnh một từ so sánh là ĐIỀU KIỆN, không phải thứ được
# đo. "bao nhiêu listing giảm giá TRÊN 50%" đo số listing; "giảm giá trên 50%"
# là bộ lọc. Để nó ở cả hai chỗ làm request khai hai measure cho một câu hỏi một
# measure, và synthesizer từ chối vì đúng lý do sai (measure_count_not_one).
# Cụm dài xếp trước: "hon" là đuôi của "lon hon"/"cao hon".
_COMPARISON: tuple[tuple[str, str], ...] = (
    ("lon hon", "gt"), ("cao hon", "gt"), ("nho hon", "lt"), ("thap hon", "lt"),
    ("it nhat", "gte"), ("toi da", "lte"), ("di atas", "gt"), ("di bawah", "lt"),
    ("tren", "gt"), ("duoi", "lt"), ("tu", "gte"), ("hon", "gt"),
)
_PERCENT_MARKERS = ("%", "phan tram", "phần trăm", "persen")

# Đơn vị TIỀN TỆ nêu tường minh trong câu, và bậc số đi kèm. Chú thích ở
# ``_comparison_predicates`` từ chối "trên 50" cạnh một measure tiền tệ vì câu
# đó không nói 50 GÌ — lý do đúng, nhưng nó chặn luôn cả câu ĐÃ NÓI: "giá trên
# 5 triệu đồng" nêu cả bậc ("triệu") lẫn đơn vị ("đồng"). Chỉ nhận khi câu mang
# CẢ HAI; thiếu một trong hai thì vẫn bỏ qua, vì đoán bậc là đoán một câu hỏi
# khác (5 triệu, 5 nghìn và 5 đồng là ba ngưỡng cách nhau sáu bậc).
_CURRENCY_MARKERS: dict[str, tuple[str, ...]] = {
    "vn": ("dong", "đồng", "vnd", "vnđ"),
    "id": ("rupiah", "idr", "rp"),
}
_MAGNITUDE_WORDS: tuple[tuple[str, int], ...] = (
    ("ty", 1_000_000_000), ("tỷ", 1_000_000_000), ("tỉ", 1_000_000_000),
    ("trieu", 1_000_000), ("triệu", 1_000_000), ("juta", 1_000_000),
    ("nghin", 1_000), ("nghìn", 1_000), ("ngan", 1_000), ("ngàn", 1_000),
    ("ribu", 1_000),
)


def _currency_threshold(literal: str, raw_question: str, country: str | None) -> float | None:
    """Ngưỡng tiền tệ mà câu NÊU RÕ, hoặc ``None``.

    Đọc từ câu GỐC: normalizer bỏ dấu, nên "đồng" và "dong" phải cùng tra được.
    Cửa sổ sau con số cố ý ngắn — đơn vị tiền phải đứng CẠNH số, không phải ở
    đâu đó trong câu.
    """
    lowered = raw_question.lower()
    anchor = lowered.find(literal.split(".")[0])
    if anchor < 0:
        return None
    window = lowered[anchor: anchor + len(literal) + 24]
    markers = _CURRENCY_MARKERS.get(country or "", ())
    named_currency = bool(markers) and any(marker in window for marker in markers)
    for word, scale in _MAGNITUDE_WORDS:
        if word in window:
            return float(literal) * scale
    # KHÔNG có từ chỉ độ lớn. Guard cũ trả None ở đây với lý do đúng: "trên 50"
    # trần cạnh một measure tiền tệ là một câu hỏi khác — 50 gì, VND hay nghìn
    # hay phần trăm? Giữ nguyên tinh thần đó, chỉ mở đúng hai chỗ mà câu hỏi
    # KHÔNG còn mơ hồ nữa:
    #
    #   "giá trên 500000 đồng"  — người dùng đã nói rõ đơn vị. Không còn gì để
    #                             đoán, và bắt họ viết "500 nghìn" mới hiểu là
    #                             bắt họ nói lại điều đã nói.
    #   "giá trên 500000"       — số đủ lớn thì mọi cách đọc khác đều vô nghĩa:
    #                             phần trăm không tới 1000, và đọc nó như "500000
    #                             nghìn" là tự nhân thêm một chữ số người dùng
    #                             không viết.
    #
    # Ngưỡng 1000 giữ đúng ca mà comment cũ nêu: "trên 50" vẫn bị bỏ qua.
    #
    # Đo được trước khi mở: "Có bao nhiêu listing giá trên 500000 ở VN ngày
    # 21/7" ra `A22-ALIGN-MEASURE` — parser bind `measure.price` rồi KHÔNG sinh
    # predicate nào, nên plan mất chính điều kiện của câu hỏi. Đáp án thật: 94.
    value = float(literal)
    if named_currency or value >= 1000:
        return value
    return None


def _comparison_predicates(
    measures: list, normalized: str, raw_question: str, country: str | None = None,
) -> tuple[list, list]:
    """``(measures còn lại, predicate mới)`` — cả BỐN điều kiện đều bắt buộc.

    1. ≥2 measure đã bind, đúng MỘT có ``counts_unit`` — câu một measure không
       có gì để lọc;
    2. measure không-đếm đứng liền trước một cụm so sánh và một số — "giảm giá"
       trần không được biến thành bộ lọc ``> None``;
    3. toán tử suy ra nằm trong ``allowed_filters`` — catalog cấm thì không lách;
    4. đơn vị của số khớp ``unit`` của measure (đọc từ câu GỐC vì normalizer bỏ
       ``%``) — "trên 50" với measure đơn vị tiền tệ là một câu hỏi KHÁC.

    Không đạt bất kỳ điều kiện nào ⇒ giữ nguyên hành vi hôm nay. Guard MỘT
    CHIỀU, như ``_has_unbound_qualifier``.
    """
    bound = [item for item in measures if item.ref]
    counting = [item for item in bound if CATALOG[item.ref].counts_unit]
    conditions = [item for item in bound if not CATALOG[item.ref].counts_unit]
    if len(bound) < 2 or len(counting) != 1 or not conditions:
        return measures, []

    kept, predicates = list(measures), []
    comparison_alternatives = "|".join(
        re.escape(term) for term, _op in _COMPARISON
    )
    for item in conditions:
        obj = CATALOG[item.ref]
        pattern = re.compile(
            re.escape(normalize(item.surface_text))
            + r"\s+(" + comparison_alternatives + r")\s+(\d+(?:[.,]\d+)?)\b",
        )
        found = pattern.search(normalized)
        if not found:
            continue
        op = next(op for term, op in _COMPARISON if term == found.group(1))
        if op not in obj.allowed_filters:
            continue
        literal = found.group(2).replace(",", ".")
        # Điều kiện 4 — đơn vị của SỐ phải khớp đơn vị của MEASURE, đọc từ câu
        # GỐC vì normalizer đã bỏ "%". Cố ý HẸP: chỉ measure đơn vị percent với
        # một số mang dấu %/phần trăm được áp; "trên 50" trần cạnh một measure
        # tiền tệ là một câu hỏi KHÁC (50 gì? VND? nghìn? phần trăm?) và guard
        # một chiều thì bỏ qua đúng hơn đoán.
        if obj.unit == "local_currency":
            scaled = _currency_threshold(literal, raw_question, country)
            if scaled is None:
                continue
            predicates.append(AnalyticalPredicate(
                field_ref=item.ref, op=op,
                value_binding=int(scaled) if float(scaled).is_integer() else scaled,
            ))
            kept = [entry for entry in kept if entry is not item]
            continue
        if obj.unit != "percent":
            continue
        raw_folded = raw_question.lower()
        anchor_pos = raw_folded.find(literal.split(".")[0])
        if anchor_pos < 0 or not any(
            marker in raw_folded[anchor_pos: anchor_pos + len(literal) + 16]
            for marker in _PERCENT_MARKERS
        ):
            continue
        number = float(literal)
        predicates.append(AnalyticalPredicate(
            field_ref=item.ref, op=op,
            value_binding=int(number) if number.is_integer() else number,
        ))
        kept = [entry for entry in kept if entry is not item]
    return kept, predicates


# W4.1 — khung "Số lượng X là bao nhiêu?" và "Có bao nhiêu X?" hỏi cùng một
# thứ. Bộ alias khớp trên cụm DÍNH LIỀN ("bao nhieu shop"), nên khung thứ hai
# làm cụm đó tách ra và câu mất measure. Viết lại NGUYÊN KHUNG và chép `rest`
# nguyên văn: định ngữ ("da xac minh", "chinh hang") nằm trong `rest` nên nó
# không thể rơi mất — đó là điều kiện để phép viết lại này không đổi câu hỏi.
_COUNT_FRAME_VI = re.compile(
    r"^(?P<lead>.*?)\bso luong\s+(?P<rest>.+?)\s+la bao nhieu\b.*$"
)
_COUNT_FRAME_ID = re.compile(
    r"^(?P<lead>.*?)\bjumlah\s+(?P<rest>.+?)\s+(?:adalah\s+)?berapa\b.*$"
)


def _normalise_count_frame(normalized: str) -> tuple[str, bool]:
    """``(câu đã viết lại, có viết lại không)`` — cờ đếm số lần nhánh bắn."""
    for frame in (_COUNT_FRAME_VI, _COUNT_FRAME_ID):
        found = frame.match(normalized)
        if found:
            rewritten = " ".join(
                f"{found.group('lead')} co bao nhieu {found.group('rest')}".split()
            )
            return rewritten, True
    return normalized, False


def _human_label(ref: str) -> str:
    """Nhãn người đọc cho một ref — alias tiếng Việt đầu tiên nếu có
    (INV-NO-INTERNAL-VOCABULARY: không lộ ref nội bộ hay tên tự sinh)."""
    obj = CATALOG.get(ref)
    if obj is None or not obj.aliases:
        return ref.split(".")[-1].replace("_", " ")
    vietnamese = next(
        (alias for alias in obj.aliases if any(ord(ch) > 127 for ch in alias)),
        None,
    )
    return vietnamese or obj.aliases[0]


_EXPLICIT_TOP_N = re.compile(r"\btop\s*(\d{1,2})\b")
# Vietnamese/Indonesian plural markers that ask for a list rather than one row.
# Deliberately narrow: "cac san pham" as a *grouping domain* ("trung binh cua
# cac san pham") must stay scalar, so only markers that introduce the ranked
# subject count. Anything unmatched falls back to top_k=1, the old behaviour.
_PLURAL_MARKERS = ("nhung ", "liet ke ", "danh sach ", "cac san pham nao", "produk apa saja")
DEFAULT_PLURAL_TOP_K = 5


def _requested_top_k(normalized: str) -> int:
    """How many rows the question asks for; 1 unless it says otherwise."""
    explicit = _EXPLICIT_TOP_N.search(normalized)
    if explicit:
        return max(1, min(int(explicit.group(1)), 10))  # AnalyticalRanking caps at 10
    if any(marker in f" {normalized} " for marker in _PLURAL_MARKERS):
        return DEFAULT_PLURAL_TOP_K
    return 1


class CatalogSlicer:
    def __init__(self, catalog: dict[str, CatalogObject] | None = None):
        self.catalog = catalog or CATALOG

    def select(self, query: str, limit: int = 30) -> tuple[CatalogObject, ...]:
        needle = normalize(query)
        scored: list[tuple[float, str, CatalogObject]] = []
        for obj in self.catalog.values():
            haystacks = (obj.ref.replace("_", " "),) + tuple(normalize(alias) for alias in obj.aliases)
            score = max(fuzz.WRatio(needle, text) for text in haystacks if text)
            if any(text and text in needle for text in haystacks):
                score += 25
            scored.append((score, obj.ref, obj))
        scored.sort(key=lambda item: (-item[0], item[1]))
        required_refs = ("dim.country", "dim.date")
        # Reserve room for the scope refs before filling, instead of evicting
        # afterwards: the old code popped from the end, so when *both* were
        # missing the second eviction removed the first one just appended and
        # the slice silently shipped without a country scope.
        missing = [ref for ref in required_refs if ref not in {item[1] for item in scored[:limit]}]
        room = max(limit - len(missing), 0)
        selected = [item[2] for item in scored[:room]]
        selected.extend(self.catalog[ref] for ref in missing)
        return tuple(selected)


# Proposer dùng chung, ĐĂNG KÝ tường minh. `None` là mặc định và là cấu hình
# đang phát hành: đường tất định trả lời phần lớn câu ở 56 ms, còn tầng LLM đo
# được ~4/6 trên bộ dò tay và KHÔNG ổn định (2/6 khi lặp cùng một input), nên nó
# chưa đủ tư cách làm mặc định. Xem ghi chú đo lường ở `term_resolver`.
_TERM_PROPOSER = None


def register_term_proposer(proposer) -> None:
    """Bật/tắt tầng W32. Gọi với ``None`` để tắt."""
    global _TERM_PROPOSER
    _TERM_PROPOSER = proposer


# Vùng trong ngoặc kép, lấy từ câu GỐC. `normalize` xoá mọi ký tự ngoài
# `[a-z0-9\s:/._-]`, nên dấu ngoặc KHÔNG còn trong chuỗi đã normalize — tìm nó
# ở đó là tìm một thứ đã bị xoá.
_QUOTED_RAW = re.compile(r'["\u201c]([^"\u201d]+)["\u201d]')


def _without_quoted_regions(
    normalized: str, raw: str, bound_values: tuple[str, ...] = (),
) -> str:
    """``normalized`` trừ đi phần trong ngoặc kép VÀ mọi literal đã bind.

    Một cụm chỉ được CLAIM MỘT LẦN. Nếu nó đã thành giá trị của một chiều
    (``dim.shop_name = "Bánh Kẹo Hải Hà - Chính hãng"``) thì nó không còn là
    chữ tự do để một binder khác đọc tiếp.

    Đo được, và cả hai dạng đều ra một số 0 GIẢ:

      shop "Bánh Kẹo Hải Hà - Chính hãng"  (trong ngoặc)
      shop Bánh Kẹo Hải Hà - Chính hãng    (không ngoặc)

    Cụm "chính hãng" nằm trong CHÍNH TÊN SHOP, và qualifier binder đọc nó thành
    ``dim.shop_official = True``. Plan thành "tên X **và** là official shop",
    lọc ra 0 dòng, rồi trả `allow` kèm "không có dòng nào thoả điều kiện" —
    trong khi shop đó có 12 listing hôm ấy. Vá riêng ngoặc kép chỉ đóng một nửa;
    người dùng gõ tên trần thì nửa kia vẫn mở.
    """
    out = normalized
    for inner in _QUOTED_RAW.findall(raw):
        folded = normalize(inner)
        if folded:
            out = out.replace(folded, " ")
    for literal in bound_values:
        folded = normalize(str(literal))
        if len(folded) >= 4:          # literal quá ngắn thì trừ đi là quá tay
            out = out.replace(folded, " ")
    return out


def _contiguous_residuals(ledger) -> tuple[str, ...]:
    """Cụm token dư LIỀN KỀ, dài trước — đầu vào cho vòng phân giải W32.

    Chỉ trả span CỰC ĐẠI — cùng luật W18 đã dùng cho cross-ref. Bản đầu gửi kèm
    cả token lẻ ("cho LLM thêm lựa chọn"), và nó phản tác dụng, đo được:

        gửi ["nhãn hàng"]                   → {"nhãn hàng": "entity.brand"}   ✓
        gửi ["nhãn hàng", "nhãn", "hàng"]   → cả ba đều null                  ✗

    Liệt kê các mảnh của một cụm bên cạnh chính cụm đó là ngầm hỏi "cụm này có
    nên tách ra không", và một model thận trọng sẽ trả null cho tất cả thay vì
    chọn bừa. Nó làm đúng; câu hỏi mới là câu hỏi tồi.
    """
    items = sorted(
        (item for item in ledger.significant() if item.kind in RESOLVABLE_KINDS),
        key=lambda item: item.span.start,
    )
    groups: list[list] = []
    for item in items:
        if groups and item.span.start == groups[-1][-1].span.end:
            groups[-1].append(item)
        else:
            groups.append([item])
    # Gửi chữ GỐC, không gửi bản đã bỏ dấu. Đo được: hỏi ``"nhan hang"`` thì
    # model trả `null` — đúng một cách thận trọng, vì cụm đó không có dấu thì
    # thật sự mơ hồ trong tiếng Việt. Ledger giữ cả hai dạng, nên không có lý do
    # nào để vứt dạng đọc được đi.
    # Cắt HƯ TỪ ở hai đầu. Ledger phân loại theo `is_function_word`, và bảng đó
    # không phủ hết — "vào", "của", "trong" rơi vào `unknown_concept` rồi bị gộp
    # vào cụm liền kề. Đo được: hỏi LLM `"nhãn hàng vào"` thay vì `"nhãn hàng"`,
    # và model trả null cho một cụm không phải tiếng Việt tự nhiên. Nó làm đúng;
    # câu hỏi mới là câu hỏi tồi.
    trim = {
        "vao", "cua", "trong", "tai", "o", "cho", "voi", "va", "la", "co",
        "theo", "tu", "den", "ngay", "thang", "nam", "so", "muc", "bao",
        "nhieu", "duoc", "bi", "ra", "len", "xuong",
    }
    out: list[str] = []
    for group in groups:
        items = list(group)
        while items and normalize(items[0].span.raw) in trim:
            items.pop(0)
        while items and normalize(items[-1].span.raw) in trim:
            items.pop()
        if items:
            out.append(" ".join(item.span.raw for item in items))
    return tuple(dict.fromkeys(out))


class DeterministicSemanticParser:
    """Fallback P7 bảo thủ; không tạo physical column hoặc join."""

    def __init__(self, term_proposer=None) -> None:
        self.alias_index = default_alias_index()
        # Mặc định None ⇒ hành vi TỪNG BIT như trước. Tầng LLM là thứ caller phải
        # chọn dùng, không phải thứ bật sẵn cho mọi lời gọi (cùng luật A3-R3).
        #
        # Lùi về proposer ĐÃ ĐĂNG KÝ khi caller không truyền: parser được dựng
        # mới ở mỗi lượt gọi tại hai chỗ khác nhau, nên không có đường nào để
        # truyền xuống mà không sửa cả hai. Biến module là chỗ duy nhất cả hai
        # cùng đọc — cùng khuôn với `DEFAULT_DATA_DIR`.
        self.term_proposer = term_proposer if term_proposer is not None else _TERM_PROPOSER

    @staticmethod
    def _contains_phrase(normalized: str, phrase: str) -> bool:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", normalized))

    def _link(self, normalized: str, kinds: set[str]) -> list[SemanticBinding]:
        """Lớp mỏng trên ``AliasIndex`` — WP-A4.1.

        Trước đây hàm này giữ bộ khớp alias THỨ HAI, cộng hai bảng seed
        hard-code làm bộ thứ ba. Ba bộ song song nghĩa là một bản vá ở bộ này
        không áp cho bộ kia: bug ``"giá trị"`` → ``measure.price`` từng được vá
        riêng ở đây trong khi vẫn sống nguyên trong ``AliasIndex``.

        Luật khớp dài nhất và ``compound_shadowed`` đã nằm sẵn trong
        ``AliasIndex.find_in``; chỗ này chỉ còn việc phân giải surface trỏ nhiều
        ref bằng ``PREFERRED_REF_BY_SURFACE``.
        """
        accepted: list[tuple[str, str]] = []
        seen_refs: set[str] = set()
        for match in self.alias_index.find_in(normalized, kinds=frozenset(kinds)):
            ref = match.refs[0]
            if match.ambiguous:
                preferred = PREFERRED_REF_BY_SURFACE.get(match.surface)
                # Surface mơ hồ mà không có ưu tiên: chọn một ref theo thứ tự
                # index là trả lời một câu hỏi khác trong im lặng — và NUỐT nó
                # (continue trần cũ) cũng vậy: "có voucher" là hai khái niệm
                # (structured 0/474 trên ID so với nhãn 210/474), câu phải
                # fail-closed bằng ambiguity chứ không lặng lẽ mất binding.
                if preferred is None or preferred not in match.refs:
                    self._pending_ambiguities.append(SemanticAmbiguity(
                        kind="alias_collision", surface=match.surface,
                        candidate_refs=tuple(match.refs),
                    ))
                    continue
                ref = preferred
            if ref in seen_refs or CATALOG[ref].kind not in kinds:
                continue
            accepted.append((match.surface, ref))
            seen_refs.add(ref)
        return [SemanticBinding(surface_text=alias, ref=ref) for alias, ref in accepted]

    def parse(self, text: str, language: str, country: str | None) -> AnalyticalRequest:
        normalized = normalize(text)
        # W4.1: viết lại khung đếm TRƯỚC _link — alias khớp cụm dính liền.
        normalized, count_frame_normalised = _normalise_count_frame(normalized)
        # W17-R1: số nhiều là fallback của alias. Chạy TRƯỚC _link và chỉ đổi
        # token mà (a) chưa khớp alias nào và (b) dạng số ít CÓ khớp.
        normalized, plural_folded = singularize_unmatched(
            normalized,
            language if language in ("vi", "id") else "en",
            self.alias_index.surfaces(),
        )
        self._pending_ambiguities: list[SemanticAmbiguity] = []
        # Dấu ngoặc kép là người dùng nói "đọc nguyên văn". Bộ ghép alias phải
        # KHÔNG nhìn vào trong đó, nếu không chính tên riêng bị ăn mất từng
        # mảnh và cái còn lại không đủ để lọc.
        #
        # Đo được trên 20 shop thật của bản đang phục vụ, câu "có bao nhiêu sản
        # phẩm của shop <tên> ở <thị trường> ngày 21/7" — 13/20 đúng, 0 sai,
        # 7 từ chối, và cả 7 tên đều chứa một từ của catalog:
        #   "lavojoy Official Shop"      "Official"→dim.shop_official, "Shop"→entity.shop
        #   "Mars Snacking VN"           "VN"→country
        #   "Perfetti Van Melle Vietnam" "Vietnam"→country
        #   "Orion VN Official Store"    "VN"→country, phần tên còn lại rơi hết
        #   "Mooi Pure Glow Official Shop", "Prettywell Official Shop", "Nestlé Chính hãng"
        # 13 ca chạy được đều là "Official STORE" — một từ catalog không có.
        # Tức tỷ lệ đúng đang phụ thuộc vào việc shop tự đặt tên trùng từ vựng
        # của hệ hay không, và đó không phải một tính chất của câu hỏi.
        #
        # `_without_quoted_regions` đã vá đúng lớp lỗi này cho qualifier binder
        # (xem docstring của nó, ca "Bánh Kẹo Hải Hà - Chính hãng" ra SỐ 0 GIẢ)
        # nhưng bộ ghép alias chính thì chưa. Dùng lại chính hàm đó thay vì viết
        # luật thứ hai — hai bản của một luật là cách chúng lệch nhau.
        # Ngoài vùng trong ngoặc, trừ luôn những TÊN CÓ THẬT xuất hiện nguyên
        # văn: người dùng thường không gõ ngoặc, và câu con do LLM bẻ ra thì
        # gần như không bao giờ. `literal_value_spans` chỉ nhận cụm ≥2 token và
        # chỉ khi cụm đó là một giá trị có thật trong chỉ mục — nên đây là một
        # sự thật về DỮ LIỆU, không phải một phỏng đoán về câu chữ.
        from gladiators.agent.value_probe import literal_value_spans

        linkable = _without_quoted_regions(
            normalized, text, literal_value_spans(normalized, country),
        )
        measures = self._link(linkable, {"measure", "derived_metric"})
        dimension_text = linkable
        for measure in measures:
            dimension_text = re.sub(
                rf"(?<![a-z0-9]){re.escape(measure.surface_text)}(?![a-z0-9])",
                " ", dimension_text,
            )
        dimensions = self._link(dimension_text, {"entity", "dimension"})
        if any(
            item.ref and item.ref.startswith("measure.shop_")
            and item.ref != "measure.shop_category_total"
            for item in measures
        ) and not any(item.ref == "entity.shop" for item in dimensions):
            dimensions.append(SemanticBinding(surface_text="shop", ref="entity.shop"))
        unresolved: list[SemanticBinding] = []
        if any(term in normalized for term in ("hieu qua", "tot nhat", "dang mua", "effective", "worth buying")):
            unresolved.append(SemanticBinding(
                surface_text="hiệu quả/tốt nhất", unresolved=True, reason="metric_ungoverned",
            ))
        if any(term in normalized for term in ("url", "image url", "duong dan", "location", "lokasi")):
            unresolved.append(SemanticBinding(
                surface_text="URL/location", unresolved=True, reason="catalog_gap",
            ))
        if any(term in normalized for term in ("profit", "loi nhuan", "conversion", "chuyen doi", "sku")):
            unresolved.append(SemanticBinding(
                surface_text="biến nghiệp vụ không có trong dataset", unresolved=True, reason="data_absent",
            ))
        measures.extend(unresolved)

        unsupported_ops = tuple(
            name for terms, name in (
                (("recursive", "de quy", "lap den khi"), "recursive"),
                (("udf", "ham tu do", "cong thuc tuy y"), "free_expression"),
                (("forecast", "du bao", "ramalan"), "forecast"),
                # Thống kê phân tán: catalog chỉ chứng nhận
                # median/mean/min/max/count/sum/share, KHÔNG có tứ phân vị, độ
                # lệch chuẩn hay phương sai. Trước khi khai ở đây, câu hỏi IQR
                # rơi vào đường chiếu và ĐỔ RA MỘT DANH SÁCH GIÁ — người dùng
                # hỏi một con số phân tán, nhận về 108 con số, và không câu nào
                # nói rằng IQR đã không được tính.
                #
                # Đo được (Richy, VN, 21/07): IQR thật là 139 500; hệ trả
                # `price=1000` rồi `price=12000`… — tức giá từng listing. Trả
                # lời một câu hỏi KHÁC trong im lặng, đúng lớp lỗi A22 sinh ra
                # để chặn, chỉ khác là nó lọt vì không ai khai phép tính này.
                (("tu phan vi", "tu phan vij", "iqr", "phan vi", "percentile",
                  "do lech chuan", "phuong sai", "standard deviation",
                  "variance", "quartile"), "dispersion_statistic"),
            ) if any(term in normalized for term in terms)
        )
        # W20 — ngày là hàm TOÀN PHẦN trên lịch của bản dữ liệu đang phục vụ.
        from gladiators.domain.calendar import default_calendar
        from .dates import parse_date_expressions

        _calendar = default_calendar()
        date_request = parse_date_expressions(normalized, _calendar)
        dates = date_request.dates
        assumptions: list[str] = []
        if date_request.clamped:
            assumptions.append("date_window_clamped")
        # LUẬT W20-R4: CÓ ngày được nêu thì KHÔNG BAO GIỜ mặc định đợt thu mới
        # nhất. Assumption đó chỉ được thêm khi DateRequest rỗng ở CẢ NĂM ô —
        # dòng code cũ (`if not dates`) là thứ đã sinh ra hai ca over_answer,
        # vì một ngày ngoài cửa sổ cũng làm `dates` rỗng.
        # Câu hỏi ĐẾM NGÀY nói về CẢ KỲ, không về một đợt thu. Mặc định "đợt
        # thu mới nhất" là đúng cho một aggregate cross-sectional (giá trung vị
        # hôm nào?) và SAI hẳn ở đây: đếm số ngày phân biệt bên trong một ngày
        # luôn ra 1. Đo được: "Shop Bibica xuất hiện trong bao nhiêu ngày ở VN"
        # trả 1, trong khi đáp án thật là 18.
        #
        # Không phải nới mặc định cho mọi câu — chỉ cho measure mà bản thân nó
        # đếm ngày, vì với measure đó "một lát cắt" không phải một câu trả lời
        # thu hẹp, nó là một câu trả lời vô nghĩa.
        # "TỪ ngày A ĐẾN ngày B" là một CỬA SỔ, không phải hai mốc — trừ khi
        # câu hỏi nói rõ là đang so hai mốc. Hai hình dạng đó trả lời hai câu
        # hỏi khác nhau và cùng có đúng hai ngày trong `dates`, nên phải phân
        # biệt bằng cụm người dùng viết ra:
        #
        #   "có bao nhiêu listing TỪ 1/7 ĐẾN 5/7"      → 701 (phân biệt trong cửa sổ)
        #   "listing ngày 1/7 SO VỚI ngày 21/7"        → 581 → 672 (hai mốc)
        #
        # Trước đây cả hai đều ra hai mốc, nên câu thứ nhất nhận 581→680 kèm
        # dòng "không suy diễn cho các ngày ở giữa" — thành thật, nhưng là một
        # hình dạng khác với hình dạng được hỏi.
        names_a_window = any(
            cue in normalized for cue in
            ("tu ngay", "trong khoang", "trong giai doan", "giai doan tu",
             "khoang tu", "between", "dari tanggal")
        ) and not any(
            cue in normalized for cue in
            ("so voi", "so sanh", "chenh", "thay doi", "tang hay giam",
             "compared", "versus")
        )
        if names_a_window and len(dates) == 2:
            from gladiators.domain.calendar import default_calendar

            window = tuple(
                iso for iso in default_calendar().dates
                if dates[0] <= iso <= dates[1]
            )
            if len(window) > 2:
                dates = window

        counts_days = any(
            item.ref == "derived.observed_day_count" for item in measures
        )
        if not dates and date_request.is_empty() and counts_days:
            from gladiators.domain.calendar import full_window

            dates = full_window()
            assumptions.append(
                "Câu hỏi đếm ngày nên phạm vi là toàn bộ kỳ thu thập, "
                "không phải đợt thu mới nhất.",
            )
        elif not dates and date_request.is_empty():
            # W30-R2: đợt thu mới nhất đọc từ lịch của bản dữ liệu, không ghim.
            # W20-R2: assumption KHÔNG mang chữ số — verifier.scan_numbers quét
            # mọi số trong answer và đòi evidence hậu thuẫn, còn assumption đi
            # kèm câu abstain thì không có evidence nào.
            from gladiators.domain.calendar import latest_snapshot

            dates = (latest_snapshot(),)
            assumptions.append(
                "Mặc định đợt thu mới nhất cho aggregate cross-sectional.",
            )
        filters = []
        if country:
            filters.append(AnalyticalPredicate(field_ref="dim.country", op="eq", value_binding=country))
        if len(dates) == 1:
            filters.append(AnalyticalPredicate(field_ref="dim.date", op="eq", value_binding=dates[0]))
        # WP-A4.4: điều kiện boolean đã có cột vật lý thì bind thành predicate.
        # Trước đây parse chỉ sinh predicate cho country và date, nên mọi câu có
        # điều kiện đều làm synthesize() trả None — kể cả điều kiện hệ thừa sức
        # lọc. Phủ định được xét trước trong `qualifier_match`.
        # WP-A4.3: giá trị chiều có thật trong dữ liệu thì bind thành predicate.
        # Chỉ bind cho chiều mà câu hỏi ĐÃ nêu tên — xem value_probe.bind_values.
        # Import trễ: `agent/` phụ thuộc `planner/`, nên import ở đầu file tạo
        # vòng qua analytics/tools.py.
        from gladiators.agent.value_probe import bind_values

        # W16 §3.3 — thứ tự claim là một QUYẾT ĐỊNH: value binding chạy SAU
        # alias/country/date. Dựng lattice ở đây với đúng những claim đó, rồi
        # value binder chỉ nhìn phần CÒN DƯ. Không có bước này thì "Nấm" khớp
        # bên trong "Việt Nam" và câu bị lọc theo một danh mục chưa ai nhắc tới.
        ledger = _ledger_of(
            text, country=country, dates=dates,
            surfaces=tuple(
                ("alias", item.ref, item.surface_text)
                for item in list(measures) + list(dimensions) if item.surface_text
            ),
        )

        for value_ref, literal in bind_values(
            normalized, country,
            frozenset(item.ref for item in dimensions if item.ref),
            ledger=ledger,
        ):
            filters.append(AnalyticalPredicate(
                field_ref=value_ref, op="eq", value_binding=literal,
            ))
        # W1.2 bước hai: đơn vị phân tích được NÊU TÊN cụ thể thì thành bộ lọc.
        # "shop" giải thành entity.shop (đơn vị đếm), nên dimension_refs ở trên
        # không chứa dim.shop_name và tên shop không bao giờ được bind — câu
        # "listing CỦA shop X" bị đọc thành "listing THEO TỪNG shop", một câu hỏi
        # khác, trả lời trong im lặng (120 listing thành bảng đếm 10 shop).
        # Khớp 0 hoặc >1 ⇒ không làm gì: câu đang gom nhóm chứ không lọc.
        if country:
            from gladiators.domain.catalog import VALUE_DIMENSION_BY_UNIT

            for unit_binding in list(dimensions):
                dim_ref = VALUE_DIMENSION_BY_UNIT.get(unit_binding.ref or "")
                if dim_ref is None:
                    continue
                named = bind_values(
                    normalized, country, frozenset({dim_ref}), ledger=ledger,
                )
                if len(named) != 1:
                    continue
                value_ref, literal = named[0]
                filters.append(AnalyticalPredicate(
                    field_ref=value_ref, op="eq", value_binding=literal,
                ))
                # Đơn vị đã thành điều kiện lọc thì không còn là chiều gom nhóm.
                dimensions = [
                    item for item in dimensions if item.ref != unit_binding.ref
                ]
        qualifier_refs: set[str] = set()
        qualifier_surfaces: list[str] = []
        # LUẬT W18-R6 — chữ TRONG NGOẶC KÉP là một TÊN, không phải một điều kiện.
        #
        # Đo được: shop `"Bánh Kẹo Hải Hà - Chính hãng"` có cụm "chính hãng"
        # nằm trong CHÍNH TÊN NÓ, và binder đọc cụm đó thành qualifier
        # `dim.shop_official = True`. Plan thành "shop tên X **và** là official
        # shop", lọc ra 0 dòng, rồi trả `allow` kèm câu *"không có dòng nào thoả
        # điều kiện"* — trong khi shop đó có 12 listing hôm ấy.
        #
        # Đây là kết cục TỆ HƠN một lời từ chối: số 0 trông như một sự thật về
        # dữ liệu, và mọi lớp kiểm phía sau đều thấy nó hợp lệ (bộ lọc có chạy,
        # evidence có thật, verifier khớp). Cùng shop nhưng tên không chứa cụm
        # đó thì không sinh filter thừa — nên khác biệt nằm ở TÊN, không ở câu
        # hỏi.
        #
        # W18 đã lập luật loại vùng trong ngoặc cho *value binder*; qualifier
        # chưa được che. Một lattice, hai bộ đọc, và bản vá chỉ áp cho một.
        bound_literals = tuple(
            str(predicate.value_binding) for predicate in filters
            if predicate.field_ref not in ("dim.country", "dim.date")
            and isinstance(predicate.value_binding, str)
        )
        qualifier_text = _without_quoted_regions(normalized, text, bound_literals)
        for matched in qualifier_match(qualifier_text):
            # W8.3: op/value đến từ hợp đồng CÓ KIỂU của qualifier — cờ nhãn
            # voucher là "vouchers_count gte 1", không phải "eq True".
            filters.append(AnalyticalPredicate(
                field_ref=matched.spec.ref, op=matched.op,
                value_binding=matched.value,
            ))
            qualifier_refs.add(matched.spec.ref)
            qualifier_surfaces.append(matched.surface)
        # Một ref đã thành điều kiện lọc thì KHÔNG còn là thứ được đo. "Bao nhiêu
        # listing CÓ VOUCHER" đo số listing; "có voucher" là điều kiện. Để nó ở
        # cả hai chỗ làm request khai hai measure cho một câu hỏi một measure, và
        # synthesizer từ chối vì đúng lý do sai.
        if qualifier_refs:
            def _is_condition(binding) -> bool:
                # W8.3: qualifier có thể bind một REF KHÁC với alias cùng cụm
                # ("có nhãn voucher" → predicate trên measure.vouchers_count,
                # alias trên derived.has_voucher_label) — so theo SURFACE để
                # cụm đã thành điều kiện không đội lốt thứ được đo.
                surface = normalize(binding.surface_text)
                return binding.ref in qualifier_refs or any(
                    surface in matched or matched in surface
                    for matched in qualifier_surfaces
                )

            measures = [item for item in measures if not _is_condition(item)]
            dimensions = [item for item in dimensions if not _is_condition(item)]

        # W11.1: chạy SAU _link (measure đã bind) và TRƯỚC khi chốt
        # requested_measures/ranking.
        measures, comparison_filters = _comparison_predicates(
            measures, normalized, text, country,
        )
        filters.extend(comparison_filters)

        # W16/W17: dựng ledger rồi phân giải khung TRƯỚC khi chốt measure/ranking.
        # Ledger dựng trên câu GỐC — hình thái viết hoa/ngoặc kép chỉ còn ở đó.
        _surfaces: list[tuple[str, str | None, str]] = []
        for _item in list(measures) + list(dimensions):
            if _item.surface_text:
                _surfaces.append(("alias", _item.ref, _item.surface_text))
        for _surface in qualifier_surfaces:
            _surfaces.append(("qualifier", None, _surface))
        for _predicate in filters:
            if _predicate.field_ref not in ("dim.country", "dim.date"):
                _surfaces.append(("value", _predicate.field_ref, str(_predicate.value_binding)))
        ledger = _ledger_of(text, country=country, dates=dates, surfaces=tuple(_surfaces))
        frames = resolve_frames(ledger, language if language in ("vi", "id") else "en")
        # Marker khung PHẢI được claim, nếu không "bao nhiêu" ở lại phần dư và
        # W22 biến mọi câu hỏi số lượng thành `A-UNBOUND-CONSTRAINT` — đúng bẫy
        # §21.11 của spec ("đừng để A-UNBOUND-CONSTRAINT thành cổng chặn mọi
        # thứ"). Dựng lại lattice với marker đã nhận; frames không đổi vì chúng
        # phân giải trên lattice TRƯỚC, và claim thêm chỉ làm phần dư nhỏ đi.
        _surfaces = tuple(_surfaces) + tuple(
            ("frame", None, frame.marker_span.normalized) for frame in frames
        )
        ledger = _ledger_of(text, country=country, dates=dates, surfaces=_surfaces)

        # ── W32 — phân giải chữ bằng LLM, CHỈ khi binder tất định bỏ lại ──────
        #
        # Điều kiện bắn cố ý hẹp và đo được: không measure nào bind ĐƯỢC, và còn
        # cụm dư mang nghĩa (`unknown_concept`/`grain_term`, không phải hư từ).
        # Đường tất định trả lời được phần lớn câu ở 56 ms; tầng này chỉ tồn tại
        # cho phần còn lại, nên nó KHÔNG được chạm vào đường đang chạy được.
        #
        # LLM chỉ ĐỀ XUẤT. `resolve_terms` kiểm ref trên chính danh sách vừa gửi
        # rồi mới trả về, nên một ref bịa không thể tới đây.
        term_resolution = None
        if self.term_proposer is not None and not any(item.ref for item in measures):
            # Gom token LIỀN KỀ thành cụm trước khi hỏi. Ledger trả về từng
            # token một (`nhan`, `hang`), và hỏi LLM chữ "nhan" trần là hỏi một
            # câu không ai trả lời được — nghĩa nằm ở CỤM. Chỉ nối những token
            # thật sự cạnh nhau; hai cụm cách nhau bởi một hư từ vẫn là hai cụm.
            residual_spans = _contiguous_residuals(ledger)
            if residual_spans:
                term_resolution = resolve_llm_terms(
                    residual_spans,
                    frozenset({"entity", "dimension", "measure", "derived_metric"}),
                    self.term_proposer, language=language, question=text,
                )
                for span, ref in term_resolution.accepted.items():
                    obj = CATALOG.get(ref)
                    if obj is None:
                        continue
                    binding = SemanticBinding(surface_text=span, ref=ref)
                    if obj.kind in {"measure", "derived_metric"}:
                        measures.append(binding)
                    else:
                        dimensions.append(binding)
                if term_resolution.accepted:
                    # Khung phải phân giải LẠI: chúng bám vào lattice, và lattice
                    # vừa có thêm span được claim. Không dựng lại thì "bao nhiêu"
                    # vẫn trỏ vào một cụm chưa bind và measure mới nằm mồ côi.
                    _surfaces = tuple(_surfaces) + tuple(
                        ("alias", ref, span)
                        for span, ref in term_resolution.accepted.items()
                    )
                    ledger = _ledger_of(
                        text, country=country, dates=dates, surfaces=_surfaces,
                    )
                    frames = resolve_frames(
                        ledger, language if language in ("vi", "id") else "en",
                    )

        # W24-R2: predicate định danh sinh TỪ LEDGER, không từ một regex thứ hai.
        # Trước W24 catalog không phơi `item_id`, nên không plan nào lọc được về
        # một listing cụ thể và `_has_unbound_qualifier` từ chối mọi câu nêu mã
        # sản phẩm — đúng logic, nhưng cái nó bảo vệ là một khoảng trống lấp
        # được. Mã KHÔNG khớp dòng nào vẫn đi qua entity resolution và nhận
        # `A-ENTITY-NOT-FOUND` như trước (W24-R3).
        if not any(f.field_ref == "dim.item_id" for f in filters):
            for _bound in ledger.bound:
                if _bound.producer == "entity_id":
                    filters.append(AnalyticalPredicate(
                        field_ref="dim.item_id", op="eq",
                        value_binding=str(_bound.payload),
                    ))
                    break

        # W4.2 — đếm theo CẤU TRÚC, không theo cụm dính liền. Bốn điều kiện đều
        # bắt buộc: measures rỗng (câu "giá trung vị theo brand" không được biến
        # brand thành measure); đúng MỘT ứng viên (hai chiều thì chọn một là
        # chọn hộ người hỏi); LIỀN KỀ từ hỏi số lượng, kiểm bằng boundary regex
        # chứ không phải `in` ("rating theo brand ... có bao nhiêu listing"
        # không được đếm brand); ref nằm trong registry đã duyệt.
        count_frame_ambiguity: str | None = None
        if not measures:
            count_candidates = []
            for item in dimensions:
                if not item.ref or item.ref not in COUNT_METRIC_BY_SURFACE_REF:
                    continue
                surface = normalize(item.surface_text)
                adjacency = re.compile(
                    r"(?:bao nhieu|berapa|how many)\s+" + re.escape(surface) + r"\b",
                )
                if adjacency.search(normalized):
                    count_candidates.append(item)
            if len(count_candidates) == 1:
                chosen = count_candidates[0]
                measures = [SemanticBinding(
                    surface_text=chosen.surface_text,
                    ref=COUNT_METRIC_BY_SURFACE_REF[chosen.ref],
                )]
                dimensions = [item for item in dimensions if item is not chosen]
            elif len(count_candidates) > 1:
                count_frame_ambiguity = (
                    "Câu hỏi số lượng nêu nhiều chiều cùng lúc: "
                    + ", ".join(item.surface_text for item in count_candidates)
                    + "; không chọn hộ một trong số đó."
                )

        # ── W17: khung lấp khe mà bảng cụm dính liền không với tới ──────────
        #
        # MỘT CHIỀU CÓ CHỦ ĐÍCH: chỉ bắn khi logic cũ KHÔNG ra gì. Nhờ vậy mọi ca
        # đang xanh không thể đổi, và W17 chỉ có thể làm hệ hiểu THÊM — đúng
        # ràng buộc fail-closed của Spec3008 §0.2.
        frame_measure_ref: str | None = None
        # "Không bind được measure nào" KHÁC "đã nhận ra một metric mà catalog
        # không chứng nhận". Câu "Shop hiệu quả nhất tại VN" nêu một metric
        # ungoverned; điền `derived.shop_count` vào đó là trả lời một câu hỏi
        # KHÁC bằng một con số có thật — đúng lớp over_answer mà W17 không được
        # phép tạo ra. Parser đã biết câu này phải clarify; đừng lấp khe đó.
        _has_unresolved = any(item.unresolved for item in measures)
        self_counting_superlative = None
        if not _has_unresolved and not any(item.ref for item in measures):
            for frame in frames:
                # SELECTOR bị loại có chủ đích: "thương hiệu NÀO có nhiều listing
                # NHẤT" có hai khung, và chúng đóng hai vai KHÁC nhau — selector
                # chọn CHIỀU GOM NHÓM (thương hiệu), superlative chọn THỨ ĐƯỢC
                # XẾP HẠNG (listing). Lấy khung đầu tiên theo vị trí sẽ cho
                # measure = brand_count, tức đếm brand thay vì đếm listing theo
                # brand — một câu hỏi khác, trả lời trong im lặng.
                if frame.marker.kind not in ("quantity", "superlative"):
                    continue
                if frame.resolution == "count_metric" and frame.argument_ref:
                    # LUẬT W17-R6 — ĐẾM CHÍNH NHÓM MÌNH KHÔNG PHẢI MỘT CỠ.
                    #
                    # "Shop nào LỚN NHẤT tại VN" không nêu tiêu chí nào. Khung
                    # superlative bám vào `entity.shop`, và luật W17-R2 bên dưới
                    # biến nó thành `derived.shop_count` — tức xếp hạng shop
                    # theo SỐ SHOP. Mỗi nhóm bằng 1, nên hệ đi hết chặng rồi mới
                    # abstain bằng A22-ALIGN-RANK-TIE, một lời từ chối nói sai
                    # trở ngại: thứ thiếu không phải cách phá hoà, mà là câu hỏi
                    # "lớn theo cái gì".
                    #
                    # Đây đúng là cạm bẫy đã ghi ở CLAUDE.md §3.1 — một grain bị
                    # chọn ngầm là một câu hỏi khác bị trả lời ngầm. Khi đơn vị
                    # được đếm TRÙNG với chiều gom nhóm, phép đếm không mang
                    # thông tin, và câu đúng phải là HỎI LẠI.
                    #
                    # "Shop nào có nhiều LISTING nhất" không rơi vào đây: đơn vị
                    # đếm (listing) khác chiều gom nhóm (shop).
                    # So với đối số của khung SELECTOR, không với `dimensions`:
                    # ở điểm này đơn vị được đếm VẪN CÒN trong `dimensions` (nó
                    # chỉ bị gỡ ở dòng dưới), nên so với cả danh sách thì điều
                    # kiện luôn đúng và mọi câu cực trị đều bị hỏi lại. Selector
                    # là thứ chọn CHIỀU GOM NHÓM, nên nó mới là vế cần so.
                    if frame.marker.kind == "superlative" and not any(
                        other.marker.measure_hint for other in frames
                    ) and any(
                        other.marker.kind == "selector"
                        and other.argument_ref == frame.argument_ref
                        for other in frames
                    ):
                        self_counting_superlative = frame
                        break
                    # LUẬT W17-R2: quantity + đơn vị đếm ⇒ measure LÀ metric đếm
                    # đó, và đơn vị RỜI KHỎI requested_dimensions.
                    frame_measure_ref = COUNT_METRIC_BY_SURFACE_REF[frame.argument_ref]
                    dimensions = [i for i in dimensions if i.ref != frame.argument_ref]
                    break
                if frame.resolution == "measure" and frame.argument_ref:
                    frame_measure_ref = frame.argument_ref
                    break
            # Tính từ mang measure ("đắt nhất") khi câu không nêu chữ "giá".
            if frame_measure_ref is None:
                for frame in frames:
                    if frame.marker.measure_hint:
                        frame_measure_ref = frame.marker.measure_hint
                        break
        # ── LIỆT KÊ = ĐẾM GOM NHÓM theo chiều đã nêu ────────────────────────
        #
        # "Liệt kê các sản phẩm của shop X ngày 21/07" parse ra ĐÚNG mọi thứ trừ
        # một measure: `dim.product_name` đã là chiều, shop/ngày/thị trường đã
        # thành filter, `requested_output_shape` đã là `table`. Chỉ vì không có
        # measure nào mà cả câu chết ở A19-CAT *"chưa xác định được chỉ số nào
        # cần đo"* — một lời từ chối đúng chữ nhưng sai việc: người dùng không
        # hỏi một chỉ số, họ hỏi các DÒNG.
        #
        # Không dựng hình dạng plan mới cho việc này. Một phép đếm gom nhóm
        # theo `dim.product_name` TRẢ VỀ ĐÚNG các dòng đó, và nó đi qua nguyên
        # đường tất định đã có — synthesize, validator, compiler, evidence,
        # verifier — nên không có lớp kiểm nào bị bỏ qua. Cột đếm dư ra là cái
        # giá phải trả, và nó rẻ hơn nhiều so với một nhánh IR thứ hai.
        #
        # Điều kiện HẸP: câu phải nêu ý liệt kê, phải chưa có measure nào, và
        # phải đã bind một chiều CÓ cột vật lý để gom nhóm. Thiếu một trong ba
        # thì giữ nguyên hành vi cũ.
        if not frame_measure_ref and not any(item.ref for item in measures):
            # Cụm nêu ý LIỆT KÊ. Danh sách này từng chỉ có "liệt kê" và các
            # biến thể của nó, nên cùng một yêu cầu nói khác đi là trượt: đo
            # được trên cùng một shop và cùng một ngày, "Liệt kê sản phẩm của X"
            # → allow ra tên, còn "Tên của các sản phẩm mà cửa hàng X có" và
            # "X có những sản phẩm nào" → A19-CAT "chưa xác định được chỉ số".
            # Người dùng hỏi một việc, hệ trả lời ba kiểu, hai trong ba là từ
            # chối oan.
            #
            # ĐÃ THỬ và bỏ: suy ra ý liệt kê từ CẤU TRÚC ("có chiều mang tên,
            # không measure, không phép tổng hợp ⇒ hỏi các giá trị"). Nó bắn
            # trên ba câu chỉ NHẮC TỚI một chiều mang tên chứ không hỏi nó —
            # "Shopee verified theo product tại VN", "URL sản phẩm tại VN",
            # "Shop nào có chiến lược voucher hiệu quả nhất VN?" — và biến ba
            # lời từ chối đúng thành ba bảng liệt kê. Sự có mặt của một chiều
            # không phải một yêu cầu về nó; chỉ cụm người dùng viết ra mới là.
            listing_cue = any(
                cue in normalized
                for cue in ("liet ke", "danh sach", "ke ten", "cho toi xem",
                            "cho xem", "list ra", "show me", "daftar",
                            # Cùng một yêu cầu, cách nói khác. "nhung " là dấu
                            # số nhiều tiếng Việt và đã được dùng đúng nghĩa đó
                            # ở `_PLURAL_MARKERS`.
                            "nhung ", "ten cua", "ten cac", "ten san pham",
                            "ten cac san pham", "apa saja", "nama produk",
                            # "có các sản phẩm gì" / "có mặt hàng gì" — cùng
                            # một yêu cầu, cách nói thứ tư. Danh sách này vẫn
                            # là danh sách, và nó sẽ còn trượt; ghi ở đây để
                            # người sau biết đó là giới hạn đã biết chứ không
                            # phải một chỗ chưa ai nghĩ tới.
                            "san pham gi", "mat hang gi", "hang gi",
                            "co cac san pham", "co nhung san pham")
            )
            groupable = [
                item for item in dimensions
                if item.ref and item.ref not in ("dim.country", "dim.date")
                and CATALOG.get(item.ref) is not None and CATALOG[item.ref].physical
            ]
            if listing_cue and groupable:
                frame_measure_ref = "derived.product_count"

        if frame_measure_ref:
            measures = [SemanticBinding(
                surface_text=frame_measure_ref.split(".", 1)[1].replace("_", " "),
                ref=frame_measure_ref,
            )]

        # LUẬT W17-R4: selector + dimension ⇒ chiều gom nhóm.
        for frame in frames:
            if frame.marker.kind != "selector" or frame.resolution != "count_metric":
                continue
            if frame.argument_ref and not any(i.ref == frame.argument_ref for i in dimensions):
                dimensions.append(SemanticBinding(
                    surface_text=frame.marker_span.normalized, ref=frame.argument_ref,
                ))

        # ĐẶT SAU W17-R4 có chủ đích: luật đó thêm lại đơn vị phân tích
        # (`entity.shop`) vào `dimensions`, nên nếu thay nhãn TRƯỚC nó thì
        # đơn vị quay lại và SQL lại có hai cột `shop_name` trùng tên.
        # "TÊN của X là gì" — người dùng hỏi NHÃN, và trước luật này hệ không
        # hiểu điều đó: `"ten"` bị chấm `unknown_concept`, không binder nào nhận
        # nó, và câu trả lời in ra `shop_id=108166524` — một định danh nội bộ.
        #
        # Con số thì đúng (337.000.000 VND, và shop đó thật sự là "Nestlé Chính
        # hãng"), nhưng cái nhãn in kèm KHÔNG phải một quyết định về thứ được
        # hỏi — nó là hệ quả tình cờ của việc plan chọn bảng nào:
        # `product_snapshot_metrics` có `shop_id` mà không có `shop_name`, nên
        # bộ chiếu nhãn lùi về khoá (W25-R1).
        #
        # Bind chiều mang tên làm hai việc cùng lúc, và việc thứ hai mới là
        # việc chính: nó nói cho các tầng sau biết NGƯỜI DÙNG HỎI TÊN. Kéo theo
        # `dim.shop_name` vào tập ref plan phải phủ, nên bộ chọn nguồn tự
        # chuyển sang bảng CÓ cột tên (`products_clean.csv`) — đo được bằng
        # `_plan_relations`.
        if any(cue in normalized for cue in ("ten cua", "ten cac", "ten shop",
                                             "ten cua hang", "ten thuong hieu",
                                             "ten san pham", "goi la gi",
                                             "name of", "nama")):
            from gladiators.domain.catalog import LABEL_REF_BY_UNIT

            # THAY, không THÊM. Giữ cả hai thì đơn vị (chiếu nhãn của nó) và
            # chiều mang tên cùng ra một cột `shop_name`, SQL có hai cột trùng
            # tên và plan chết ở thực thi (A19-EXECUTION). Gom nhóm theo NHÃN
            # là đúng thứ câu hỏi yêu cầu — người dùng hỏi tên, không hỏi mã.
            swapped = [
                SemanticBinding(surface_text=item.surface_text,
                                ref=LABEL_REF_BY_UNIT[item.ref])
                if item.ref in LABEL_REF_BY_UNIT else item
                for item in dimensions
            ]
            # Khử trùng theo ref. Câu "cửa hàng NÀO ... và tên của HÀNG đó" nêu
            # đơn vị hai lần; sau khi thay thì có hai `dim.shop_name`, SQL ra
            # hai cột trùng tên và plan chết ở thực thi.
            seen_refs: set[str] = set()
            dimensions = [
                item for item in swapped
                if item.ref is None or not (item.ref in seen_refs
                                            or seen_refs.add(item.ref))
            ]


        descending = any(term in normalized for term in ("cao nhat", "nhieu nhat", "lon nhat", "highest", "tertinggi", "top"))
        ascending = any(term in normalized for term in ("thap nhat", "it nhat", "lowest", "terendah"))
        rank_ref = next((item.ref for item in measures if item.ref), None)
        ranking = AnalyticalRanking(
            order_by=rank_ref, direction="asc" if ascending else "desc",
            top_k=_requested_top_k(normalized),
        ) if rank_ref and (descending or ascending) else None
        if ranking is None and rank_ref:
            # LUẬT W17-R4 (nửa sau): superlative ⇒ ranking. Bảng `descending`/
            # `ascending` khớp cụm DÍNH LIỀN nên "nhiều … nhất" (circumfix) và
            # "đắt nhất" không bao giờ trúng — đó là d0033/d0034/d0036/h0035.
            for frame in frames:
                if frame.marker.kind == "superlative" and frame.marker.polarity:
                    ranking = AnalyticalRanking(
                        order_by=rank_ref, direction=frame.marker.polarity,
                        top_k=_requested_top_k(normalized),
                    )
                    break
        # "Cửa hàng nào có nhiều SẢN PHẨM nhất" counts products per shop: the
        # counted noun is the unit, not a second grouping key. It only looked
        # like one because "sản phẩm" binds to dim.product_name while the
        # synonymous "listing" binds to entity.product_listing, so the two
        # phrasings of one question took different paths and A22 rejected the
        # plan for "dropping" a dimension nobody grouped by. The original patch
        # required entity.shop to be present; the concept does not, and two rules
        # for one concept drift apart.
        counted_unit = any(term in normalized for term in _COUNTING_CUES)
        if counted_unit:
            dimensions = [
                SemanticBinding(surface_text=item.surface_text, ref="entity.product_listing")
                if item.ref == "dim.product_name" else item
                for item in dimensions
            ]
        # A5: a unit with no column of its own is not a dimension at all, so it must
        # not be reported as one: A22 would otherwise see the plan "drop" a
        # dimension nobody could have grouped by. entity.shop stays -- owning
        # shop_id is what makes a unit groupable as well as countable.
        dimensions = [
            item for item in dimensions
            if not item.ref or CATALOG[item.ref].analysis_role != "analysis_unit"
            or CATALOG[item.ref].physical
        ]
        grouping = tuple(
            item.ref for item in dimensions
            if item.ref and item.ref not in {"dim.country"} and CATALOG[item.ref].physical
        )
        price_change_table = any(
            term in normalized
            for term in ("gia thay doi", "bien dong gia", "price change", "perubahan harga")
        )
        if price_change_table and "dim.date" not in grouping:
            grouping = (*grouping, "dim.date")
        requested_grain = "shop" if "entity.shop" in grouping else "category" if "dim.platform_category_name" in grouping else "listing" if ranking else "group"
        operators = ["filter"]
        if grouping or any(item.ref == "derived.product_count" for item in measures):
            operators.append("aggregate")
        if ranking:
            operators.append("rank")
        comparison = None
        if any(term in normalized for term in ("so sanh", "compare", "bandingkan")):
            comparison = {"mode": "descriptive_group_comparison"}
            operators.append("compare")
        ambiguities = []
        if self_counting_superlative is not None:
            ambiguities.append(
                "Câu hỏi nêu một cực trị nhưng chưa nói theo tiêu chí nào; "
                "hãy nêu rõ đo bằng gì (ví dụ số listing, giá, hay điểm đánh giá)."
            )
        semantic_ambiguities = tuple(dict.fromkeys(self._pending_ambiguities))
        for item in semantic_ambiguities:
            # Render lựa chọn từ MÔ TẢ catalog, không lộ ref nội bộ
            # (INV-NO-INTERNAL-VOCABULARY).
            choices = " hoặc ".join(
                _human_label(ref)
                for ref in item.candidate_refs
            )
            ambiguities.append(
                f'Cụm "{item.surface}" có thể chỉ {choices}; hãy nêu rõ nghĩa nào.'
            )
        if count_frame_ambiguity:
            ambiguities.append(count_frame_ambiguity)
        if count_frame_normalised:
            # Khoá đếm (§0.3 ô 4): nhánh viết lại phải đếm được số lần nó bắn.
            assumptions = (*assumptions, "count_frame_normalised")
        # ``tổng số listing`` là một phép ĐẾM, không phải phép cộng — và khung
        # ngữ pháp đã phân giải đúng như vậy (``quantity`` bám vào một đơn vị
        # phân tích). Nhưng ``_detect_requested_aggregation`` đọc CHUỖI TRẦN,
        # nơi cue ``"tong "`` nằm gọn trong ``"tong so"``, nên nó khai `sum` cho
        # một chỉ số mà catalog không chứng nhận `sum`, và câu bị hỏi lại bằng
        # A19-AGGREGATION. Hai bộ máy cùng đọc một cụm và ra hai kết luận; cái
        # đọc được CẤU TRÚC thắng cái đọc chuỗi.
        _count_refs = frozenset(COUNT_METRIC_BY_SURFACE_REF.values())
        counts_an_entity = any(
            frame.marker.kind == "quantity"
            and (frame.resolution == "count_metric" or frame.argument_ref in _count_refs)
            for frame in frames
        )
        aggregation_text = (
            normalized.replace("tong so", " ") if counts_an_entity else normalized
        )
        requested_aggregation, aggregation_ambiguity = _detect_requested_aggregation(
            aggregation_text,
            has_ranking_subject=_names_a_ranking_subject(normalized),
            asks_for_a_number=any(
                term in normalized for term in _SCALAR_INTERROGATIVE
            ),
        )
        if aggregation_ambiguity:
            ambiguities.append(aggregation_ambiguity)
        # "bao nhiêu phần trăm X" là CÁCH HỎI TỶ LỆ, không phải một cụm chưa
        # hiểu. Đo được: "Tỷ lệ listing có giảm giá ở VN ngày 21/7" trả đúng
        # 514/672, còn "Bao nhiêu phần trăm listing ở VN ngày 21/7 có giảm giá"
        # ra `A22-ALIGN-MEASURE` — cùng một câu hỏi, cùng một năng lực đã có,
        # khác mỗi cách nói. Bộ tách cắt "phần trăm" thành `magnitude_claim
        # 'phan'` + `unknown_concept 'tram'` nên không binder nào nhận nó.
        if requested_aggregation is None and any(
            cue in normalized for cue in (
                "bao nhieu phan tram", "phan tram", "ty le", "ti le",
                "berapa persen", "what percent", "percentage of",
            )
        ):
            # Chỉ bắn khi ref tỷ lệ THẬT SỰ tồn tại cho measure đã bind. Cue
            # rộng làm hỏng những câu chỉ TÌNH CỜ chứa "phần trăm": đo được,
            # dr2607:tc08 ("...làm biên lợi nhuận giảm bao nhiêu phần trăm?")
            # mất hẳn plan `synth:measure.monthly_sold:median` vì `share` được
            # đặt lên một measure không có phép đó. Một cue chỉ nên mở đúng
            # phần nó có năng lực để mở.
            from gladiators.domain.catalog import SHARE_METRIC_BY_MEASURE

            swappable = [
                item for item in measures
                if item.ref in SHARE_METRIC_BY_MEASURE
            ]
            if swappable:
                requested_aggregation = "share"
                measures = [
                    SemanticBinding(
                        surface_text=item.surface_text,
                        ref=SHARE_METRIC_BY_MEASURE[item.ref],
                    )
                    if item.ref in SHARE_METRIC_BY_MEASURE else item
                    for item in measures
                ]
        if requested_aggregation is None:
            # W11.2: alias tỷ lệ được bind ⇒ aggregation đến từ ĐỊNH NGHĨA
            # metric, không phải từ từ "tỷ lệ" trần trong câu.
            from gladiators.domain.metrics import METRICS

            for item in measures:
                if item.ref and item.ref.startswith("derived."):
                    spec = METRICS.get(item.ref.split(".", 1)[1])
                    if spec is not None and spec.share is not None:
                        requested_aggregation = "share"
                        break
        if requested_aggregation in _EXTREMUM_AGGREGATIONS and ranking is not None:
            # W5.2: "giá cao nhất LÀ BAO NHIÊU" hỏi một CON SỐ, còn ranking suy
            # ra từ chính cụm "cao nhất" biến nó thành một câu hỏi về các DÒNG.
            # Giữ cả hai thì plan xếp hạng các dòng trong khi câu hỏi yêu cầu
            # một giá trị tổng hợp, và lời từ chối sinh ra nói về measure bị
            # thay chứ không nói về thứ thật sự sai. Đo trước khi đổi: 0 entry
            # trong 60 plan bị khoá thay đổi.
            ranking = None
            requested_grain = "group"
            operators = [item for item in operators if item != "rank"]
        monetary = any(item.ref in {"measure.price", "derived.estimated_recent_revenue"} for item in measures)
        if not country:
            ambiguities.append(
                "Thiếu country cho metric tiền tệ; không được trộn VND và IDR."
                if monetary else "Thiếu country để khóa scope VN hoặc ID."
            )
        # Hai lối bind giá trị (chiều được nêu tên, và đơn vị phân tích qua
        # VALUE_DIMENSION_BY_UNIT) có thể cùng tìm ra một predicate. Trùng lặp
        # không đổi kết quả SQL nhưng làm `planned_predicate_count` lệch, và
        # W1.4 dùng đúng con số đó để phát hiện predicate rơi mất.
        _seen: set[tuple[str, str, str]] = set()
        filters = [
            item for item in filters
            if (key := (item.field_ref, item.op, str(item.value_binding))) not in _seen
            and not _seen.add(key)
        ]

        return AnalyticalRequest(
            llm_terms=term_resolution.as_attrs() if term_resolution else {},
            date_request=date_request.as_dict(),
            binding_ledger={
                **ledger.digest(),
                "frame_hits": frame_hits(frames),
                "plural_folded": plural_folded,
            },
            unbound_spans=tuple(
                (item.kind, item.span.normalized) for item in ledger.significant()
            ),
            normalized_question=normalized,
            language=language if language in {"vi", "id"} else "unknown",
            requested_measures=tuple(measures), requested_dimensions=tuple(dimensions),
            filters=tuple(filters), time_scope=AnalyticalTimeScope(
                dates=dates, mode="single_snapshot" if len(dates) == 1 else "all_with_caveat",
            ), grouping=grouping, comparison=comparison, ranking=ranking, requested_grain=requested_grain,
            analytical_operators=tuple(operators), ambiguities=tuple(ambiguities),
            assumptions=tuple(assumptions),
            requested_output_shape="ranking" if ranking else "scalar" if not grouping else "table",
            unsupported_operators=unsupported_ops,
            requested_aggregation=requested_aggregation,
            semantic_ambiguities=semantic_ambiguities,
        )


def classify_a19(request: AnalyticalRequest) -> tuple[str, str, str] | None:
    """Trả ``(action, rule_id, reason)`` hoặc None nếu request được admit vào P8."""
    if request.ambiguities:
        return "clarify", "A-ANALYTICAL-AMBIGUITY", "; ".join(request.ambiguities)
    if request.unsupported_operators:
        return "abstain", "A19-OP", "IR hiện không hỗ trợ operator: " + ", ".join(request.unsupported_operators)
    unresolved = [item for item in request.requested_measures + request.requested_dimensions if item.unresolved]
    if any(item.reason == "metric_ungoverned" for item in unresolved):
        return "clarify", "A19-METRIC", "Metric nghiệp vụ chưa có định nghĩa được duyệt; có thể chuyển sang so sánh mô tả nếu bạn xác nhận."
    if any(item.reason == "catalog_gap" for item in unresolved):
        return "abstain", "A19-CAT", "Trường dữ liệu được hỏi chưa được mở cho truy vấn."
    if any(item.reason == "data_absent" for item in unresolved):
        return "abstain", "A-DATA-ABSENT", "Dataset không có biến nghiệp vụ được yêu cầu."
    if not any(item.ref for item in request.requested_measures):
        return "clarify", "A19-CAT", "Chưa xác định được chỉ số nào cần đo từ câu hỏi."
    return None


def classify_complexity(request: AnalyticalRequest) -> Literal["L0", "L1", "L2", "L3", "L4"]:
    """Phân lớp bảo thủ từ semantic contract; không dựa vào lời tự khai của LLM planner."""
    resolved_measures = sum(bool(item.ref) for item in request.requested_measures)
    if request.comparison and (resolved_measures >= 2 or len(request.grouping) >= 2):
        return "L4"
    if request.comparison or len(request.grouping) >= 2:
        return "L3"
    if request.ranking or request.grouping or "aggregate" in request.analytical_operators:
        return "L2"
    if request.filters:
        return "L1"
    return "L0"
