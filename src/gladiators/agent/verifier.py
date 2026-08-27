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
from typing import Any

from gladiators.contracts import Evidence, ResponseClaim

NUMBER = re.compile(r"(?<![\w-])-?\d+(?:[.,]\d+)?%?")
CITATION = re.compile(r"\[(ev:[^\[\]\s]+)\]")
# ≥2 lần lặp nhóm-3-chữ-số mới coi là thousands grouping (vd "298,219,517,806"
# hay "298 219 517 806" — narrow no-break space đã được normalize về space đơn).
# Separator PHẢI đúng 1 ký tự: "298, 219, 517" (comma+space) là danh sách số rời,
# KHÔNG phải một số — nếu cho 2 ký tự sẽ gộp oan list "512, 431, 380" thành số bịa.
# Chỉ 1 lần lặp ("745.078") vẫn mơ hồ với số thập phân nên KHÔNG gộp.
_THOUSANDS_GROUP = re.compile(r"(?<![\w.,])\d{1,3}(?:[,.\s]\d{3}){2,}(?!\d)")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATE_LITERAL = re.compile(r"(?<!\d)\d{4}[-/.]\d{2}[-/.]\d{2}(?!\d)")
# LLM đôi khi sinh dấu gạch nối/khoảng trắng kiểu "typographic" (non-breaking
# hyphen, narrow no-break space...) thay vì ASCII thường — cùng giá trị hiển
# thị nhưng lệch ký tự khiến so khớp chuỗi/ghép nhóm-nghìn thất bại.
_UNICODE_DASHES = "".join(chr(c) for c in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2212))
_UNICODE_SPACES = "".join(chr(c) for c in (0x00A0, 0x2007, 0x2009, 0x202F))


def _normalize_unicode_punctuation(text: str) -> str:
    for ch in _UNICODE_DASHES:
        text = text.replace(ch, "-")
    for ch in _UNICODE_SPACES:
        text = text.replace(ch, " ")
    return text


def _normalize_thousands_grouping(text: str) -> str:
    """Gộp cụm số bị dấu phân cách nghìn tách thành nhiều token rời (V2 §13.7
    locale normalization) thành một số liền để không bị chấm nhầm là "số bịa"."""
    return _THOUSANDS_GROUP.sub(lambda m: re.sub(r"[,.\s]", "", m.group(0)), text)


def _date_variants(value: str) -> list[str]:
    """ISO date evidence value có thể bị LLM viết lại với dấu phân cách khác
    (2026/07/03, 2026.07.03) — vẫn là cùng một giá trị, không phải số bịa."""
    if not _ISO_DATE.match(value):
        return [value]
    return [value, value.replace("-", "/"), value.replace("-", ".")]


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


def _tier_mixing(text: str, evidence: list[Evidence]) -> list[dict[str, Any]]:
    """A20-TIER: one textual claim or derived evidence cannot bind >1 tier."""
    by_id = {item.evidence_id: item for item in evidence}
    violations: list[dict[str, Any]] = []
    # Newline and sentence punctuation form conservative claim boundaries. A
    # Sources block should list each evidence item on its own line.
    segments = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
    for index, segment in enumerate(segments):
        ids = tuple(dict.fromkeys(CITATION.findall(segment)))
        tiers = sorted({by_id[eid].source_tier for eid in ids if eid in by_id})
        if len(tiers) > 1:
            violations.append({"kind": "claim", "segment": index, "evidence_ids": ids, "tiers": tiers})

    for item in evidence:
        if not item.parent_evidence_ids:
            continue
        parent_tiers = sorted({
            by_id[parent].source_tier for parent in item.parent_evidence_ids if parent in by_id
        })
        if len(parent_tiers) > 1:
            violations.append({
                "kind": "derived_evidence", "evidence_id": item.evidence_id,
                "parent_evidence_ids": item.parent_evidence_ids, "tiers": parent_tiers,
            })
    return violations



# WP-A12.2 — ba khối tách bạch. Chính sự tách bạch là điểm ăn tiền: người đọc
# phải biết ngay con số nào truy vết được và con số nào chỉ là bối cảnh.
BLOCK_HEADINGS: tuple[tuple[str, str], ...] = (
    ("internal", "SỐ LIỆU NỘI BỘ"),
    ("context", "NGỮ CẢNH THỊ TRƯỜNG"),
    ("action", "ĐỀ XUẤT HÀNH ĐỘNG"),
)

