"""Vòng W — sửa CÂU CHỮ thay vì bỏ cả câu trả lời (Spec2308 §A5.3).

Chỉ chạy khi cả bốn điều đúng: verification hỏng, nhưng answer alignment và
question alignment đều PASS. Nghĩa là **số đúng, evidence khớp, chỉ câu chữ
sai** — đúng lớp lỗi đã đo được: tên listing chứa chữ số
(``"... Cream 30 Gr"``) bị ``verifier.scan_numbers`` chấm là số bịa, và 21/60
case của suite legacy rơi từ 1.0 xuống 0.65 vì nó.

Hai bước, dừng ngay khi bước đầu đủ. Không có lần thử thứ ba, và **không gọi
LLM ở bất kỳ bước nào** — vòng này chỉ được *bớt* chữ hoặc *miễn trừ* span đã
có nguyên văn trong evidence (A5-R2).
"""
from __future__ import annotations

import re

from gladiators.contracts import Evidence, ResponseClaim

# Ít hơn hai từ thì "span" chỉ còn chính con số, và miễn trừ nó là miễn trừ
# đúng thứ verifier sinh ra để bắt.
MIN_SPAN_WORDS = 2

_WORD = re.compile(r"\S+")


def _evidence_strings(evidence: list[Evidence]) -> tuple[str, ...]:
    """Mọi chuỗi mà evidence này thực sự mang theo, phẳng hoá một lớp.

    ``Evidence`` là bất biến (bất biến hệ thống #4) nên đây chỉ đọc, không copy
    và không sửa.
    """
    found: list[str] = []
    for item in evidence:
        if isinstance(item.value, str) and item.value.strip():
            found.append(item.value)
        for value in item.attrs.values():
            if isinstance(value, str) and value.strip():
                found.append(value)
            elif isinstance(value, (list, tuple)):
                found.extend(
                    entry for entry in value
                    if isinstance(entry, str) and entry.strip()
                )
    return tuple(dict.fromkeys(found))


def quotable_spans(
    answer: str, evidence: list[Evidence], unsupported: list[float],
) -> tuple[str, ...]:
    """Span trong answer chứa một số chưa khớp evidence, VÀ có nguyên văn trong evidence.

    A5-R3: khớp **nguyên văn**, không so gần đúng, không cắt bớt. Một span gần
    giống được miễn trừ là đúng cách biến vòng sửa câu chữ thành một lỗ hổng cho
    số bịa đi qua.

    Chiều so sánh ở đây là chiều mà verifier **không** che được: verifier xoá
    chuỗi evidence khỏi answer, nên nó chỉ giúp khi evidence là chuỗi NGẮN HƠN
    hoặc bằng đoạn in ra. Khi answer chỉ in một phần của tên dài trong evidence
    ("Serum Vitamin C 30ml" từ "Serum Vitamin C 30ml - Chính hãng"), phép xoá đó
    không khớp gì cả và chữ số trong tên sống sót thành claim bịa.
    """
    if not unsupported:
        return ()
    haystack = _evidence_strings(evidence)
    if not haystack:
        return ()

    words = [(match.group(), match.start(), match.end()) for match in _WORD.finditer(answer)]
    wanted = {_number_text(value) for value in unsupported}
    spans: list[str] = []
    for index, (word, _, _) in enumerate(words):
        if not any(token in word for token in wanted):
            continue
        # Dài trước: một span dài khớp nguyên văn là bằng chứng mạnh hơn hẳn một
        # span ngắn, và miễn trừ span dài che ít số ngoài ý muốn hơn.
        best: str | None = None
        for start in range(0, index + 1):
            for end in range(len(words), index, -1):
                if end - start < MIN_SPAN_WORDS:
                    continue
                span = answer[words[start][1]:words[end - 1][2]]
                if any(span in text for text in haystack):
                    if best is None or len(span) > len(best):
                        best = span
        if best is not None:
            spans.append(best)
    return tuple(dict.fromkeys(spans))


def _number_text(value: float) -> str:
    """Chữ số như nó xuất hiện trong văn bản, không phải như float in ra."""
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def strict_answer(
    evidence: list[Evidence], claims: tuple[ResponseClaim, ...],
) -> str:
    """Bước 2: khuôn chặt nhất — mỗi claim đúng một dòng ``giá trị đơn vị [id]``.

    KHÔNG echo tên listing, KHÔNG câu dẫn, KHÔNG số nào ngoài claim. Đây là lý do
    nó qua được verifier ở chỗ câu văn đầy đủ không qua: nó không còn chữ nào có
    thể chứa một chữ số không có evidence.
    """
    by_id = {item.evidence_id: item for item in evidence}
    lines: list[str] = []
    for claim in claims:
        item = by_id.get(claim.evidence_id)
        # Claim trỏ tới evidence không có mặt là một claim không in được — bỏ nó
        # chứ không in giá trị trần: một con số không kèm citation là đúng thứ
        # verifier tồn tại để chặn.
        if item is None or isinstance(item.value, str):
            continue
        unit = f" {item.unit}" if item.unit else ""
        lines.append(f"{item.value}{unit} [{item.evidence_id}]")
    if not lines:
        # Không claim số nào in được ⇒ không có gì để cứu. Trả rỗng để caller
        # rơi về A-VERIFICATION-FINAL, thay vì in một câu trống rỗng nghe như
        # một câu trả lời.
        return ""
    return "\n".join(lines)
