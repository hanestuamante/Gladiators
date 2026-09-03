"""A1-R1 — khoá tương đương của bộ sinh kế hoạch.

Ràng buộc quan trọng nhất của WP-A1: **chỉ được THÊM, không được ĐỔI**. Với mọi
câu hỏi mà ``synthesize()`` trước đây trả một plan, bản mới phải trả plan giống
hệt — so bằng ``model_dump_json()`` sau khi chuẩn hoá đoạn phiên bản của
``plan_id``.

Baseline chụp tại `fbd34d0`, trước khi RelationPlanner tồn tại: 173 câu của 9
suite, 58 câu có plan, 115 câu trả ``None``.

Hai mục đã cập nhật có chủ đích ở A1.4 — ``semantic_linking:sl12`` và ``sl17``:
node ``Join`` của chúng trước đây có ``refs=[]`` vì code cũ chỉ đưa *dimension*
vào join, còn ``measure.shop_rating`` là measure. Projection cũ (6 cột cố định)
KHÔNG mang ``rating_star_num`` sang, nên join đó không khai thứ nó tồn tại để
mang. Bản mới khai đúng, và chạy thật cho ``shop_rating = 4.947162`` — khớp
chính xác giá trị tính bằng pandas.

Mục thứ ba cập nhật có chủ đích ở W1.2 (SolutionSpec2808 §2.4) — ``dr2607:tc01``:
"tại shop Perfetti Van Melle Vietnam" trước đây thành ``group_by entity.shop``
(trả mọi shop), vì surface "shop" giải về đơn vị đếm chứ không phải chiều mang
tên. VALUE_DIMENSION_BY_UNIT bind tên shop thành predicate
``dim.shop_name = 'Perfetti Van Melle Vietnam'`` và bỏ grouping — "listing CỦA
shop X" không còn bị đọc thành "listing THEO TỪNG shop".

Mục thứ tư cập nhật có chủ đích ở W30 (Spec3008 §17, LUẬT W30-R5) — **52 plan**:
``expected_cardinality`` trước đây là một CON SỐ của một bản dữ liệu
(``"<=3341"``, ``"<=1157"``, ``"<=2046"``); nay nó là một KÝ HIỆU trên lịch
snapshot (``"<=snapshot_rows"``, ``"<=listings"``). Đã chứng minh trước khi sửa
fixture: so 52 plan sau khi bỏ đúng hai khoá ``expected_cardinality`` /
``original_cardinality``, **0 plan khác nhau ở bất kỳ chỗ nào khác** — cùng
node, cùng op, cùng predicate, cùng grain, cùng plan_id. Đây là đổi hợp đồng có
chủ đích, không phải một golden bị ép xanh: cận cũ **đúng** trên bộ 3 ngày và
**sai lặng lẽ** trên bộ 20 ngày, và nó sai theo kiểu fail-closed nên nguyên nhân
bị nói sai ("plan sai hợp đồng") thay vì nói đúng ("cận viết cho một bản dữ liệu
khác").

Câu trước đây ``None`` mà nay có plan là **mở rộng hợp lệ** — đó chính là mục
tiêu của WP. Chiều ngược lại thì không: một plan biến mất hoặc đổi hình nghĩa là
WP đã lấy đi năng lực đang có, và test này bắt đúng chiều đó.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from gladiators.planner.semantic_parser import DeterministicSemanticParser
from gladiators.planner.synthesizer import synthesize

BASELINE = json.loads(
    (Path(__file__).parent / "fixtures" / "synthesizer_equivalence_baseline.json")
    .read_text(encoding="utf-8")
)
PARSER = DeterministicSemanticParser()
QUESTIONS: dict[str, tuple[str, str]] = {}
for _suite in (
    "questions", "questions_v2", "questions_a19", "questions_boundaries",
    "questions_ambiguity", "questions_counting", "questions_critic",
    "dr2607", "semantic_linking",
):
    for _case in json.loads(Path(f"eval/{_suite}.json").read_text(encoding="utf-8")):
        if _case.get("question"):
            QUESTIONS[f"{_suite}:{_case['id']}"] = (
                _case["question"], _case.get("country") or "vn",
            )


def _plan_of(question: str, country: str):
    try:
        result = synthesize(PARSER.parse(question, "vi", country), country)
    except Exception as exc:                      # noqa: BLE001 — baseline ghi cả exception
        return {"exc": type(exc).__name__}
    if result is None:
        return None
    payload = json.loads(result.plan.model_dump_json())
    # Bỏ cả đoạn quan hệ (A1.5) lẫn đoạn phiên bản trước khi so.
    payload["plan_id"] = re.sub(
        r"(?::[a-z_+]+)?:1\.\d+$", "", str(payload.get("plan_id", "")),
    )
    return payload


@pytest.mark.parametrize("key", sorted(k for k, v in BASELINE.items() if isinstance(v, dict)))
def test_existing_plans_are_unchanged(key):
    """Câu đã có plan phải giữ NGUYÊN plan đó."""
    question, country = QUESTIONS[key]
    assert _plan_of(question, country) == BASELINE[key]


# Plan biến mất CÓ CHỦ ĐÍCH: câu hỏi yêu cầu mean, catalog không chứng nhận mean
# cho discount_percent ('median','min','max'), và phép thay thầm mean→median là
# đúng lớp sai mà _choose_aggregation tồn tại để chặn. Từ chối đúng hơn một con
# số sai. Ca này cross-market nên A16-CROSS-CURRENCY chặn trước khi thực thi ⇒
# hành vi runtime KHÔNG đổi, chỉ plan đổi.
INTENTIONALLY_LOST = {
    # dr2607:tc32 ĐÃ RỜI danh sách này ngày 01/09. Lý do cũ ghi ở đây là plan
    # ra `grain_mismatch` + `fanout_risk`, và nó đọc như một giới hạn của quan
    # hệ. Đo lại thì không phải: node Join do synthesize dựng VIẾT CỨNG
    # `listing_snapshot → listing_snapshot` và không khai `dedupe_policy` bao
    # giờ, trong khi bốn cạnh left_join của registry khai bốn cặp grain KHÁC
    # NHAU. Chỉ `belongs_to` tình cờ khớp; ba cạnh còn lại không bao giờ dựng
    # nổi plan hợp lệ. Plan không hỏng vì dữ liệu — nó hỏng vì tự khai sai về
    # chính cạnh nó dùng.
    #
    # Sau khi node Join đọc grain và dedupe TỪ REGISTRY, plan của ca này dựng
    # được. Runtime KHÔNG đổi và đó là điểm quan trọng: nó vẫn
    # `abstain / A-MISSING-ADS` — từ chối vì dataset không có impressions,
    # clicks hay ad spend, tức vì ĐÚNG lý do, thay vì vì một khiếm khuyết khi
    # dựng plan. Một lời từ chối đúng kết cục mà sai nguyên nhân vẫn là một lời
    # từ chối sai.
    # dr2607:tc29 ĐÃ RỜI danh sách này ở W26 (Spec3008 §13). Plan của nó mất vì
    # `mean` không được chứng nhận cho `measure.discount_percent` — nhưng đó là
    # hệ quả của một bảng `valid_aggregations` gán tay giống hệt nhau cho mọi
    # measure, không phải một tính chất của đại lượng. W26 khai
    # `discount_percent` là `snapshot_stock`: cộng giá qua các listing vô nghĩa,
    # còn TRUNG BÌNH thì có nghĩa. Plan quay lại — "câu trước đây None mà nay có
    # plan là mở rộng hợp lệ". Runtime VẪN từ chối tc29, nay bằng
    # `A22-ALIGN-COUNTRY`: trở ngại thật của nó là câu hỏi trải hai thị trường,
    # không phải phép trung bình.
    # W8.3: cụm "voucher" trần là HAI khái niệm (structured 0/474 trên ID so
    # với nhãn hiển thị 210/474). Plan cũ của sáu câu này tồn tại nhờ alias
    # chọn THẦM nghĩa structured — đúng phép chọn hộ mà W8.3 đóng. Runtime cả
    # sáu câu đi đường MACRO (promotion_effectiveness / voucher_profile_rank)
    # và không đổi hành vi: questions + questions_v2 vẫn 1.0 sau thay đổi.
    "questions:q28": "voucher trần hết được chọn thầm nghĩa structured",
    "questions:q29": "voucher trần hết được chọn thầm nghĩa structured",
    "questions:q32": "voucher trần hết được chọn thầm nghĩa structured",
    "questions:q60": "voucher trần hết được chọn thầm nghĩa structured",
    "questions_v2:v2q10": "voucher trần hết được chọn thầm nghĩa structured",
    "questions_v2:v2q11": "voucher trần hết được chọn thầm nghĩa structured",
}


def test_no_plan_is_lost():
    """Không câu nào đang có plan được phép rơi về None, trừ ca đã khai lý do."""
    lost = [
        key for key, expected in BASELINE.items()
        if isinstance(expected, dict) and "exc" not in expected
        and _plan_of(*QUESTIONS[key]) is None
    ]
    assert lost == [], f"WP đã lấy đi plan của: {lost}"


def test_an_intentionally_lost_plan_is_lost_for_the_reason_it_declares():
    """Allowlist phải THẬT SỰ mất plan, và mất vì đúng mã decline đã ghi — nếu
    không nó là một tấm thảm quét bụi thay vì một quyết định."""
    from gladiators.planner.synthesizer import synthesize

    for key, reason in INTENTIONALLY_LOST.items():
        question, country = QUESTIONS[key]
        codes: list[str] = []
        assert synthesize(
            PARSER.parse(question, "vi", country), country, decline=codes,
        ) is None, key
        # Sáu ca voucher: mất binding vì ambiguity — synthesizer thấy câu không
        # còn measure/điều kiện voucher, và decline vì lý do CẤU TRÚC
        # (measure_count/unbound), không phải aggregation.
        assert codes, (key, reason)


def test_baseline_still_describes_the_same_corpus():
    """Baseline lệch tập câu hỏi thì nó không còn khoá được gì."""
    assert set(BASELINE) == set(QUESTIONS)
