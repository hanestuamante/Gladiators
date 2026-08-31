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

    accepted: dict[str, str] = {}
    rejected: dict[str, str] = {}
    for span, ref in mapping.items():
        if not isinstance(span, str) or span not in spans:
            continue                              # cụm không hỏi thì không nhận
        if ref is None or ref == "":
            continue                              # "không biết" là câu trả lời hợp lệ
        if isinstance(ref, str) and ref in allowed:
            accepted[span] = ref
        else:
            rejected[span] = str(ref)
    return TermResolution(
        accepted=accepted, rejected=rejected, asked=tuple(spans), called=True,
    )