# Đề xuất chỉ dựa vào khối 2 phải nói THẲNG điều đó. Không có câu này, một gợi ý
# rút ra từ một bài báo trông giống hệt một gợi ý rút ra từ dữ liệu đã kiểm.
UNVERIFIED_DISCLAIMER = "chưa kiểm chứng bằng dữ liệu nội bộ"


def split_blocks(text: str) -> dict[str, str]:
    """Cắt câu trả lời theo tiêu đề khối. Không có tiêu đề ⇒ dict rỗng.

    Rỗng chứ không phải "tất cả là khối 1": một câu trả lời không khai khối nào
    thì luật ba khối không áp cho nó, và đoán hộ nó thuộc khối nào là dựng ra một
    ranh giới mà tác giả chưa từng vẽ.
    """
    positions: list[tuple[int, str]] = []
    upper = text.upper()
    for name, heading in BLOCK_HEADINGS:
        found = upper.find(heading)
        if found >= 0:
            # Lùi về ĐẦU DÒNG. Cắt ngay tại chữ tiêu đề để lại tiền tố
            # "KHỐI 2 · " nằm trong khối trước, và chữ số 2 ở đó bị đọc thành một
            # con số của khối trước — tức luật tự tạo ra vi phạm nó đi bắt.
            positions.append((text.rfind("\n", 0, found) + 1, name))
    if len(positions) < 2:
        return {}
    positions.sort()
    blocks: dict[str, str] = {}
    for index, (start, name) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(text)
        blocks[name] = text[start:end]
    return blocks


def _block_rules(text: str, evidence: list[Evidence]) -> list[dict[str, Any]]:
    """Ba luật của §A12.2, kiểm bằng máy.

    Luật 1 là ``A20-TIER`` nhìn ở mức KHỐI thay vì mức câu: ``_tier_mixing`` cắt
    theo dấu câu và newline, nên nó bắt được một câu trộn hai tier, nhưng không
    bắt được một con số của khối 2 bị chép sang khối 1.
    """
    blocks = split_blocks(text)
    if not blocks:
        return []
    violations: list[dict[str, Any]] = []

    external_ids = {
        item.evidence_id for item in evidence if item.source_tier != "btc_dataset"
    }
    internal = blocks.get("internal", "")
    if external_ids and any(eid in internal for eid in external_ids):
        violations.append({"rule": "external_citation_in_internal_block"})

    context_numbers = set(scan_numbers(blocks.get("context", "")))
    internal_numbers = set(scan_numbers(internal))
    shared = context_numbers & internal_numbers
    # Số của khối 2 xuất hiện lại trong khối 1 nghĩa là một con số ngoài đã được
    # trình bày như một con số nội bộ — dù nó đến đó bằng đường nào.
    if shared:
        violations.append({
            "rule": "context_number_reused_in_internal_block",
            "numbers": sorted(shared),
        })

    action = blocks.get("action", "")
    # "Chỉ dựa vào khối 2" đo bằng việc khối 1 KHÔNG mang con số hay citation nào.
    # Đo bằng ``internal.strip()`` là sai: chuỗi đó luôn còn dòng tiêu đề, nên
    # luật sẽ không bao giờ bắn.
    internal_body = "\n".join(internal.splitlines()[1:])
    internal_backed = bool(scan_numbers(internal_body) or CITATION.findall(internal_body))
    if action and "context" in blocks and not internal_backed:
        if UNVERIFIED_DISCLAIMER not in action.lower():
            violations.append({"rule": "action_block_missing_disclaimer"})
    return violations


def _provenance_gaps(evidence: list[Evidence]) -> list[dict[str, str]]:
    """A21-PROV: every non-internal record must carry matching provenance."""
    gaps: list[dict[str, str]] = []
    for item in evidence:
        if item.source_tier == "btc_dataset":
            if item.provenance is not None:
                gaps.append({"evidence_id": item.evidence_id, "reason": "unexpected_external_provenance"})
            continue
        if item.provenance is None:
            gaps.append({"evidence_id": item.evidence_id, "reason": "missing_provenance"})
        elif item.provenance.source_tier != item.source_tier:
            gaps.append({"evidence_id": item.evidence_id, "reason": "tier_mismatch"})
        elif item.provenance.source_id == "live_web_search":
            required = {
                "provider": item.provenance.provider,
                "search_query": item.provenance.search_query,
                "result_rank": item.provenance.result_rank,
                "source_spans": item.provenance.source_spans,
            }
            for field, value in required.items():
                if value is None or value == ():
                    gaps.append({"evidence_id": item.evidence_id, "reason": f"missing_{field}"})
    return gaps


