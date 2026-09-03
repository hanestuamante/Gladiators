"""W17 — ngữ pháp KHUNG thay cho danh sách cụm.

``derived.product_count.aliases`` hôm nay chứa ``"bao nhiêu listing"``,
``"berapa listing"``, ``"berapa produk"``, ``"how many listing"``,
``"jumlah produk"`` — **năm cụm dính liền cho một khái niệm**. Benchmark tìm ra
``berapa banyak toko``, ``how many shops``, ``jumlah toko`` chưa có. Mỗi đơn vị
đếm mới nhân với mỗi khung mới nhân với mỗi ngôn ngữ.

Đếm **không phải** một danh sách chuỗi. Nó là một **quan hệ ngữ pháp** giữa một
*từ hỏi lượng* và một *đơn vị đếm được*, và quan hệ đó là thứ hữu hạn:

* khung VI/ID/EN là *circumfix* hoặc *tách được*: ``bao nhiêu … ?``,
  ``berapa banyak X``, ``how many Xs``, ``nhiều X nhất``, ``X nào … nhất``,
  ``mana yang … terbanyak``;
* một bộ khớp liền kề cần **một cụm cho mỗi (ngôn ngữ × khung × đơn vị)** — một
  dãy vô hạn, và mỗi lần thêm một cụm là một lần khẳng định rằng lần này đã đủ.

Module này khai **marker** (hữu hạn, dữ liệu) và **luật phân giải** (thuật toán,
độc lập ngôn ngữ). Đối số của một khung tìm bằng cách quét trên lattice của W16,
nên nó không quan tâm giữa marker và đối số có bao nhiêu từ chen vào.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gladiators.domain.catalog import CATALOG, COUNT_METRIC_BY_SURFACE_REF
from gladiators.domain.function_words import is_function_word

from .spans import BindingLedger, BoundSpan, Span

FrameKind = Literal["quantity", "superlative", "comparative", "selector", "aggregate"]
Attachment = Literal["prefix", "suffix", "circumfix", "free"]
Resolution = Literal["count_metric", "measure", "dimension", "unresolved"]


class FrameRegistryError(ValueError):
    """Bảng marker mâu thuẫn — hỏng ở import, không đợi một câu hỏi chạm vào."""


@dataclass(frozen=True)
class FrameMarker:
    surfaces: tuple[str, ...]
    kind: FrameKind
    language: Literal["vi", "id", "en", "*"]
    attachment: Attachment
    polarity: Literal["desc", "asc"] | None = None
    # CHIỀU CÓ CHẮC KHÔNG. `"nhất"` trần cho biết đây là một cực trị nhưng KHÔNG
    # cho biết cực trị nào — chiều nằm ở tính từ đứng trước ("cao/nhiều/lớn" so
    # với "thấp/ít/kém/bét/rẻ"). Khai `desc` cho nó là chọn hộ một trong hai.
    #
    # Đo được: *"shop nào có doanh thu KÉM NHẤT tại VN ngày 21/07"* trả về
    # 337.000.000 (Nestlé Chính hãng) — đó là shop doanh thu CAO NHẤT. Đáp án
    # thật là 4.056.000 (Richy - Chi nhánh Miền Nam). Câu hỏi thấp nhất được
    # trả lời bằng cao nhất, im lặng, kèm evidence. Cùng câu viết `"thấp nhất"`
    # hay `"lowest"` thì đúng, vì hai cụm đó có marker riêng.
    #
    # Registry vẫn ĐÒI mọi superlative khai polarity (nó là giá trị mặc định khi
    # không có gì rõ hơn); cờ này nói cho tầng sau biết ĐỪNG TIN nó.
    polarity_certain: bool = True
    measure_hint: str | None = None
    aggregation: str | None = None


# Từ TĂNG CƯỜNG: bị BỎ QUA khi đi tìm đối số, không phải một khung riêng.
# ``berapa banyak toko`` hỏng hôm nay đúng vì ``banyak`` chen giữa ``berapa`` và
# ``toko`` làm regex kề không khớp.
INTENSIFIERS: dict[str, tuple[str, ...]] = {
    "vi": ("nhieu", "lam", "bao", "rat", "that"),
    "id": ("banyak", "sangat"),
    "en": ("many", "much", "very"),
}
_ALL_INTENSIFIERS = frozenset(w for group in INTENSIFIERS.values() for w in group)

FRAME_MARKERS: tuple[FrameMarker, ...] = (
    # --- quantity ---------------------------------------------------------
    FrameMarker(("bao nhieu", "so luong", "tong so", "may"), "quantity", "vi", "prefix"),
    FrameMarker(("berapa", "jumlah"), "quantity", "id", "prefix"),
    FrameMarker(("how many", "number of", "count of", "total number of"),
                "quantity", "en", "prefix"),
    # --- superlative ------------------------------------------------------
    FrameMarker(("nhat", "dan dau", "hang dau"), "superlative", "vi", "suffix", "desc",
                polarity_certain=False),
    FrameMarker(("it nhat", "thap nhat"), "superlative", "vi", "suffix", "asc"),
    # CIRCUMFIX: "ít MẶT HÀNG nhất" — hai mảnh cách nhau bởi chính đơn vị được
    # đếm, nên surface liền "it nhat" không khớp và câu rơi về `desc` mặc định.
    # Đo được: "shop nào có ÍT mặt hàng nhất" trả về shop NHIỀU listing nhất.
    # `_find_markers` khớp theo cụm liền, nên mảnh đầu được khai riêng; mảnh
    # "nhat" đứng sau vẫn do marker superlative desc nhận, và luật dài-trước
    # cùng `taken` giữ cho hai marker không giẫm nhau.
    FrameMarker(("it",), "superlative", "vi", "prefix", "asc"),
    # VẾ ĐỐI XỨNG của circumfix trên. Trước đây chiều `desc` của "nhiều … nhất"
    # đến từ chính marker `"nhất"` trần — mà marker đó nay khai
    # `polarity_certain=False`, nên thiếu dòng này thì "shop nào có NHIỀU listing
    # nhất" mất chiều và trả về shop đầu bảng thay vì shop nhiều nhất (đo được:
    # Bibica 92 thay vì Richy - Chi nhánh Miền Nam).
    #
    # Chiều ở đây CHẮC: "nhiều"/"lớn" chỉ có một nghĩa xếp hạng.
    #
    # `"cao"` CỐ Ý không nằm đây. Nó fold trùng nửa sau của `"quảng cáo"`
    # (`quang cao`), nên thêm nó biến câu *"Quảng cáo tạo bao nhiêu sales?"*
    # thành một cực trị giảm dần — đo được ở `questions:q43`, plan đổi từ
    # `none` sang `desc` top_k=1. Đúng lớp lỗi `"giá trị"`→`measure.price` mà
    # CLAUDE.md §3.1 gọi là "ánh xạ chữ→ký hiệu là chỗ hỏng".
    #
    # Không mất gì: cụm dính liền `"cao nhất"` đã có trong bảng `descending`
    # của `semantic_parser`, và circumfix `"cao … nhất"` không xuất hiện trong
    # bộ đề. Nếu sau này cần, nó phải đi kèm một trap cho `"quảng cáo"`.
    FrameMarker(("nhieu", "lon"), "superlative", "vi", "prefix", "desc"),
    FrameMarker(("terbanyak", "tertinggi", "paling"), "superlative", "id", "suffix", "desc"),
    FrameMarker(("terendah", "tersedikit"), "superlative", "id", "suffix", "asc"),
    FrameMarker(("most", "highest", "largest", "top", "leading"),
                "superlative", "en", "prefix", "desc"),
    FrameMarker(("least", "lowest", "fewest"), "superlative", "en", "prefix", "asc"),
    # --- selector ---------------------------------------------------------
    FrameMarker(("nao", "gi"), "selector", "vi", "suffix"),
    FrameMarker(("mana", "apa"), "selector", "id", "suffix"),
    FrameMarker(("which", "what"), "selector", "en", "prefix"),
    # --- comparative ------------------------------------------------------
    FrameMarker(("hon",), "comparative", "vi", "suffix"),
    FrameMarker(("lebih",), "comparative", "id", "prefix"),
    FrameMarker(("more than", "greater than"), "comparative", "en", "free"),
    # --- aggregate --------------------------------------------------------
    FrameMarker(("trung binh", "binh quan", "rata rata", "average", "mean"),
                "aggregate", "*", "prefix", aggregation="mean"),
    FrameMarker(("trung vi", "median"), "aggregate", "*", "prefix", aggregation="median"),
    FrameMarker(("tong", "tong cong", "sum", "total"),
                "aggregate", "*", "prefix", aggregation="sum"),
)

# Tính từ MANG measure — bảng riêng, cùng cơ chế. ``đắt nhất`` là một cực trị
# trên giá mà không câu nào nêu chữ "giá".
MEASURE_HINTS: tuple[FrameMarker, ...] = (
    FrameMarker(("dat", "mac"), "superlative", "vi", "suffix", "desc",
                measure_hint="measure.price"),
    FrameMarker(("re",), "superlative", "vi", "suffix", "asc",
                measure_hint="measure.price"),
    FrameMarker(("expensive", "priciest"), "superlative", "en", "prefix", "desc",
                measure_hint="measure.price"),
    FrameMarker(("cheapest",), "superlative", "en", "prefix", "asc",
                measure_hint="measure.price"),
    FrameMarker(("termahal",), "superlative", "id", "suffix", "desc",
                measure_hint="measure.price"),
    FrameMarker(("termurah",), "superlative", "id", "suffix", "asc",
                measure_hint="measure.price"),
    # CỤM ĐẦY ĐỦ "ban chay nhat", KHÔNG phải "ban chay" trần — và khác biệt đó
    # là cả vấn đề, không phải một chi tiết:
    #
    #   "Sản phẩm nào BÁN CHẠY NHẤT"  → xác định: hàng đầu theo monthly_sold
    #   "Bao nhiêu sản phẩm BÁN CHẠY" → MƠ HỒ: bán chạy là từ ngưỡng nào?
    #
    # Chú thích tay của bộ đề (`annotations_A.json`, acc-v1-0074) nói đúng điều
    # thứ hai: *"'Bán chạy' không có ngưỡng định nghĩa — mỗi ngưỡng cho một số
    # khác"*. Cực trị tự giải quyết ngưỡng; một bộ lọc trần thì không. Khai cụm
    # trần ở đây sẽ biến một câu PHẢI hỏi lại thành một câu trả lời bừa.
    FrameMarker(("ban chay nhat", "best selling", "terlaris"),
                "superlative", "*", "suffix", "desc",
                measure_hint="measure.monthly_sold"),
)

ALL_MARKERS: tuple[FrameMarker, ...] = FRAME_MARKERS + MEASURE_HINTS


def _check_registry() -> None:
    """Fail ở import theo đúng khuôn ``_build_catalog`` / ``VALUE_DIMENSION_BY_UNIT``."""
    for marker in ALL_MARKERS:
        if not marker.surfaces:
            raise FrameRegistryError(f"marker {marker.kind} không có surface nào")
        if marker.measure_hint and marker.measure_hint not in CATALOG:
            raise FrameRegistryError(
                f"measure_hint trỏ ref không tồn tại: {marker.measure_hint}",
            )
        if marker.kind == "superlative" and marker.polarity is None:
            raise FrameRegistryError(f"superlative thiếu polarity: {marker.surfaces}")
        if marker.kind == "aggregate" and marker.aggregation is None:
            raise FrameRegistryError(f"aggregate thiếu aggregation: {marker.surfaces}")


_check_registry()


# Hậu tố số nhiều theo ngôn ngữ (LUẬT W17-R1). HẸP CÓ CHỦ ĐÍCH: chỉ chạy khi
# khớp thẳng đã thất bại, và chỉ trên hậu tố đã khai. Đây là fallback của alias,
# KHÔNG phải alias mới — thêm "shops" vào catalog là thêm một cụm nữa vào chính
# cái danh sách vô hạn mà W17 tồn tại để đóng.
PLURAL_SUFFIXES: dict[str, tuple[str, ...]] = {
    "en": ("es", "s"),
    "id": (),      # số nhiều tiếng Indonesia là lặp từ (X-X), xử lý riêng
    "vi": (),      # tiếng Việt không có hình thái số nhiều
}


def singularize(word: str, language: str) -> str | None:
    """Dạng số ít của ``word``, hoặc ``None`` nếu không nhận ra hậu tố nào.

    Ngôn ngữ được nêu tra TRƯỚC, rồi tới các ngôn ngữ còn lại. Lý do giống hệt
    ``_find_markers``: nhãn ngôn ngữ được gán bằng bốn từ, và
    ``"How many listings are there in Indonesia on 2026-07-03?"`` không chứa từ
    nào trong đó nên bị gán ``vi`` — mà ``PLURAL_SUFFIXES["vi"]`` rỗng, nên
    ``listings`` không bao giờ rút về ``listing``, không measure nào bind, và
    một câu trả lời được thành một lời hỏi lại.

    Nới ra ở đây AN TOÀN THEO CẤU TRÚC, không phải theo may rủi: người gọi
    (``singularize_unmatched``) chỉ chấp nhận kết quả khi dạng số ít **là một
    alias đã biết**. Thử thêm hậu tố của ngôn ngữ khác vì thế không thể bịa ra
    một từ — nó chỉ có thể tìm thấy một từ vốn đã nằm trong catalog.
    """
    ordered = (language, *(lang for lang in PLURAL_SUFFIXES if lang != language))
    for lang in ordered:
        for suffix in PLURAL_SUFFIXES.get(lang, ()):
            if len(word) > len(suffix) + 2 and word.endswith(suffix):
                return word[: -len(suffix)]
    if "-" in word:                      # tiếng Indonesia: "toko-toko" → "toko"
        head, _, tail = word.partition("-")
        if head and head == tail:
            return head
    return None


@dataclass(frozen=True)
class ResolvedFrame:
    marker: FrameMarker
    marker_span: Span
    argument_span: Span | None
    argument_ref: str | None
    resolution: Resolution
    # W17-R8: grain của ref đối số. Trộn ``shop_snapshot`` với
    # ``listing_snapshot`` trong một Aggregate là nối hai grain âm thầm.
    grain: str | None = None


def _clause_bound(ledger: BindingLedger, index: int, direction: int) -> int:
    """Biên mệnh đề theo hướng quét: dấu phẩy, "và"/"dan"/"and", dấu hỏi."""
    stop_words = {"va", "dan", "and", "hoac", "atau", "or", "nhung", "but"}
    i = index
    while 0 <= i < len(ledger.tokens):
        token = ledger.tokens[i]
        if token.is_punct or token.normalized in stop_words:
            return i
        i += direction
    return i


def _bound_at(ledger: BindingLedger, index: int) -> BoundSpan | None:
    for item in ledger.bound:
        if item.span.start <= index < item.span.end:
            return item
    return None


def _classify(ref: str) -> tuple[Resolution, str | None]:
    if ref in COUNT_METRIC_BY_SURFACE_REF:
        return "count_metric", CATALOG[ref].grain if ref in CATALOG else None
    obj = CATALOG.get(ref)
    if obj is None:
        return "unresolved", None
    if obj.kind in {"measure", "derived_metric"}:
        return "measure", obj.grain
    if obj.kind in {"dimension", "entity"}:
        return "dimension", obj.grain
    return "unresolved", obj.grain


def _find_markers(ledger: BindingLedger, language: str) -> list[tuple[FrameMarker, Span]]:
    """Marker xuất hiện trên lattice, DÀI TRƯỚC để cụm dài không bị cụm ngắn ăn."""
    found: list[tuple[FrameMarker, Span]] = []
    taken: set[int] = set()
    # MỌI ngôn ngữ, không lọc theo ``language`` — cùng quyết định đã ghi ở
    # ``function_words.is_function_word`` (tra hợp của cả ba) và ở
    # ``_ALL_INTENSIFIERS`` ngay trong file này. Lọc ở đây là chỗ duy nhất còn
    # tin vào nhãn ngôn ngữ, và nhãn đó được gán bằng BỐN TỪ
    # (``produk``/``penjualan``/``mirip``/``promosi``, parser.py:155).
    #
    # Đo được: ``"Berapa jumlah listing di Indonesia pada 03/07?"`` không chứa
    # từ nào trong bốn từ đó ⇒ nhãn ``vi`` ⇒ chỉ marker tiếng Việt được quét ⇒
    # KHÔNG khung nào khớp ⇒ không measure nào bind ⇒ plan rơi về đợt thu gần
    # nhất và A22 bắt lệch ngày. Câu tiếng Việt cùng nghĩa thì trả lời được.
    # Một khung đếm là quan hệ ngữ pháp; nó không ngừng là quan hệ đó vì bộ
    # đoán ngôn ngữ đoán trượt.
    #
    # ``language`` vẫn là tham số vì nó còn dùng ở chỗ khác của module.
    candidates = [
        (marker, surface)
        for marker in ALL_MARKERS
        for surface in marker.surfaces
    ]
    candidates.sort(key=lambda pair: -len(pair[1].split()))
    words = [t.normalized for t in ledger.tokens]
    for marker, surface in candidates:
        want = surface.split()
        size = len(want)
        for i in range(len(words) - size + 1):
            if words[i:i + size] != want:
                continue
            if any(j in taken for j in range(i, i + size)):
                continue
            taken.update(range(i, i + size))
            found.append((marker, Span(
                i, i + size, surface,
                " ".join(t.raw for t in ledger.tokens[i:i + size]),
            )))
            break
    found.sort(key=lambda pair: pair[1].start)
    return found


def resolve_frames(ledger: BindingLedger, language: str) -> tuple[ResolvedFrame, ...]:
    """Phân giải mọi khung trên lattice — deterministic, độc lập ngôn ngữ.

    Với mỗi marker, quét theo hướng của ``attachment`` trong CÙNG MỆNH ĐỀ, bỏ
    qua từ tăng cường và từ chức năng, dừng ở ``BoundSpan`` đầu tiên.
    """
    resolved: list[ResolvedFrame] = []
    for marker, span in _find_markers(ledger, language):
        directions: tuple[int, ...]
        if marker.attachment == "prefix":
            directions = (1,)
        elif marker.attachment == "suffix":
            directions = (-1,)
        else:
            directions = (1, -1)

        argument: BoundSpan | None = None
        for direction in directions:
            start = span.end if direction > 0 else span.start - 1
            limit = _clause_bound(ledger, start, direction)
            index = start
            while (index < limit) if direction > 0 else (index > limit):
                token = ledger.tokens[index]
                if (
                    token.is_punct
                    or token.normalized in _ALL_INTENSIFIERS
                    or is_function_word(token.normalized, language)
                ):
                    index += direction
                    continue
                candidate = _bound_at(ledger, index)
                if candidate is not None and candidate.ref:
                    argument = candidate
                    break
                index += direction
            if argument is not None:
                break

        if argument is None or not argument.ref:
            resolved.append(ResolvedFrame(marker, span, None, None, "unresolved"))
            continue
        resolution, grain = _classify(argument.ref)
        resolved.append(ResolvedFrame(
            marker, span, argument.span, argument.ref, resolution, grain,
        ))
    return tuple(resolved)


def frame_hits(frames: tuple[ResolvedFrame, ...]) -> dict[str, int]:
    """Khoá telemetry thay cho ``count_frame_normalised`` của W4.1.

    Vẫn giữ tính chất "nhánh nào cũng đếm được số lần bắn", và mang nhiều thông
    tin hơn: một bảng ``{kind: 0}`` và một bảng thiếu khoá đó nói hai chuyện
    khác nhau.
    """
    hits: dict[str, int] = {}
    for frame in frames:
        hits[frame.marker.kind] = hits.get(frame.marker.kind, 0) + 1
        if frame.resolution == "unresolved":
            hits["unresolved"] = hits.get("unresolved", 0) + 1
    return hits


def singularize_unmatched(normalized: str, language: str, known: frozenset[str]) -> tuple[str, int]:
    """LUẬT W17-R1 — hình thái số nhiều là FALLBACK của alias, không phải alias mới.

    ``"How many shops are there"`` hỏng vì alias là ``shop`` còn câu dùng
    ``shops``. Thêm ``"shops"`` vào catalog là thêm một cụm nữa vào chính cái
    danh sách vô hạn mà W17 tồn tại để đóng.

    HẸP CÓ CHỦ ĐÍCH, ba điều kiện cùng lúc:

    1. token gốc **không** phải một alias đã biết (không viết đè lên thứ đã khớp);
    2. dạng số ít **là** một alias đã biết (không bịa ra một từ);
    3. hậu tố nằm trong bảng đã khai theo ngôn ngữ.

    Trả ``(câu đã viết lại, số token đã đổi)`` — số đếm là khoá telemetry: một
    nhánh không đếm được số lần bắn thì "đã đo" và "đã chạy" không phân biệt được.
    """
    rewritten: list[str] = []
    changed = 0
    for word in normalized.split():
        if word in known:
            rewritten.append(word)
            continue
        singular = singularize(word, language)
        if singular and singular in known:
            rewritten.append(singular)
            changed += 1
        else:
            rewritten.append(word)
    return " ".join(rewritten), changed
