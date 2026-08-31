"""W32 — LLM đề xuất ánh xạ chữ→ref, validator tất định quyết định.

Bốn luật ở đây đều sinh ra từ hành vi ĐO ĐƯỢC của model thật (deepseek,
31/08), không từ suy đoán về prompt:

* ref bịa bị vứt — cửa an toàn duy nhất của tầng này;
* cụm KHÔNG cần nằm trong ``spans`` — bộ tách cắt cụt ("điểm sao" → "Điểm"),
  nên đòi khớp span là đòi model lặp lại một mảnh hỏng;
* cụm chỉ phép tính bị bỏ — model map luôn "trung vị" thành một measure, và
  request hai measure thì rơi ``A19-PLAN``;
* không có proposer thì im lặng đi qua — vắng LLM là trạng thái mặc định.
"""
from __future__ import annotations

from gladiators.planner.term_resolver import RESOLVABLE_KINDS, resolve_terms

KINDS = frozenset({"entity", "measure", "dimension", "derived_metric"})


def test_ref_ngoai_danh_sach_bi_vut():
    out = resolve_terms(
        ("gian buôn",), KINDS,
        lambda payload: {"mapping": {"gian buôn": "entity.khong_ton_tai"}},
    )
    assert out.accepted == {}
    assert out.rejected == {"gian buôn": "entity.khong_ton_tai"}


def test_cum_ngoai_spans_van_duoc_nhan():
    # Bộ tách gửi "Điểm"; model đọc cả câu và trả về "Điểm sao". Cụm dài hơn là
    # cụm ĐÚNG — vứt nó đi là giữ lại đúng lỗi mà tầng này sinh ra để sửa.
    out = resolve_terms(
        ("Điểm",), KINDS,
        lambda payload: {"mapping": {"Điểm sao": "measure.rating"}},
        question="Điểm sao trung bình của listing VN ngày 21/7 là bao nhiêu?",
    )
    assert out.accepted == {"Điểm sao": "measure.rating"}


def test_ca_cau_duoc_gui_di():
    seen: dict = {}
    resolve_terms(("Điểm",), KINDS, lambda p: seen.update(p) or {"mapping": {}},
                  question="Điểm sao của listing VN")
    assert seen["question"] == "Điểm sao của listing VN"


def test_cum_chi_phep_tinh_bi_bo():
    out = resolve_terms(
        ("Tiền hàng",), KINDS,
        lambda payload: {"mapping": {
            "Tiền hàng": "measure.price",
            "trung vị": "derived.median_monthly_sold",   # phép tính, không phải chỉ số
        }},
        question="Tiền hàng trung vị của listing VN ngày 21/7",
    )
    assert out.accepted == {"Tiền hàng": "measure.price"}


def test_khong_co_proposer_thi_khong_lam_gi():
    out = resolve_terms(("gian buôn",), KINDS, None)
    assert out.called is False and out.accepted == {}


def test_loi_llm_khong_thoat_ra_ngoai():
    def no(payload):
        raise TimeoutError("mạng")

    out = resolve_terms(("gian buôn",), KINDS, no)
    assert out.called is True and out.failed == "TimeoutError" and out.accepted == {}


def test_hu_tu_khong_nam_trong_kind_duoc_hoi():
    assert "function_word" not in RESOLVABLE_KINDS


def test_so_do_phan_biet_duoc_ba_trang_thai():
    """Rỗng mang hai nghĩa; nếu chúng trông giống nhau thì nhánh này không đo được.

    WP-A11 đã mắc đúng lỗi đó: một nhánh chết trả `no_change` cho mọi câu và
    tám test cô lập đều xanh, vì không khoá nào đếm số lần nó thật sự bắn.
    """
    from gladiators.planner.semantic_parser import DeterministicSemanticParser

    khong = DeterministicSemanticParser().parse("gian buôn nào ở VN", "vi", "vn")
    assert khong.llm_terms == {}                      # chưa từng hỏi

    rong = DeterministicSemanticParser(
        term_proposer=lambda payload: {"mapping": {}},
    ).parse("gian buôn nào ở VN", "vi", "vn")
    assert rong.llm_terms["llm_terms_called"] is True  # đã hỏi, model không biết
    assert rong.llm_terms["llm_terms_accepted"] == 0

    trung = DeterministicSemanticParser(
        term_proposer=lambda payload: {"mapping": {"gian buôn": "entity.shop"}},
    ).parse("có bao nhiêu gian buôn ở VN", "vi", "vn")
    assert trung.llm_terms["llm_terms_map"] == {"gian buôn": "entity.shop"}
