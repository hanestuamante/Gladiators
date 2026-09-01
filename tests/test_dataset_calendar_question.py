"""Câu hỏi về CHÍNH bộ dữ liệu, không phải về hàng hoá trong đó.

Macro `dataset_coverage` trả sẵn ngày đầu / ngày cuối / số đợt thu từ lâu, nhưng
cửa vào duy nhất của nó là nhánh "dự báo tháng N" — tức hệ chỉ nói ra lịch dữ
liệu khi đang TỪ CHỐI một câu hỏi khác. Hỏi thẳng thì rơi vào đường analytical
và nhận "Thiếu country để khóa scope VN hoặc ID", một đòi hỏi sai: lịch đợt thu
giống hệt nhau ở cả hai thị trường.
"""
from __future__ import annotations

import pytest

from gladiators.agent.parser import MultilingualIntentParser
from gladiators.domain.intent_registry import default_registry

PARSER = MultilingualIntentParser()
REGISTRY = default_registry()

CALENDAR_QUESTIONS = (
    "Dữ liệu có bao nhiêu ngày?",
    "Bộ dữ liệu này gồm những ngày nào?",
    "Có bao nhiêu snapshot trong dữ liệu?",
    "Dữ liệu bắt đầu từ ngày nào đến ngày nào?",
    "Dataset này bao phủ khoảng thời gian nào?",
)

# Câu GỌI TÊN bộ dữ liệu nhưng KHÔNG hỏi về thời gian — phải đi đường cũ. Đây là
# vế giữ cho luật hẹp; thiếu nó thì mọi câu có chữ "dữ liệu" biến thành câu hỏi
# về lịch, và "có bao nhiêu shop trong dữ liệu" ngừng trả 10.
NOT_CALENDAR = (
    "Có bao nhiêu shop trong dữ liệu ở VN?",
    "Giá trung vị trong dữ liệu ở VN ngày 21/7?",
    "Có bao nhiêu listing ở VN ngày 21/7?",
)


@pytest.mark.parametrize("question", CALENDAR_QUESTIONS)
def test_cau_hoi_ve_lich_du_lieu_di_toi_macro_dataset_coverage(question):
    assert PARSER.parse(question, REGISTRY).intent == "dataset_coverage", question


@pytest.mark.parametrize("question", NOT_CALENDAR)
def test_cau_goi_ten_du_lieu_nhung_hoi_thu_khac_khong_bi_keo_sang(question):
    assert PARSER.parse(question, REGISTRY).intent != "dataset_coverage", question


def test_khong_doi_country_vi_lich_khong_phu_thuoc_thi_truong():
    """Đo được: vn và id đều 20 ngày 01–21/07, nên country không đổi đáp án."""
    request = PARSER.parse("Dữ liệu có bao nhiêu ngày?", REGISTRY)
    assert request.country is None
    assert request.intent == "dataset_coverage"
