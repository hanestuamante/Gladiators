"""Bẻ câu bằng LLM — kiểm phần TẤT ĐỊNH, không kiểm model.

Ranh giới cần chốt ở đây chỉ có hai: đề xuất nào bị vứt, và kết luận nào không
được rút. Chất lượng của việc bẻ là chuyện đo trên câu hỏi thật, không phải
chuyện khẳng định bằng test.
"""
from __future__ import annotations

from gladiators.planner.question_split import (
    COMBINE_OPS,
    MAX_STEPS,
    StepResult,
    combine_results,
    dataset_brief,
    propose_steps,
)


def _step(question, value, *, answered=True, rule_id=None):
    return StepResult(
        question=question,
        action="allow" if answered else "abstain",
        rule_id=rule_id,
        value=value,
        evidence_id="ev:test:0001" if answered else None,
    )


# ── Đề xuất: cái gì bị vứt ───────────────────────────────────────────────────

def test_toan_tu_gop_ngoai_tap_dong_bi_vut():
    """"maximum" KHÔNG được suy thành "argmax".

    Suy một chuỗi tự do về một toán tử gần đúng là để model quyết định cách rút
    kết luận, tức đúng thứ tập đóng sinh ra để chặn.
    """
    steps, combine, failed = propose_steps(
        "ngày nào doanh thu cao nhất",
        lambda payload: {"steps": ["a", "b"], "combine": "maximum"},
    )
    assert (steps, combine, failed) == ((), None, "bad_combine")


def test_khong_co_proposer_thi_khong_lam_gi():
    assert propose_steps("bất kỳ", None) == ((), None, None)


def test_loi_llm_khong_thoat_ra_ngoai():
    def no(payload):
        raise TimeoutError("mạng")

    steps, combine, failed = propose_steps("bất kỳ", no)
    assert (steps, combine, failed) == ((), None, "TimeoutError")


def test_so_buoc_bi_chan_tran():
    steps, _, _ = propose_steps(
        "bất kỳ",
        lambda payload: {"steps": [f"q{i}" for i in range(200)],
                         "combine": "list"},
    )
    assert len(steps) == MAX_STEPS


def test_moi_toan_tu_khai_bao_deu_gop_duoc():
    """Ba nơi phải khớp: tập đóng, luật gộp, và cái gộp thật sự làm được.

    Một toán tử có trong `COMBINE_OPS` mà `combine_results` không xử lý sẽ đi
    qua mọi phép kiểm hình dạng rồi chết ở lượt chạy thật.
    """
    results = (_step("a", 1), _step("b", 2))
    for op in COMBINE_OPS:
        conclusion, declined = combine_results(results, op)
        assert (conclusion is None) != (declined is None), op
        assert conclusion is not None, op


# ── Gộp: kết luận nào KHÔNG được rút ─────────────────────────────────────────

def test_argmax_tu_choi_khi_con_buoc_khong_tra_loi_duoc():
    """Bất biến chính của tầng này, và nó đến từ một ca thật.

    "ngày nào cửa hàng Richy miền Nam có doanh thu cao nhất" bẻ ra 20 câu con,
    nhưng doanh thu chỉ quan sát được 6/20 ngày. Lấy max trên 20 kết quả trong
    đó 14 rỗng trả về 21/07 — có evidence, trôi chảy, và nói về ngày dữ liệu
    tồn tại chứ không phải ngày bán chạy.
    """
    results = (
        _step("ngày 03/07", 1_544_400),
        _step("ngày 04/07", None, answered=False, rule_id="A19-PLAN"),
        _step("ngày 21/07", 4_094_222_300),
    )
    conclusion, declined = combine_results(results, "argmax")
    assert conclusion is None
    assert declined is not None and "1/3" in declined


def test_argmax_khong_dien_0_cho_buoc_rong():
    """Điền 0 làm "không đo được" trông giống hệt "đo được và bằng 0"."""
    results = (_step("ngày 01/07", None, answered=False), _step("ngày 21/07", 5))
    conclusion, _ = combine_results(results, "argmax")
    assert conclusion is None


