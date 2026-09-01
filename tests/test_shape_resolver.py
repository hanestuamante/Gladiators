"""LLM đề xuất HÌNH DẠNG câu hỏi — kiểm phần TẤT ĐỊNH, không kiểm model.

Tầng này tồn tại vì parser đang làm hai việc và chỉ một việc là vô hạn: nhận ra
KHÁI NIỆM (vô hạn, mỗi bộ dữ liệu một từ vựng) và nhận ra HÌNH DẠNG (hữu hạn,
chín phần tử, không đổi theo bộ dữ liệu). Việc thứ hai đang bị vá bằng danh sách
cụm viết tay, và danh sách đó phình mà vẫn trượt.

Hai cửa phải khoá, và cửa thứ hai mới là cửa thật:

    shape ∈ SHAPES                       — chuỗi bịa không đi tiếp
    shape ÁP ĐƯỢC vào measure đã bind    — `mean` trên một thang thứ bậc là một
                                           phép tính catalog không chứng nhận
"""
from __future__ import annotations

import pytest

from gladiators.planner.shape_resolver import (
    SHAPES,
    aggregation_of,
    applicable_shapes,
    ranking_direction,
    resolve_shape,
)


def test_tap_hinh_dang_la_tap_dong_chin_phan_tu():
    """Con số này là luận điểm của cả tầng: hình dạng HỮU HẠN và không đổi theo
    bộ dữ liệu, nên nhận ra nó không cần một danh sách cụm phình theo miền."""
    assert len(SHAPES) == 9
    assert {"argmax", "argmin", "median", "mean", "share"} <= SHAPES


def test_khong_co_proposer_thi_khong_lam_gi():
    out = resolve_shape("bất kỳ", ("measure.price",), None)
    assert out.called is False and out.shape is None


def test_hinh_dang_ngoai_tap_dong_bi_vut():
    out = resolve_shape(
        "x", ("measure.price",), lambda payload: {"shape": "argmaximum"},
    )
    assert out.shape is None
    assert out.rejected == "argmaximum" and "ngoài tập đóng" in (out.reason or "")


def test_hinh_dang_khong_ap_duoc_vao_measure_bi_vut():
    """`measure.rating` là thang THỨ BẬC — catalog chứng nhận median, không
    chứng nhận mean ("trung bình sao không phải trung bình của gì cả"). Một
    hình dạng có thật nhưng sai chỗ phải bị chặn ở cửa thứ hai."""
    out = resolve_shape(
        "x", ("measure.rating",), lambda payload: {"shape": "mean"},
    )
    assert out.shape is None
    assert out.rejected == "mean" and "không áp được" in (out.reason or "")
    # cùng measure, hình dạng ĐƯỢC chứng nhận thì đi qua
    assert resolve_shape(
        "x", ("measure.rating",), lambda payload: {"shape": "median"},
    ).shape == "median"


def test_null_la_cau_tra_loi_hop_le():
    """Câu mơ hồ thật thì trả null, và null KHÔNG phải một thất bại — hệ quay
    về đúng hành vi khi không có LLM."""
    out = resolve_shape("x", ("measure.price",), lambda payload: {"shape": None})
    assert out.called is True and out.shape is None and out.failed is None


def test_loi_llm_khong_thoat_ra_ngoai():
    def no(payload):
        raise TimeoutError("mạng")

    out = resolve_shape("x", ("measure.price",), no)
    assert out.called is True and out.failed == "TimeoutError" and out.shape is None


def test_hinh_dang_sai_kieu_bi_vut():
    out = resolve_shape("x", ("measure.price",), lambda payload: {"shape": 7})
    assert out.shape is None and out.rejected == "7"


def test_danh_sach_gui_di_thu_hep_theo_measure():
    """Gửi đúng lát thay vì cả chín: cơ hội nhận về một hình dạng không dùng
    được biến mất, cùng lý do `term_resolver.candidate_refs` gửi lát catalog."""
    assert "mean" not in applicable_shapes(("measure.rating",))
    assert "mean" in applicable_shapes(("measure.price",))
    # Chưa bind measure nào thì mọi hình dạng cần một đại lượng đều vô nghĩa.
    assert set(applicable_shapes(())) == {"list", "lookup", "count"}


def test_danh_sach_gui_di_luon_nam_trong_tap_dong():
    for refs in ((), ("measure.price",), ("measure.rating",),
                 ("derived.estimated_recent_revenue",)):
        assert set(applicable_shapes(refs)) <= SHAPES


@pytest.mark.parametrize("shape,direction", [("argmax", "desc"), ("argmin", "asc")])
def test_cuc_tri_suy_ra_chieu_xep_hang(shape, direction):
    assert ranking_direction(shape) == direction


@pytest.mark.parametrize("shape", ["median", "mean", "share", "count"])
def test_phep_tong_hop_suy_ra_dung_ten(shape):
    assert aggregation_of(shape) == shape


@pytest.mark.parametrize("shape", ["argmax", "argmin", "list", "lookup", "compare", None])
def test_khong_phai_phep_tong_hop_thi_khong_suy_ra_gi(shape):
    assert aggregation_of(shape) is None


def test_so_do_phan_biet_duoc_ba_trang_thai():
    """Rỗng mang ba nghĩa và chúng phải phân biệt được — nếu không thì "đã đo"
    và "đã chạy" trông giống nhau (lỗi WP-A11)."""
    chua_hoi = resolve_shape("x", ("measure.price",), None)
    da_hoi_null = resolve_shape("x", ("measure.price",), lambda p: {"shape": None})
    bi_vut = resolve_shape("x", ("measure.price",), lambda p: {"shape": "xyz"})

    assert chua_hoi.as_attrs()["llm_shape_called"] is False
    assert da_hoi_null.as_attrs()["llm_shape_called"] is True
    assert "llm_shape_rejected" not in da_hoi_null.as_attrs()
    assert bi_vut.as_attrs()["llm_shape_rejected"] == "xyz"
