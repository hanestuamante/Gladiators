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


def _strip_diacritics(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")


def _fold(value: str) -> str:
    return _strip_diacritics(value.lower().replace("đ", "d"))


# Mệnh đề phủ định: từ negation tới hết cụm (chặn ở dấu câu). Quét trên bản CÒN
# DẤU (chỉ lowercase), dùng negator có dấu — nếu quét sau khi bỏ dấu thì đại từ
# "nó"/"nò" và động từ "nốt" bị fold thành "no"/"not" rồi scrub oan cả mệnh đề
# nhân quả phía sau, làm thủng causal-claim gate (bug 22/07).
_NEGATION = re.compile(r"\b(?:không|chưa|not|no)\b[^.;:\n]{0,90}")

# (rule, các cụm bị cấm — viết KHÔNG DẤU vì so khớp trên văn bản đã fold)
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("causal_language", (
        "gay ra", "lam tang", "lam giam", "khien", "nho voucher", "nho khuyen mai",
        "nho chien dich", "do chien dich", "boi chien dich", "keo theo", "dan den",
        "vi vay gia", "tac dong lam", "hieu qua ro ret", "chung minh hieu qua",
        "cho thay hieu qua",
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

# §4.7 jargon blacklist. Internal vocabulary that is meaningful in a trace and
# meaningless to a user: naming an "expected_cardinality" or an "A22" rule in a
# sentence tells them nothing they can act on, and a raw exception tells them
# about our stack rather than their question. Rule ids stay available in the
# trace and in machine-facing API fields -- this only governs the prose.
JARGON_LEXICON_VERSION = "jargon.v1"
_JARGON_TERMS: tuple[str, ...] = (
    "artifact", "monthly_sold_proxy", "semantic catalog", "expected_cardinality",
    "analytical template", "logicalqueryplan", "analyticalrequest",
    "requestdigest", "plan_hash", "semantic_ref", "catalog slice",
    "validation error", "traceback", "pydantic", "stacktrace",
)
# Rule ids: A19-*, A22-*, A14-*, A16-* ... spoken at the user is an internal code.
_RULE_ID = re.compile(r"\bA\d{2}[-\w]*\b")


def check_wording(answer: str) -> list[dict[str, str]]:
    """Trả danh sách violation; rỗng = answer qua gate."""
    lowered = answer.lower().replace("đ", "d")
    folded = _strip_diacritics(lowered)
    # Scrub negation trên bản còn dấu, rồi mới bỏ dấu để so khớp rule term.
    scrubbed = _strip_diacritics(_NEGATION.sub(" ", lowered))
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
    violations.extend(check_jargon(answer))
    return violations


def check_jargon(answer: str) -> list[dict[str, str]]:
    """§4.7 jargon lint, applied to *every* answer, generated or templated.

    Deliberately separate from the causal/forecast rules above: those only apply
    to LLM prose because certified templates are reviewed, whereas jargon can
    leak from a template just as easily -- a formatter that interpolates a rule
    id or an exception is exactly how internals reach a UI.
    """
    folded = _fold(answer)
    violations = [
        {"rule": "jargon", "term": term}
        for term in _JARGON_TERMS if term in folded
    ]
    violations.extend(
        {"rule": "internal_rule_id", "term": match}
        for match in dict.fromkeys(_RULE_ID.findall(answer))
    )
    return violations
