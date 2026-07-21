"""Deterministic wording gate — tập con quy tắc V2 mục 11.3, negation-aware.

Numeric verifier chỉ chặn SỐ bịa; lớp này chặn KẾT LUẬN bịa: câu chữ nhân quả,
forecast, khẳng định cùng-SKU, hoặc gọi revenue proxy như doanh thu thật. Đây là
regex thuần (không LLM) đúng cơ chế enforce V2 chỉ định; chỉ áp lên answer do LLM
sinh — deterministic template đã được review theo contract.

Negation handling: mệnh đề phủ định ("không chứng minh ... gây ra ...") bị loại
khỏi vùng quét trước khi so khớp, để các caveat chuẩn của chính hệ thống không bị
chặn oan.
"""
from __future__ import annotations

import re
import unicodedata


def _fold(value: str) -> str:
    value = value.lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")


# Mệnh đề phủ định: từ negation tới hết cụm (chặn ở dấu câu) — quét trên bản đã bỏ dấu.
_NEGATION = re.compile(r"\b(?:khong|chua|not|no)\b[^.;:\n]{0,90}")

# (rule, các cụm bị cấm — viết KHÔNG DẤU vì so khớp trên văn bản đã fold)
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("causal_language", (
        "gay ra", "lam tang", "lam giam", "khien", "nho voucher", "nho khuyen mai",
        "tac dong lam", "hieu qua ro ret", "chung minh hieu qua", "cho thay hieu qua",
    )),
    ("same_sku_claim", (
        "cung mau", "cung sku", "chinh xac cung loai", "exact same model", "same sku",
    )),
    ("forecast_claim", (
        "du bao", "se tang", "se giam", "thang sau se", "forecast", "du doan doanh",
    )),
)

# Các cụm yêu cầu nhãn bắt buộc đi kèm (V2 rule 2: revenue proxy luôn kèm "ước tính").
_REVENUE_TERMS = ("doanh thu", "revenue", "pendapatan")
_ESTIMATE_LABELS = ("uoc tinh", "proxy", "estimated")


def check_wording(answer: str) -> list[dict[str, str]]:
    """Trả danh sách violation; rỗng = answer qua gate."""
    folded = _fold(answer)
    scrubbed = _NEGATION.sub(" ", folded)
    violations = [
        {"rule": rule, "term": term}
        for rule, terms in _RULES
        for term in terms
        if term in scrubbed
    ]
    if any(term in folded for term in _REVENUE_TERMS) and not any(
        label in folded for label in _ESTIMATE_LABELS
    ):
        violations.append({"rule": "revenue_missing_estimate_label", "term": "doanh thu/revenue"})
    return violations
