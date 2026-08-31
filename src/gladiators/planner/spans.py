"""W16 — Binding Ledger: lattice span dùng chung cho mọi bộ khớp.

Tầng binding TRƯỚC module này là *N bộ khớp chuỗi con liền kề chạy độc lập trên
một chuỗi đã chuẩn hoá*, mỗi bộ giữ một danh sách cụm riêng, mỗi bộ trả một
output tuỳ chọn, và **không bộ nào ghi lại nó đã tiêu thụ gì, cũng không ai ghi
lại phần còn dư**.

Hệ quả đo được trên 45 ca fail của benchmark accuracy v1:

1. **Cấu trúc rời không chạm tới được.** ``bao nhiêu … ?``, ``berapa banyak X``,
   ``nhiều X nhất`` là *circumfix*; một bộ khớp liền kề cần một cụm cho mỗi
   (ngôn ngữ × khung × đơn vị) — một dãy vô hạn.
2. **Phần không khớp bị vứt không dấu vết.** Khi ``Bibica`` không bind được,
   request KHÔNG có filter brand: plan khớp request, evidence khớp plan, answer
   khớp evidence, verifier xanh. Chuỗi nhất quán từ đầu đến cuối, quanh **một
   câu hỏi khác**.
3. **Lý do từ chối do thứ tự luật quyết định**, không do thứ đã chặn: một câu
   hỏi về NPS thiếu country nhận lời khuyên "hãy chọn thị trường" — một hành
   động không thể làm cột NPS tồn tại.

Điểm quyết định của module: **phần dư là dữ liệu CÓ KIỂU, không phải rác.** Ba
lỗ độc lập hôm nay (tên riêng ngắn, ngày ngoài cửa sổ, khái niệm dataset không
có) trở thành **một** phép kiểm mà năm lớp phía sau đọc được.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

from gladiators.domain.function_words import is_function_word

# Ký tự mở/đóng ngoặc kép mà người dùng thật sự gõ — thẳng, cong, và đơn.
_QUOTE_CHARS = "\"'‘’“”"

# Token = cụm chữ-số liền nhau, HOẶC một dấu câu có nghĩa ranh giới mệnh đề.
# Giữ dấu câu làm token riêng để W17 biết mệnh đề dừng ở đâu; bỏ chúng đi thì
# "shop A, brand B" và "shop A brand B" không phân biệt được.
_CLAUSE_PUNCT = ",;?()"
_TOKEN_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)*|[^\W_]+|[" + re.escape(_CLAUSE_PUNCT) + r"]")


def fold(text: str) -> str:
    """Bỏ dấu + lowercase, GIỮ NGUYÊN độ dài khái niệm.

    Khác ``semantic_parser.normalize``: hàm kia chạy trên cả câu và huỷ ánh xạ
    về vị trí gốc, nên ``value_probe`` phải quét lại ``raw_question`` bằng một
    regex thứ hai để hỏi "token này có viết hoa không". Fold theo TỪNG token thì
    câu hỏi đó trả lời được tại chỗ.
    """
    lowered = text.lower().replace("đ", "d")
    stripped = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in stripped if unicodedata.category(ch) != "Mn")


@dataclass(frozen=True)
class Token:
    index: int
    normalized: str
    raw: str
    char_start: int
    char_end: int
    capitalized: bool
    quoted: bool
    numeric: bool

    # Viết hoa ĐẦU CÂU không phải bằng chứng của một tên riêng — mọi câu đều
    # bắt đầu bằng một chữ hoa. Trước khi có cờ này, "Điểm NPS của shop…" cho
    # `Điểm` là ``proper_name`` và W22 sẽ từ chối oan một câu chỉ thiếu measure.
    sentence_initial: bool = False

    @property
    def is_punct(self) -> bool:
        return self.raw in _CLAUSE_PUNCT

    @property
    def name_shaped(self) -> bool:
        """Hình dạng tên riêng: trong ngoặc kép, hoặc viết hoa GIỮA câu."""
        return self.quoted or (self.capitalized and not self.sentence_initial)


@dataclass(frozen=True)
class Span:
    """Khoảng token nửa mở ``[start, end)``."""

    start: int
    end: int
    normalized: str
    raw: str

    def __len__(self) -> int:
        return self.end - self.start

    def overlaps(self, other: "Span") -> bool:
        return self.start < other.end and other.start < self.end


Producer = Literal[
    "alias", "frame", "value", "qualifier", "date", "country",
    "number", "entity_id", "function_word",
]


@dataclass(frozen=True)
class BoundSpan:
    span: Span
    producer: Producer
    ref: str | None = None
    payload: Any | None = None


ResidualKind = Literal[
    "proper_name",      # viết hoa hoặc trong ngoặc kép, không phải từ chức năng
    "date_like",        # phân tích được thành ngày nhưng không bind được
    "quantity_phrase",  # một số + đơn vị không thành predicate nào
    "unknown_concept",  # từ nội dung mà không alias nào phủ  ← ĐÁY
    "grain_term",       # nêu một grain (giờ, phút, sku, đơn hàng)
    "magnitude_claim",  # "một nửa", "gấp đôi", "50%" cạnh một động từ biến động
    "function_word",    # bỏ qua được
]


@dataclass(frozen=True)
class ResidualSpan:
    span: Span
    kind: ResidualKind
    evidence: tuple[str, ...] = ()


# Từ nêu một GRAIN mà dataset không có. Chúng phải rơi vào ``grain_term`` chứ
# không phải ``unknown_concept``: hai loại này dẫn tới hai lời từ chối khác nhau
# (W22), và "hệ không hiểu từ này" khác "hệ hiểu, dữ liệu không có grain đó".
_GRAIN_TERMS = {
    "gio", "phut", "giay", "tuan", "thang", "quy", "nam",
    "sku", "bien", "the", "variant", "don", "hang", "order", "pesanan",
    "hourly", "weekly", "monthly", "jam", "menit", "minggu", "bulan",
}

# Cụm chỉ ĐỘ LỚN của một biến động. W21 đọc chúng; ledger chỉ đánh dấu.
_MAGNITUDE_TERMS = {
    "nua", "phan", "gap", "doi", "ba", "tu", "half", "double", "triple",
    "setengah", "ganda",
}

_DATE_LIKE = re.compile(r"^\d{1,4}([/-]\d{1,2}){1,2}$|^\d{1,2}$")

# Kết thúc câu: dấu chấm/hỏi/than, có thể kèm ngoặc đóng và khoảng trắng.
_SENTENCE_END = re.compile(r"[.?!][\"'\)\s]*$")


@dataclass(frozen=True)
class BindingLedger:
    tokens: tuple[Token, ...]
    bound: tuple[BoundSpan, ...]
    residual: tuple[ResidualSpan, ...]
    raw_question: str = ""

    def significant(self) -> tuple[ResidualSpan, ...]:
        """Span dư KHÁC ``function_word`` — thứ duy nhất W22 được nhìn.

        Cho W22 nhìn cả function word sẽ biến mỗi từ nối chưa vào registry thành
        một ``unknown_concept``, và ``over_refusal_rate`` tăng vọt.
        """
        return tuple(item for item in self.residual if item.kind != "function_word")

    def coverage(self) -> float:
        """Tỷ lệ token đã bound hoặc là từ chức năng. Khoá telemetry.

        Không có nó thì "ledger đã chạy" và "ledger chạy mà không claim gì" là
        hai bảng số giống hệt nhau.
        """
        countable = [t for t in self.tokens if not t.is_punct]
        if not countable:
            return 1.0
        claimed = sum(
            1 for t in countable
            if self.claimed(t.index, t.index + 1)
            or is_function_word(t.normalized)
        )
        return claimed / len(countable)

    def claimed(self, start: int, end: int) -> bool:
        """Khoảng token này đã bị một ``BoundSpan`` chiếm chưa."""
        probe = Span(start, end, "", "")
        return any(item.span.overlaps(probe) for item in self.bound)

    def free_spans(self, max_len: int = 6) -> tuple[Span, ...]:
        """Mọi span CỰC ĐẠI chưa bị claim, dài trước — ứng viên của W18."""
        free: list[Span] = []
        run: list[Token] = []
        for token in self.tokens:
            if token.is_punct or self.claimed(token.index, token.index + 1):
                if run:
                    free.extend(_subspans(run, max_len))
                    run = []
                continue
            run.append(token)
        if run:
            free.extend(_subspans(run, max_len))
        return tuple(sorted(free, key=lambda s: (-len(s), s.start)))

    def refs(self) -> tuple[str, ...]:
        return tuple(item.ref for item in self.bound if item.ref)

    def digest(self) -> dict[str, Any]:
        """Khối telemetry bắt buộc (W16 §3.5)."""
        kinds: dict[str, int] = {}
        for item in self.residual:
            kinds[item.kind] = kinds.get(item.kind, 0) + 1
        producers: dict[str, int] = {}
        for item in self.bound:
            producers[item.producer] = producers.get(item.producer, 0) + 1
        return {
            "coverage": round(self.coverage(), 4),
            "residual_kinds": kinds,
            "claims_by_producer": producers,
        }


def _subspans(run: list[Token], max_len: int) -> list[Span]:
    out: list[Span] = []
    for size in range(min(max_len, len(run)), 0, -1):
        for i in range(len(run) - size + 1):
            window = run[i:i + size]
            out.append(Span(
                start=window[0].index,
                end=window[-1].index + 1,
                normalized=" ".join(t.normalized for t in window),
                raw=" ".join(t.raw for t in window),
            ))
    return out


def tokenize(raw_question: str) -> tuple[Token, ...]:
    """Cắt câu thành token, GIỮ offset về câu gốc (LUẬT W16-R1)."""
    quoted_ranges = _quoted_ranges(raw_question)
    tokens: list[Token] = []
    previous_ends_sentence = True          # token đầu tiên luôn đứng đầu câu
    for index, match in enumerate(_TOKEN_RE.finditer(raw_question)):
        raw = match.group(0)
        start, end = match.start(), match.end()
        tokens.append(Token(
            index=index,
            normalized=fold(raw),
            raw=raw,
            char_start=start,
            char_end=end,
            capitalized=bool(raw[:1].isupper()),
            quoted=any(lo <= start and end <= hi for lo, hi in quoted_ranges),
            numeric=raw[:1].isdigit(),
            sentence_initial=previous_ends_sentence,
        ))
        # Token kế tiếp đứng đầu câu khi phần văn bản trước nó kết thúc bằng một
        # dấu chấm câu. Tính từ CHUỖI GỐC chứ không từ token, vì "." và "!" không
        # phải token (chúng không nằm trong _CLAUSE_PUNCT).
        previous_ends_sentence = bool(_SENTENCE_END.search(raw_question[:end]))
    return tuple(tokens)


def _quoted_ranges(text: str) -> list[tuple[int, int]]:
    """Khoảng ký tự nằm giữa một cặp ngoặc. Ngoặc lẻ ⇒ bỏ qua, không đoán."""
    ranges: list[tuple[int, int]] = []
    open_at: int | None = None
    for i, ch in enumerate(text):
        if ch not in _QUOTE_CHARS:
            continue
        if open_at is None:
            open_at = i + 1
        else:
            ranges.append((open_at, i))
            open_at = None
    return ranges


def span_of(tokens: tuple[Token, ...], start: int, end: int) -> Span:
    window = tokens[start:end]
    return Span(
        start=start, end=end,
        normalized=" ".join(t.normalized for t in window),
        raw=" ".join(t.raw for t in window),
    )


def classify_residual(token: Token, ledger_tokens: tuple[Token, ...]) -> ResidualSpan:
    """LUẬT W16-R4 — phân loại phần dư là hàm TOÀN PHẦN.

    Mỗi token không được claim nhận ĐÚNG MỘT loại. Không có nhánh "bỏ qua":
    ``unknown_concept`` là đáy, và đó là loại làm W22 hỏi lại.
    """
    span = span_of(ledger_tokens, token.index, token.index + 1)
    if is_function_word(token.normalized):
        return ResidualSpan(span, "function_word", ("registry từ chức năng",))
    # TỪ VỰNG ĐÃ BIẾT thắng HEURISTIC HÌNH DẠNG. "SKU" viết hoa giữa câu có hình
    # dạng một tên riêng, nhưng nó là một grain hệ biết và đã khai là không có.
    # Xếp nó thành proper_name sẽ đẩy nó sang W19 ("giá trị này có trong dữ liệu
    # không?") thay vì W22 ("dataset không có grain này") — sai lớp, sai lời
    # khuyên. Hình dạng chỉ là bằng chứng khi không có gì tốt hơn.
    if token.normalized in _GRAIN_TERMS:
        return ResidualSpan(span, "grain_term", ("từ nêu grain",))
    if token.normalized in _MAGNITUDE_TERMS:
        return ResidualSpan(span, "magnitude_claim", ("cụm chỉ độ lớn",))
    if token.name_shaped:
        return ResidualSpan(
            span, "proper_name",
            ("quoted" if token.quoted else "capitalized giữa câu",),
        )
    if token.numeric or _DATE_LIKE.match(token.normalized):
        return ResidualSpan(span, "date_like", ("hình dạng ngày/số",))
    return ResidualSpan(span, "unknown_concept", ("không alias nào phủ",))


@dataclass
class LedgerBuilder:
    """Bộ dựng: mọi binder CLAIM span trên cùng một lattice.

    LUẬT W16-R2 — một token chỉ được claim MỘT lần, span dài thắng span ngắn.
    Đây chính là luật ``residual`` đang nằm trong ``AliasIndex.find_in``; ở đây
    nó được nâng từ mẹo riêng của một binder thành tính chất của lattice.
    """

    raw_question: str
    tokens: tuple[Token, ...] = field(default_factory=tuple)
    _bound: list[BoundSpan] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.tokens:
            self.tokens = tokenize(self.raw_question)

    def is_free(self, start: int, end: int) -> bool:
        probe = Span(start, end, "", "")
        return not any(item.span.overlaps(probe) for item in self._bound)

    def claim(
        self, start: int, end: int, producer: Producer,
        ref: str | None = None, payload: Any = None,
    ) -> BoundSpan | None:
        """Nhận span nếu nó còn tự do. Trả ``None`` khi đã bị chiếm."""
        if start >= end or end > len(self.tokens) or not self.is_free(start, end):
            return None
        bound = BoundSpan(span_of(self.tokens, start, end), producer, ref, payload)
        self._bound.append(bound)
        return bound

    def find_free(
        self, surface_normalized: str, avoid: frozenset[int] = frozenset(),
    ) -> tuple[int, int] | None:
        """Vị trí token đầu tiên khớp NGUYÊN CỤM ``surface`` và còn tự do.

        ``avoid`` là các chỉ số token KHÔNG được nhận — dùng cho vùng trong
        ngoặc kép. Ưu tiên vị trí ngoài vùng cấm, và chỉ lùi về vị trí trong
        vùng cấm khi không còn lựa chọn nào khác: bỏ hẳn thì một câu chỉ nêu tên
        nước bên trong tên riêng sẽ mất luôn thị trường, và mất một ràng buộc
        tệ hơn là gán nó vào chỗ hơi lệch.
        """
        want = surface_normalized.split()
        if not want:
            return None
        size = len(want)
        fallback: tuple[int, int] | None = None
        for i in range(len(self.tokens) - size + 1):
            window = self.tokens[i:i + size]
            if [t.normalized for t in window] != want:
                continue
            if not self.is_free(i, i + size):
                continue
            if any(index in avoid for index in range(i, i + size)):
                fallback = fallback or (i, i + size)
                continue
            return i, i + size
        return fallback

    def build(self) -> BindingLedger:
        bound = tuple(sorted(self._bound, key=lambda b: b.span.start))
        residual = tuple(
            classify_residual(token, self.tokens)
            for token in self.tokens
            if not token.is_punct and self.is_free(token.index, token.index + 1)
        )
        return BindingLedger(
            tokens=self.tokens, bound=bound, residual=residual,
            raw_question=self.raw_question,
        )