def test_list_van_ke_lai_buoc_hong():
    """`list` kể lại từng bước, nên bước hỏng là một dòng chứ không phải một
    lý do dừng — hình dạng của nó không rút kết luận xuyên qua các bước."""
    results = (_step("ngày 01/07", None, answered=False, rule_id="A19-PLAN"),
               _step("ngày 21/07", 5))
    conclusion, declined = combine_results(results, "list")
    assert declined is None
    assert "không trả lời được (A19-PLAN)" in conclusion
    assert "5" in conclusion


def test_argmax_giu_nguyen_evidence_cua_buoc_thang():
    results = (_step("ngày 03/07", 10), _step("ngày 21/07", 99))
    conclusion, _ = combine_results(results, "argmax")
    assert "ngày 21/07" in conclusion and "99" in conclusion
    assert "ev:test:0001" in conclusion


def test_bool_khong_phai_mot_con_so_so_sanh_duoc():
    """`isinstance(True, int)` là True, và một cờ đem so lớn-nhỏ là vô nghĩa."""
    results = (_step("có voucher không", True), _step("có voucher không", False))
    conclusion, declined = combine_results(results, "argmax")
    assert conclusion is None and declined is not None


# ── Bức tranh dữ liệu ────────────────────────────────────────────────────────

def test_ban_mo_ta_sinh_tu_du_lieu_khong_viet_tay():
    """Bản mô tả nói về BẢN ĐANG ĐỌC, không về một bản được nhớ trong đầu.

    Cố ý KHÔNG khẳng định cột nào thưa: bộ kiểm ghim vào bộ đóng băng 3 ngày,
    nơi `monthly_sold` được quan sát mỗi đợt thu và do đó KHÔNG thưa; ở bộ 20
    ngày đang phục vụ thì nó thưa (5,3%). Một test viết cứng tên cột sẽ xanh
    trên một bản và đỏ trên bản kia trong khi code vẫn đúng — nó đo bản dữ liệu
    chứ không đo hàm.
    """
    brief = dataset_brief()
    if not brief:                      # artifact vắng là trạng thái ĐƯỢC KHAI
        return
    assert brief["dates"], "phải nêu được các ngày có trong bản đang phục vụ"
    assert brief["dataset_version"], "phải nêu bản nào đang được mô tả"
    assert all(
        0.0 <= coverage < 0.5 for coverage in brief["sparse_columns"].values()
    ), brief["sparse_columns"]


def test_ban_mo_ta_vang_artifact_thi_rong_chu_khong_no():
    assert dataset_brief("khong/ton/tai.json") == {}


def test_sum_khong_duoc_cong_qua_nhieu_ngay():
    """Con số ĐÚNG SỐ HỌC mà SAI CÂU HỎI — lớp lỗi nguy hiểm nhất ở đây.

    Đo được: "Có bao nhiêu listing ở VN từ 1/7 đến 5/7" bẻ ra 5 bước, mỗi bước
    trả đúng số ngày mình (581, 670, 668, 684, 680), `sum` ra 3283. Cộng đúng.
    Nhưng đáp án của chính câu đó là 701 — số listing PHÂN BIỆT trong cửa sổ.
    3283 đếm mỗi listing một lần cho mỗi ngày nó xuất hiện, và mang đủ năm
    evidence id để trông như đã được kiểm.
    """
    results = tuple(
        _step(f"Số listing tại VN ngày 0{day}/07 là bao nhiêu?", value)
        for day, value in enumerate((581, 670, 668, 684, 680), start=1)
    )
    conclusion, declined = combine_results(results, "sum")
    assert conclusion is None
    assert declined is not None and "đếm trùng" in declined


def test_sum_van_cong_duoc_trong_cung_mot_ngay():
    """Ba shop trong CÙNG một ngày là các tập rời nhau — 92+22+73=187."""
    results = (
        _step('Số listing của shop "Bibica Official Store" tại VN ngày 21/07?', 92),
        _step('Số listing của shop "Kinh Do Official Store" tại VN ngày 21/07?', 22),
        _step('Số listing của shop "Mars Snacking VN" tại VN ngày 21/07?', 73),
    )
    conclusion, declined = combine_results(results, "sum")
    assert declined is None
    assert "187" in conclusion
