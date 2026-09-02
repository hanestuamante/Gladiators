"""Nạp lại lời hỏi cho LLM, để nó SỬA câu hỏi — đề xuất, không quyết định.

Vì sao tầng này tồn tại
=======================

Hệ đã biết đủ để tự sửa mà không sửa. Câu *"shop Richy ở VN bán được doanh thu
bao nhiêu ngày 3/7"* bị từ chối kèm một lời nói rõ:

    Câu hỏi nêu "shop" nhưng "Richy" không phải tên shop. Các shop chứa cụm
    đó: "Richy - Chi Nhánh Miền Bắc", "Richy - Chi nhánh Miền Nam".

Danh sách đó lấy thẳng từ chỉ mục giá trị. Người dùng đọc xong sẽ gõ lại một
trong hai tên — và đó chính xác là một việc NGÔN NGỮ trên một TẬP ĐÓNG, tức
đúng hình dạng mà W32 đã giải: LLM đề xuất, hệ tất định định đoạt.

Vì sao hình dạng này an toàn
============================

Danh sách ứng viên **do dữ liệu sinh ra**, không do LLM nghĩ ra. Model chỉ chọn
một phần tử, và phép kiểm không tin lời nó:

    tên LLM trả về  ∈ danh sách ứng viên  ⇒ nhận, thay vào câu, chạy LẠI
    ngược lại                              ⇒ vứt, giữ nguyên lời từ chối

Chạy lại là một lượt ``AgentRuntime.run`` bình thường trên một câu hỏi khác, nên
nó mang theo nguyên gate, plan, verifier. Không lớp kiểm nào bị bỏ qua chỉ vì
câu hỏi được một máy viết lại.

Điều tầng này KHÔNG làm
=======================

Nó **không** chọn khi chỉ có một ứng viên và cũng **không** chọn khi có nhiều mà
model im lặng — hai trường hợp đó giữ nguyên lời hỏi lại. Một ứng viên duy nhất
nghe như hiển nhiên, nhưng "Bibica" → "Bibica Official Store" vẫn là một quyết
định về Ý ĐỊNH của người hỏi, và hệ này không đoán ý.

Sửa đúng MỘT lần. Câu đã sửa mà vẫn bị từ chối thì lời từ chối đó là câu trả
lời — sửa vòng hai là bắt đầu một cây tìm kiếm không có đáy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


class RepairProposer(Protocol):
    def repair_question(self, payload: dict) -> dict: ...


@dataclass
class Repair:
    """Một lượt sửa, kèm đủ số đo để đếm được nhánh đã bắn."""

    question: str | None = None
    chosen: str | None = None
    candidates: tuple[str, ...] = ()
    called: bool = False
    rejected: str | None = None
    failed: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def as_attrs(self) -> dict[str, Any]:
        return {
            "llm_repair_called": self.called,
            "llm_repair_candidates": len(self.candidates),
            "llm_repair_chosen": self.chosen,
            **({"llm_repair_rejected": self.rejected} if self.rejected else {}),
            **({"llm_repair_failed": self.failed} if self.failed else {}),
        }


def candidates_for(question: str, country: str | None) -> tuple[str, str, tuple[str, ...]]:
    """``(cụm đơn vị, giá trị sai, ứng viên)`` cho một câu bị lệch chiều đơn vị.

    Dùng CHUNG phép phát hiện với parser (``unit_value_mismatch``) thay vì dựng
    một bản thứ hai: bản thứ hai sẽ lệch, và cái lệch ở đây im lặng — bước sửa
    nhắm vào một mismatch mà parser không thấy, hoặc ngược lại.
    """
    import re

    from gladiators.domain.catalog import CATALOG, VALUE_DIMENSION_BY_UNIT

    from .semantic_parser import (
        DeterministicSemanticParser,
        _partial_values,
        normalize,
    )

    # Hỏi một câu KHÁC với guard trong parser, và đó là chủ đích. Guard hỏi
    # "một bộ lọc có rơi vào sai chiều không" — nhưng nó ĐÃ GỠ bộ lọc đó ra
    # khỏi request, nên parse lại thì không còn gì để thấy. Ở đây câu hỏi là
    # "người dùng gõ gì ngay sau chữ `shop`", và câu trả lời nằm trong chính
    # câu hỏi, không phụ thuộc guard đã làm gì.
    request = DeterministicSemanticParser().parse(question, "vi", country)
    normalized = request.normalized_question
    for unit_ref, dim_ref in VALUE_DIMENSION_BY_UNIT.items():
        obj = CATALOG.get(unit_ref)
        if obj is None:
            continue
        for alias in obj.aliases:
            match = re.search(
                rf"(?<![a-z]){re.escape(normalize(alias))}\s+(.+)", normalized,
            )
            if match is None:
                continue
            tokens = match.group(1).split()
            # Cụm DÀI trước: "richy mien nam" trước "richy". Cụm dài khớp được
            # thì nó là cụm người dùng thật sự nêu.
            for size in range(min(5, len(tokens)), 0, -1):
                probe = " ".join(tokens[:size])
                near = _partial_values(probe, dim_ref, country)
                if near:
                    return alias, probe, tuple(near)
    return "", "", ()


def repair(
    question: str,
    country: str | None,
    proposer: RepairProposer | Callable[[dict], dict] | None,
) -> Repair:
    """Câu hỏi đã sửa, hoặc rỗng. Không có proposer ⇒ không làm gì."""
    if proposer is None:
        return Repair()
    said, literal, candidates = candidates_for(question, country)
    if len(candidates) < 2:
        # Không có gì để chọn, hoặc chỉ một — xem docstring: một ứng viên duy
        # nhất vẫn là một quyết định về ý định người hỏi.
        return Repair(candidates=candidates)

    payload = {
        "question": question,
        "problem": f'"{literal}" không phải tên {said}',
        # Danh sách ĐÓNG, do dữ liệu sinh ra. Prompt nói rõ chỉ được chọn trong
        # đây; phép kiểm bên dưới không tin lời đó.
        "candidates": list(candidates),
    }
    call = getattr(proposer, "repair_question", proposer)
    try:
        raw = call(payload)
    except Exception as exc:                       # noqa: BLE001 — lỗi LLM là
        return Repair(candidates=candidates, called=True,
                      failed=type(exc).__name__)
    if not isinstance(raw, dict):
        return Repair(candidates=candidates, called=True, failed="shape")
    chosen = raw.get("chosen")
    if chosen is None or chosen == "":
        # "Không chắc" là một câu trả lời hợp lệ: lời hỏi lại giữ nguyên.
        return Repair(candidates=candidates, called=True)
    if not isinstance(chosen, str) or chosen not in candidates:
        return Repair(candidates=candidates, called=True, rejected=str(chosen))
    return Repair(
        question=_substitute(question, literal, chosen),
        chosen=chosen, candidates=candidates, called=True,
    )


def _substitute(question: str, literal: str, chosen: str) -> str:
    """Thay giá trị sai bằng tên đầy đủ, ĐẶT TRONG NGOẶC KÉP.

    Không phân biệt hoa thường: `literal` đến từ chuỗi ĐÃ CHUẨN HOÁ ("richy")
    còn câu gốc viết "Richy". Bản đầu so nguyên văn nên phép thay im lặng không
    xảy ra — câu "sửa xong" giống hệt câu cũ và chạy lại cho đúng lời từ chối cũ.

    Ngoặc kép không phải trang trí: nó là cách người dùng nói "đọc nguyên văn",
    và tên shop chứa từ của chính catalog ("Official", "Chính hãng") thì thiếu
    nó sẽ bị bộ ghép alias xé nhỏ — lớp lỗi đã đo ở 2f9ccc2.
    """
    import re as _re

    from .semantic_parser import normalize

    pattern = _re.compile(
        r"(?<!\w)" + _re.escape(literal) + r"(?!\w)", _re.IGNORECASE,
    )
    match = pattern.search(question)
    if match is None:
        return question
    # NUỐT LUÔN phần mô tả kế tiếp đã nằm trong tên được chọn. Người dùng gõ
    # "shop Richy mien Nam"; thay mỗi "Richy" thì còn lại
    # `shop "Richy - Chi nhánh Miền Nam" mien Nam` — phần thừa đó không sai
    # nghĩa nhưng nó là chữ dư đi vào parser, và chữ dư là thứ sinh ra phần dư
    # chưa bind.
    folded_choice = normalize(chosen)
    tail = question[match.end():]
    consumed = 0
    for token in tail.split():
        if normalize(token) and normalize(token) in folded_choice:
            consumed = tail.index(token) + len(token)
            continue
        break
    return (
        question[:match.start()] + f'"{chosen}"' + tail[consumed:]
    )