def _source_label_gaps(text: str, evidence: list[Evidence]) -> list[dict[str, str]]:
    """V2 11.3.10: external claims require source and retrieval-time labels."""
    gaps: list[dict[str, str]] = []
    segments = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
    for item in evidence:
        if item.source_tier == "btc_dataset" or item.provenance is None:
            continue
        cited = [segment for segment in segments if f"[{item.evidence_id}]" in segment]
        retrieved = item.provenance.retrieved_at.isoformat()
        labelled = any(
            "[nguồn:" in segment.lower()
            and item.provenance.source_id.lower() in segment.lower()
            and (retrieved in segment or retrieved[:10] in segment)
            for segment in cited
        )
        if not labelled:
            gaps.append({"evidence_id": item.evidence_id, "reason": "missing_inline_source_or_retrieved_at"})
        if item.provenance.mapping_status == "needs_review" and "chưa xác nhận cùng sản phẩm/thực thể" not in text.lower():
            gaps.append({"evidence_id": item.evidence_id, "reason": "missing_needs_review_label"})
    return gaps


def _resolve_path(item: Evidence, path: str) -> tuple[bool, Any]:
    current: Any = item
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return False, None
            current = current[part]
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return False, None
    return True, current


def _claim_value_matches(claimed: Any, actual: Any) -> bool:
    if isinstance(claimed, bool) or isinstance(actual, bool):
        return claimed is actual
    if isinstance(claimed, (int, float)) and isinstance(actual, (int, float)):
        shown = str(claimed)
        decimals = len(shown.rsplit(".", 1)[1]) if "." in shown else 0
        return _display_match(float(claimed), decimals, float(actual))
    left = _normalize_unicode_punctuation(str(claimed)).strip()
    right = _normalize_unicode_punctuation(str(actual)).strip()
    return left in _date_variants(right)


def _claim_value_is_displayed(claim: ResponseClaim) -> bool:
    text = _normalize_thousands_grouping(_normalize_unicode_punctuation(claim.text))
    if isinstance(claim.value, (int, float)) and not isinstance(claim.value, bool):
        return any(_display_match(value, decimals, float(claim.value)) for value, decimals in scan_number_tokens(text))
    value = _normalize_unicode_punctuation(str(claim.value))
    return any(variant in text for variant in _date_variants(value))


def _claim_binding_gaps(
    text: str, evidence: list[Evidence], claims: tuple[ResponseClaim, ...], *, require_claims: bool,
) -> list[dict[str, str]]:
    by_id = {item.evidence_id: item for item in evidence}
    gaps: list[dict[str, str]] = []
    seen: set[str] = set()
    for claim in claims:
        item = by_id.get(claim.evidence_id)
        if item is None:
            gaps.append({"claim_id": claim.claim_id, "reason": "unknown_evidence_id"})
            continue
        seen.add(item.evidence_id)
        if claim.text not in text:
            gaps.append({"claim_id": claim.claim_id, "reason": "claim_text_not_in_answer"})
        if f"[{item.evidence_id}]" not in claim.text:
            gaps.append({"claim_id": claim.claim_id, "reason": "missing_bound_citation"})
        if claim.evidence_path not in item.claimable_paths:
            gaps.append({"claim_id": claim.claim_id, "reason": "path_not_claimable"})
            continue
        found, actual = _resolve_path(item, claim.evidence_path)
        if not found:
            gaps.append({"claim_id": claim.claim_id, "reason": "path_not_found"})
            continue
        if not _claim_value_matches(claim.value, actual):
            gaps.append({"claim_id": claim.claim_id, "reason": "value_mismatch"})
        expected_unit = item.unit if claim.evidence_path == "value" else None
        if (claim.unit or None) != (expected_unit or None):
            gaps.append({"claim_id": claim.claim_id, "reason": "unit_mismatch"})
        if not _claim_value_is_displayed(claim):
            gaps.append({"claim_id": claim.claim_id, "reason": "value_not_in_claim_text"})
    if require_claims:
        required = {
            item.evidence_id for item in evidence
            if item.source_tier != "btc_dataset"
            or isinstance(item.value, (int, float)) and not isinstance(item.value, bool)
            or isinstance(item.value, str) and bool(re.search(r"\d", item.value))
        }
        for evidence_id in sorted(required - seen):
            gaps.append({"claim_id": "", "reason": f"missing_claim:{evidence_id}"})
    return gaps



