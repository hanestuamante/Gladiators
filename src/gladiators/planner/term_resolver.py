"""LLM ánh xạ CHỮ vào kho từ vựng đóng — đề xuất, không quyết định.

Vì sao tầng này tồn tại
=======================

CLAUDE.md §3.1 nói thẳng: *"ánh xạ chữ→ký hiệu là chỗ hỏng, không phải phần suy
luận"*. Đo được, mọi lỗi tìm ra trong phiên 31/08 đều nằm đúng ở biên đó —
``mặt hàng`` không map được trong khi ``sản phẩm`` map được, ``tổng số`` bị đọc
thành phép cộng, câu tiếng Anh bị gán nhãn ``vi`` nên số nhiều không rút được.
Không lỗi nào ở tầng suy luận.

Nên vai trò của LLM ở đây HẸP và khác hẳn ``parse_intent``: nó **không** đoán
intent, **không** sinh plan, **không** tính số. Nó nhận đúng những cụm mà binder
tất định bỏ lại, cùng một DANH SÁCH ĐÓNG các ref hợp lệ, và trả về ánh xạ.

Vì sao hình dạng này an toàn
============================

Không phải vì prompt viết khéo — mà vì output **kiểm lại được trên tập đóng**:

    ref LLM trả về  ∈ danh sách đã gửi  ⇒ nhận
    ngược lại                            ⇒ vứt, hệ quay về hành vi cũ (clarify)

Một ref bịa không thể đi tới plan, và điều đó đúng theo cấu trúc chứ không theo
lời hứa. Cùng khuôn với ``plan_analytical`` → ``validator`` đã chạy từ trước.

Rủi ro CÒN LẠI, và nó không nằm ở đây
=====================================

Ref **có thật nhưng sai nghĩa** (map ``nhãn hàng`` → ``entity.shop``) đi qua được
cửa này. Nó bị chặn ở A22: một ref không khớp câu hỏi thì alignment bắt, y như
nó đang bắt mọi thứ khác. Tầng này KHÔNG cố tự bắt lỗi đó — thêm một phép kiểm
ngữ nghĩa thứ hai ở đây là dựng bản sao thứ hai của A22, và hai bản của một luật
là cách chúng lệch nhau.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

# Kiểu residual ĐÁNG hỏi. ``function_word`` là hư từ — hỏi LLM "của" nghĩa là gì
# thì tốn một lượt gọi để nhận lại một câu trả lời vô nghĩa.
RESOLVABLE_KINDS = frozenset({"unknown_concept", "grain_term"})


class TermProposer(Protocol):
    """Thứ duy nhất tầng này cần từ một LLM client."""

    def resolve_terms(self, payload: dict) -> dict: ...


@dataclass
class TermResolution:
    """Kết quả MỘT lượt phân giải, kèm đủ số liệu để kiểm lại sau khi chạy.

    Mọi khoá ở đây là khoá telemetry theo §0.3: một nhánh không đếm được số lần
    bắn thì "đã đo" và "đã chạy" không phân biệt được — và WP-A11 đã cho thấy một
    nhánh chết vẫn trông như một nhánh hoà.
    """

    accepted: dict[str, str] = field(default_factory=dict)
    rejected: dict[str, str] = field(default_factory=dict)
    asked: tuple[str, ...] = ()
    called: bool = False
    failed: str | None = None

    def as_attrs(self) -> dict[str, object]:
        return {
            "llm_terms_called": self.called,
            "llm_terms_asked": len(self.asked),
            "llm_terms_accepted": len(self.accepted),
            "llm_terms_rejected": len(self.rejected),
            "llm_terms_map": dict(self.accepted),
            **({"llm_terms_failed": self.failed} if self.failed else {}),
        }


def candidate_refs(kinds: frozenset[str]) -> dict[str, tuple[str, ...]]:
    """``{ref: aliases}`` của các ``kind`` được nêu — chính là danh sách gửi đi.

    Toàn bộ catalog chỉ ~9,5 KB; lát ``entity`` + ``dimension`` là ~1,5 KB. Gửi
    cả kho vẫn rẻ, nhưng gửi đúng lát thì prompt nhỏ hơn và cơ hội chọn nhầm một
    ref thuộc loại khác cũng biến mất — đó là cách rẻ nhất để thu hẹp lỗi.
    """
    from gladiators.domain.catalog import CATALOG

    return {
        ref: obj.aliases
        for ref, obj in CATALOG.items()
        if obj.kind in kinds and obj.aliases
    }


def resolve_terms(
    spans: tuple[str, ...],
    kinds: frozenset[str],
    proposer: TermProposer | Callable[[dict], dict] | None,
    *,
    language: str = "vi",
    question: str = "",
) -> TermResolution:
    """Ánh xạ ``spans`` vào ref hợp lệ. Không có proposer ⇒ không làm gì.

    Vắng LLM là trạng thái MẶC ĐỊNH và nó phải im lặng đi qua: đường tất định
    trả lời được 87% câu ở 56 ms, và tầng này chỉ tồn tại cho phần còn lại.
    """
    if not spans or proposer is None:
        return TermResolution(asked=tuple(spans))

    allowed = candidate_refs(kinds)
    if not allowed:
        return TermResolution(asked=tuple(spans))

    payload = {
        # CẢ CÂU, không chỉ các cụm đã tách. Bộ tách cắt theo phần dư của
        # lattice, và nó cắt cụt: "điểm sao" gửi đi thành "Điểm", "số lượt tim"
        # thành "lượt" — model nhận một mảnh không đủ nghĩa rồi trả null, và nó
        # làm đúng. Câu đầy đủ cho nó ngữ cảnh mà bộ tách không có cách nào
        # truyền lại được.
        #
        # Hợp đồng RA không đổi: model vẫn chỉ được chọn ref trong `vocabulary`,
        # và mọi ref vẫn bị kiểm lại bên dưới. Chỉ ĐẦU VÀO rộng ra.
        "question": question or " ".join(spans),
        "spans": list(spans),
        "language": language,
        # Danh sách ĐÓNG. Prompt nói rõ chỉ được chọn trong đây; phép kiểm bên
        # dưới không tin lời nói đó.
        "vocabulary": {ref: list(aliases) for ref, aliases in allowed.items()},
    }
    call = getattr(proposer, "resolve_terms", proposer)
    try:
        raw = call(payload)
    except Exception as exc:                      # noqa: BLE001 — lỗi LLM là một
        # kết cục bình thường, không phải một sự kiện ngoại lệ: hệ quay về đúng
        # hành vi khi không có LLM, và ghi lại LOẠI lỗi để đếm được.
        return TermResolution(asked=tuple(spans), called=True,
                              failed=type(exc).__name__)

    mapping = (raw or {}).get("mapping") if isinstance(raw, dict) else None
    if not isinstance(mapping, dict):
        return TermResolution(asked=tuple(spans), called=True, failed="shape")

    # Cụm chỉ PHÉP TÍNH, không phải chỉ số. Đưa cả câu cho model thì nó cũng ánh
    # xạ luôn "trung vị" → `derived.median_monthly_sold`, và request có HAI
    # measure ⇒ `measure_count_not_one` ⇒ A19-PLAN. Bốn câu đo được hỏng đúng
    # vì lý do này trong khi cụm chính đã map ĐÚNG ("Tiền hàng" → measure.price,
    # "Chiết khấu" → measure.discount_percent).
    #
    # Phép tính đã có đường riêng (`_detect_requested_aggregation`) và nó chạy
    # tất định; để LLM nói thêm một lần nữa là để hai bộ máy cùng trả lời một
    # câu hỏi rồi chồng lên nhau.
    aggregation_words = {
        "trung vi", "trung binh", "binh quan", "tong", "tong cong", "median",
        "mean", "average", "sum", "total", "cao nhat", "thap nhat", "lon nhat",
        "nho nhat", "max", "min", "toi da", "toi thieu",
    }

    def _is_aggregation_phrase(phrase: str) -> bool:
        import unicodedata

        folded = "".join(
            c for c in unicodedata.normalize("NFD", phrase.lower())
            if unicodedata.category(c) != "Mn"
        ).replace("đ", "d").strip()
        return folded in aggregation_words

    # Ánh xạ được nhận phải nói về CỤM ĐÃ HỎI. Đưa cả câu cho model thì nó cũng
    # ánh xạ những cụm khác trong câu, và một trong số đó đủ để câu trở nên trả
    # lời được TRONG KHI cụm gây ra lượt hỏi vẫn chưa hiểu.
    #
    # Đo được: "Cái xí xổn ở VN có bao nhiêu?" — hỏi vì "xí xổn" không bind
    # được; model bỏ qua nó, map "bao nhiêu" → derived.product_count, và hệ trả
    # "Có 672 listing" cho một câu hỏi về một thứ nó không hiểu. Tắt LLM thì
    # câu này `clarify`. Đó là over-answer, và over_answer_rate phải giữ 0.0 ở
    # MỌI mốc — nên luật này là điều kiện để tầng LLM được phép tồn tại.
    #
    # Trùng theo TOKEN, không theo chuỗi bằng nhau: bộ tách cắt cụt, nên cụm
    # đúng thường DÀI HƠN cụm đã hỏi ("Điểm" → "Điểm sao", "lượt" → "Số lượt
    # tim"). Đòi bằng nhau là dựng lại chính rào cản vừa gỡ.
    asked_tokens = {
        tok for span in spans for tok in span.lower().split() if tok
    }

    def _talks_about_asked(phrase: str) -> bool:
        return bool(asked_tokens & {t for t in phrase.lower().split() if t})

    accepted: dict[str, str] = {}
    rejected: dict[str, str] = {}
    for span, ref in mapping.items():
        if isinstance(span, str) and _is_aggregation_phrase(span):
            continue
        if isinstance(span, str) and not _talks_about_asked(span):
            continue
        if not isinstance(span, str) or not span.strip():
            continue
        # KHÔNG còn đòi cụm phải nằm trong `spans`: model nay đọc cả câu và tự
        # chỉ ra cụm nào mang khái niệm. Ràng buộc thật vẫn nguyên và nó nằm ở
        # dòng dưới — ref phải có trong danh sách đã gửi.
        if ref is None or ref == "":
            continue                              # "không biết" là câu trả lời hợp lệ
        if isinstance(ref, str) and ref in allowed:
            accepted[span] = ref
        else:
            rejected[span] = str(ref)
    return TermResolution(
        accepted=accepted, rejected=rejected, asked=tuple(spans), called=True,
    )
