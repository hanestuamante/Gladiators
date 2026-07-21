"""Numeric claim verifier — answer-wide scan (V2 mục 9.2 Pass 1 + display-rounding).

Ba bảo đảm của lớp này:

1. **Display-rounding tolerance** thay cho relative tolerance lỏng: một số hiển thị
   ``d`` chữ số thập phân chỉ pass khi ``|shown − true| ≤ 0.5 × 10^(−d)`` (làm tròn
   đúng vẫn là trung thực; 750 không được phép khớp 745.078 như tolerance 1,1% cũ).
2. **Citation validation**: mọi token ``[ev:...]`` trong answer phải trỏ về một
   evidence_id thật của request — LLM bịa citation là fail, không phải cảnh cáo.
3. **String evidence values** (tên shop, ngày, tên sản phẩm) được loại khỏi vùng
   scan giống ``attrs`` — chữ số bên trong giá trị evidence dạng chuỗi không bị
   chấm nhầm thành "số bịa".

Fail ở bất kỳ điều nào ⇒ ``passed=False`` — caller (workflow) retry một lần rồi
rơi về deterministic answer; verifier không bao giờ tự sửa số (V2 mục 9.3).
"""
from __future__ import annotations

import math
import re

from gladiators.contracts import Evidence

NUMBER = re.compile(r"(?<![\w-])-?\d+(?:[.,]\d+)?%?")
CITATION = re.compile(r"\[(ev:[^\[\]\s]+)\]")


def scan_numbers(text: str) -> list[float]:
    return [value for value, _ in scan_number_tokens(text)]


def scan_number_tokens(text: str) -> list[tuple[float, int]]:
    """Trả ``(giá trị, số chữ số thập phân hiển thị)`` cho từng numeric occurrence."""
    tokens: list[tuple[float, int]] = []
    for token in NUMBER.findall(text):
        token = token.rstrip("%").replace(",", ".")
        decimals = len(token.rsplit(".", 1)[1]) if "." in token else 0
        tokens.append((float(token), decimals))
    return tokens


def _display_match(claimed: float, decimals: int, allowed: float) -> bool:
    tolerance = max(0.5 * 10 ** (-decimals), 1e-9 * max(1.0, abs(allowed)))
    return math.isclose(claimed, allowed, rel_tol=0.0, abs_tol=tolerance)


def verify_numeric_claims(text: str, evidence: list[Evidence], tolerance: float | None = None) -> dict:
    known_ids = {item.evidence_id for item in evidence}
    unknown_citations = sorted({c for c in CITATION.findall(text) if c not in known_ids})

    metric_text = text
    for evidence_id in known_ids:
        metric_text = metric_text.replace(evidence_id, "")
    # Mọi citation token (kể cả token lạ) được loại khỏi vùng scan số để không sinh
    # nhiễu số kép; bản thân token lạ đã fail qua unknown_citations.
    metric_text = CITATION.sub(" ", metric_text)

    ignored_strings: list[str] = []
    for item in evidence:
        if isinstance(item.value, str) and item.value:
            ignored_strings.append(item.value)
        for value in item.attrs.values():
            if isinstance(value, str) and value:
                ignored_strings.append(value)
    for value in sorted(set(ignored_strings), key=len, reverse=True):
        metric_text = metric_text.replace(value, "")

    claimed_tokens = scan_number_tokens(metric_text)
    claimed = [value for value, _ in claimed_tokens]
    allowed = [float(e.value) for e in evidence if isinstance(e.value, (int, float)) and not isinstance(e.value, bool)]

    if tolerance is not None:
        # Escape hatch tương thích cũ: caller truyền tolerance thì dùng isclose legacy.
        unsupported = [n for n, _ in claimed_tokens
                       if not any(math.isclose(n, a, rel_tol=tolerance, abs_tol=tolerance) for a in allowed)]
    else:
        unsupported = [n for n, d in claimed_tokens if not any(_display_match(n, d, a) for a in allowed)]

    passed = not unsupported and not unknown_citations
    return {
        "passed": passed,
        "claimed": claimed,
        "allowed": allowed,
        "unsupported": unsupported,
        "unknown_citations": unknown_citations,
        "coverage": 1.0 if not claimed else (len(claimed) - len(unsupported)) / len(claimed),
    }
