"""Vòng W — Spec2308 §A5.3.

Ranh giới phải giữ: một câu trả lời có SỐ ĐÚNG nhưng câu chữ chứa tên có chữ số
phải được cứu; một câu trả lời chứa một số KHÔNG có trong evidence phải chết như
cũ. Nới quá tay ở đây là mở đúng cánh cửa mà verifier sinh ra để đóng.
"""
from __future__ import annotations

import gladiators.agent.workflow  # noqa: F401  (khép vòng import, xem test_context_relax)
from gladiators.contracts import Evidence, ResponseClaim, SourceLocator
from gladiators.agent.wording_repair import quotable_spans, strict_answer


def _evidence(value, *, metric="median_price", unit="VND", name=None, eid="ev:t:0001"):
    attrs = {"country": "vn"}
    if name is not None:
        attrs["listing_name"] = name
    return Evidence(
        evidence_id=eid, metric=metric, value=value, unit=unit,
        source_tier="btc_dataset",
        source_locator=SourceLocator(kind="internal", value="compiled_semantic_plan"),
        source_path="result.value", dataset_version="test",
        attrs=attrs,
    )


def test_a_name_with_digits_quoted_from_evidence_is_exempted():
    """Tên listing in ra từ evidence được miễn — kể cả khi answer in NGẮN HƠN.

    Đây là chiều verifier không tự che được: nó xoá chuỗi evidence khỏi answer,
    nên khi answer chỉ in một phần của tên dài, phép xoá không khớp gì cả.
    """
    evidence = [_evidence(120000.0, name="Serum Vitamin C 30ml - Chính hãng")]
    answer = "Sản phẩm Serum Vitamin C 30ml có giá trung vị 120000 VND [ev:t:0001]."
    spans = quotable_spans(answer, evidence, [30.0])
    assert spans, "span có nguyên văn trong evidence phải được miễn trừ"
    assert any("Serum Vitamin C 30ml" in span for span in spans)


def test_a_number_absent_from_evidence_is_never_exempted():
    """A5-R3: không có nguyên văn trong evidence ⇒ không miễn, dù câu nghe hợp lý."""
    evidence = [_evidence(120000.0, name="Serum Vitamin C 30ml")]
    answer = "Giá trung vị 120000 VND, tăng khoảng 47 phần trăm [ev:t:0001]."
    assert quotable_spans(answer, evidence, [47.0]) == ()


def test_a_single_digit_alone_is_not_a_span():
    """Span dưới hai từ chỉ còn chính con số — miễn nó là vô hiệu hoá verifier."""
    evidence = [_evidence(120000.0, name="30")]
    answer = "Kết quả 30 [ev:t:0001]."
    assert quotable_spans(answer, evidence, [30.0]) == ()


def test_strict_template_prints_only_value_unit_and_citation():
    """Bước 2 chỉ được BỚT chữ (A5-R2): không câu dẫn, không tên, không số lạ."""
    evidence = [_evidence(120000.0, name="Serum Vitamin C 30ml")]
    claims = (ResponseClaim(
        claim_id="cl:median_price", text="giá trung vị", claim_type="money",
        value=120000.0, unit="VND",
        evidence_id="ev:t:0001", evidence_path="result.value",
    ),)
    assert strict_answer(evidence, claims) == "120000.0 VND [ev:t:0001]"


def test_strict_template_returns_empty_when_nothing_numeric_survives():
    """Không claim số nào in được ⇒ trả rỗng, để caller rơi về A-VERIFICATION-FINAL.

    In một câu trống rỗng ở đây nghe như một câu trả lời, và đó là cách tệ nhất
    để thất bại.
    """
    assert strict_answer([], ()) == ""