def _caveat_clauses(caveat: str) -> list[str]:
    """Mệnh đề dùng được của một caveat đã khai.

    Bỏ mệnh đề có chữ số: chúng không bao giờ được phép xuất hiện trong câu trả
    lời, nên đòi chúng là đòi một điều bất khả. Bỏ mệnh đề quá ngắn: một cụm ba
    chữ khớp ngẫu nhiên thì phép kiểm không còn nghĩa.
    """
    parts = re.split(r"[—;(),]", caveat or "")
    return [
        clause for clause in (part.strip() for part in parts)
        if len(clause.split()) >= 4 and not any(char.isdigit() for char in clause)
    ]


def _lineage_gaps(
    text: str, evidence: list[Evidence], claims: tuple[ResponseClaim, ...],
) -> list[dict[str, object]]:
    """WP-A9 — chỉ số DẪN XUẤT phải kèm evidence tổ tiên, hoặc caveat đã khai.

    ``MetricGraph`` biết ``derived.estimated_recent_revenue`` dựng trên những gì.
    Verifier trước đây chỉ hỏi "số này có evidence không", không hỏi "cái nó dựng
    TRÊN có không" — nên một số dẫn xuất được trình bày y hệt một số đo trực tiếp.

    Hoặc đưa đủ evidence tổ tiên, hoặc nói rõ đây là số dẫn xuất kèm đúng caveat
    đã khai ở ``MetricSpec.caveats``. Không có đường thứ ba.
    """
    from gladiators.domain.metrics import METRICS, build_metric_graph

    graph = build_metric_graph(METRICS)
    by_id = {item.evidence_id: item for item in evidence}
    # A9-R3: tier ngoài đã có A20-TIER / A21-PROV lo.
    present = {
        item.metric for item in evidence if item.source_tier == "btc_dataset"
    }
    gaps: list[dict[str, object]] = []
    seen: set[str] = set()
    for claim in claims:
        item = by_id.get(claim.evidence_id)
        if item is None or item.source_tier != "btc_dataset":
            continue
        metric = item.metric
        if metric in seen or metric not in graph.specs:
            continue
        seen.add(metric)
        ancestors = graph.ancestors(metric)
        if not ancestors:
            continue
        # Cờ boolean (`unit == "bool"`) là VỊ TỪ mà chỉ số dẫn xuất tính trên,
        # không phải một đại lượng được hiển thị. Đòi một dòng Evidence cho
        # `has_structured_voucher` cạnh `voucher_rate` là đòi bằng chứng cho
        # một thứ không ai đọc. Phân biệt này lấy từ metadata ĐÃ KHAI, không
        # phải từ khoá tự nghĩ (A9-R2).
        missing = [
            name for name in ancestors
            if name not in present
            and graph.specs[name].unit != "bool"
        ]
        if not missing:
            continue
        # A9-R2: đối chiếu theo caveat text ĐÃ KHAI, không bằng từ khoá tự nghĩ.
        #
        # So nguyên văn cả chuỗi thì quá giòn: caveat của `similarity_score` là
        # "'tương tự' theo thành phần điểm — không khẳng định cùng mẫu (không có
        # nhãn same-product)", còn câu trả lời viết "không khẳng định cùng mẫu
        # hoặc cùng SKU" — cùng nội dung, khác cách ghép câu. Và nhiều caveat
        # mang CHỮ SỐ ("1580/1580 dòng True..."), mà một câu trả lời chứa số
        # không có evidence sẽ bị chính verifier này chấm là số bịa (§3.1).
        #
        # Nên khớp theo MỆNH ĐỀ của caveat đã khai: vẫn là text đã khai, chỉ bỏ
        # phần không thể xuất hiện hợp lệ.
        if any(
            clause in text
            for _, caveat in graph.effective_caveats(metric)
            for clause in _caveat_clauses(caveat)
        ):
            continue
        gaps.append({
            "kind": "lineage", "metric": metric,
            "missing_ancestors": sorted(missing),
        })
    return gaps


def verify_numeric_claims(
    text: str, evidence: list[Evidence], tolerance: float | None = None,
    *, claims: tuple[ResponseClaim, ...] = (), require_claims: bool = False,
    ignore_texts: tuple[str, ...] = (),
) -> dict:
    """``ignore_texts`` are spans quoted back from the dataset, not claims.

    An ambiguity shortlist has to echo listing names so the user can choose, and
    those names contain digits ("... Cleanser 100ml", "... Cream 30 Gr"). With no
    evidence attached -- a clarify carries none -- every such digit scanned as an
    unsupported number and failed the answer. Measured on the legacy suite that
    was 21 of 60 cases: end-to-end accuracy 0.65 while trajectory, evidence,
    citation and routing all stayed at 1.0, i.e. the answers were right and the
    checker was wrong.
    """
    known_ids = {item.evidence_id for item in evidence}
    unknown_citations = sorted({c for c in CITATION.findall(text) if c not in known_ids})

    metric_text = _normalize_unicode_punctuation(text)
    for evidence_id in known_ids:
        metric_text = metric_text.replace(evidence_id, "")
    # Mọi citation token (kể cả token lạ) được loại khỏi vùng scan số để không sinh
    # nhiễu số kép; bản thân token lạ đã fail qua unknown_citations.
    metric_text = CITATION.sub(" ", metric_text)

    # Normalised the same way as the text they are masked out of. The scan runs
    # on unicode-normalised text, so a name carrying an en dash ("Hair Mask
    # 150ml – Masker") no longer matched itself and its digits survived as an
    # unsupported claim.
    ignored_strings: list[str] = [
        _normalize_unicode_punctuation(t) for t in ignore_texts if t
    ]
    for item in evidence:
        if isinstance(item.value, str) and item.value:
            ignored_strings.extend(_date_variants(item.value))
        for value in item.attrs.values():
            if isinstance(value, str) and value:
                ignored_strings.extend(_date_variants(value))
        if item.provenance is not None:
            ignored_strings.extend((
                item.provenance.source_id,
                item.provenance.content_hash,
                item.provenance.license,
                item.provenance.observed_at.isoformat(),
                item.provenance.retrieved_at.isoformat(),
                item.provenance.observed_at.date().isoformat(),
                item.provenance.retrieved_at.date().isoformat(),
                item.provenance.source_locator.value,
            ))
            if item.provenance.provider:
                ignored_strings.append(item.provenance.provider)
            if item.provenance.search_query:
                ignored_strings.append(item.provenance.search_query)
    for value in sorted(set(ignored_strings), key=len, reverse=True):
        metric_text = metric_text.replace(value, "")

    # An ISO date is a date, not a measurement. Left in, the scanner read the
    # year out of "2026-07-02" and reported 2026 as an unsupported claim -- and
    # it was not even checking the date, just its first four digits. Date scope
    # is checked by A22-ALIGN-DATE, which compares whole dates against the digest.
    metric_text = _ISO_DATE_LITERAL.sub(" ", metric_text)
    metric_text = _normalize_thousands_grouping(metric_text)
    claimed_tokens = scan_number_tokens(metric_text)
    claimed = [value for value, _ in claimed_tokens]
    allowed = [float(e.value) for e in evidence if isinstance(e.value, (int, float)) and not isinstance(e.value, bool)]
    for item in evidence:
        for key in ("result_count", "returned_rows", "row_limit"):
            value = item.attrs.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                allowed.append(float(value))

    if tolerance is not None:
        # Escape hatch tương thích cũ: caller truyền tolerance thì dùng isclose legacy.
        unsupported = [n for n, _ in claimed_tokens
                       if not any(math.isclose(n, a, rel_tol=tolerance, abs_tol=tolerance) for a in allowed)]
    else:
        unsupported = [n for n, d in claimed_tokens if not any(_display_match(n, d, a) for a in allowed)]

    tier_mixing = _tier_mixing(text, evidence)
    # A12.2 luật 1: ranh giới KHỐI, bổ sung cho ranh giới câu ở trên.
    tier_mixing.extend(_block_rules(text, evidence))
    provenance_gaps = _provenance_gaps(evidence)
    source_label_gaps = _source_label_gaps(text, evidence)
    claim_binding_gaps = _claim_binding_gaps(
        text, evidence, claims, require_claims=require_claims,
    )
    lineage_gaps = _lineage_gaps(text, evidence, claims)
    passed = (
        not unsupported and not unknown_citations and not tier_mixing
        and not provenance_gaps and not source_label_gaps and not claim_binding_gaps
        and not lineage_gaps
    )
    return {
        "passed": passed,
        "claimed": claimed,
        "allowed": allowed,
        "unsupported": unsupported,
        "unknown_citations": unknown_citations,
        "tier_mixing": tier_mixing,
        "provenance_gaps": provenance_gaps,
        "source_label_gaps": source_label_gaps,
        "claim_binding_gaps": claim_binding_gaps,
        "lineage_gaps": lineage_gaps,
        "coverage": 1.0 if not claimed else (len(claimed) - len(unsupported)) / len(claimed),
    }
