"""Trọng tài intent theo chính sách — Spec2308 §WP-A11.

Số đã đo trên corpus 32 câu có nhãn::

    deterministic          17/32 = 53,1%
    LLM thô                23/32 = 71,9%      ← đúng hơn 6 case
    intent sau khi merge   17/32 = 53,1%      ← precedence cho deterministic thắng 32/32

LLM đóng góp **bằng 0** vào intent cuối. Đó không phải lỗi model mà là một chính
sách an toàn **đang quá chặt** — và một chính sách chỉ sửa được khi nó là một
thứ có tên, đọc được, và đo được, thay vì nằm rải trong một hàm parse.

Module này **không** chứa năm nhánh precedence. Chúng ở nguyên trong
``workflow._parse`` và luôn chạy TRƯỚC (A11-R2): chúng là các nhánh **an toàn**,
không phải nhánh **chất lượng**. Thứ ở đây là một luật duy nhất chạy sau chúng.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Literal

Policy = Literal["P-A", "P-B"]

# A11-R3: mặc định P-A, tức hành vi hiện tại. Đổi mặc định cần một phép đo cho
# thấy P-B THẮNG — không phải hoà.
DEFAULT_POLICY: Policy = "P-A"
POLICY_ENV = "GLADIATORS_INTENT_POLICY"


def current_policy() -> Policy:
    """Chính sách đang hiệu lực. Giá trị lạ ⇒ P-A, không ⇒ lỗi.

    Một biến môi trường gõ sai không được phép mở một chính sách rộng hơn: chế độ
    hỏng an toàn ở đây là quay về hành vi hiện tại.
    """
    value = os.getenv(POLICY_ENV, DEFAULT_POLICY)
    return "P-B" if value == "P-B" else "P-A"


class IntentLabelError(ValueError):
    """A11-R5: nhãn ngoài tập đã đăng ký là **lỗi**, không phải nhãn gần đúng."""


def validate_label(label: str, allowed: frozenset[str]) -> str:
    """Kiểm nhãn bằng allow-list trước khi nó đi tiếp.

    "Gần đúng" là khái niệm không tồn tại ở đây: một nhãn sai được sửa thành nhãn
    gần nhất là một quyết định định tuyến do phép so chuỗi đưa ra.
    """
    if label in allowed:
        return label
    if label.startswith("unsupported:"):
        return label
    raise IntentLabelError(f"Nhãn intent ngoài tập đã đăng ký: {label}")


def arbitrate(
    deterministic: Any, parsed: Any, adjustments: list[str], *,
    policy: Policy,
    is_registered: Callable[[str], bool],
    capability_serves: Callable[[str, Any], bool],
    llm_intent: str | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Chọn request cuối sau khi năm nhánh precedence đã chạy.

    ``llm_intent`` phải là nhãn LLM **TRƯỚC** khi precedence ghi đè. Đọc nó từ
    ``parsed.intent`` là sai và sai một cách IM LẶNG: tới lúc hàm này chạy,
    các nhánh precedence đã ghi ``deterministic.intent`` vào ``parsed``, nên
    ``parsed.intent == deterministic.intent`` và P-B trả ``no_change`` cho MỌI
    câu. Đo trên 44 câu B3 cho ra hai bảng số giống hệt nhau — trông như "P-B
    vô hại", thật ra là "P-B chưa từng chạy".

    ``P-A`` trả lại y nguyên thứ nhận vào — đó chính là định nghĩa "hành vi hiện
    tại", và nó phải đúng theo cấu trúc chứ không theo lời hứa.

    ``P-B`` thêm **đúng một** luật: khi parser deterministic nói nó KHÔNG tìm
    được đường (``open_analytical``, hoặc một intent không có trong registry),
    nhãn của LLM được dùng — nhưng chỉ khi nhãn đó vừa có đăng ký vừa **thoả
    capability contract** của chính request này. Điều kiện sau là thứ ngăn P-B
    lặp lại lỗi đã đo: DeepSeek gán "Có bao nhiêu listing ở VN?" thành
    ``dataset_coverage``, mà hình dạng đã chứng nhận của macro đó không sinh được
    một con số vô hướng — và macro trả lời một câu khác.
    """
    if policy != "P-B":
        return parsed, {"policy": "P-A"}

    llm_intent = llm_intent or getattr(parsed, "intent", None)
    deterministic_is_open = (
        deterministic.intent == "open_analytical"
        or not is_registered(deterministic.intent)
    )
    if not deterministic_is_open or not llm_intent or llm_intent == deterministic.intent:
        return parsed, {"policy": "P-B", "reason": "no_change"}
    if not is_registered(llm_intent) or not capability_serves(llm_intent, deterministic):
        return parsed, {"policy": "P-B", "reason": "llm_label_not_served"}

    # Nhãn LLM thắng ⇒ gỡ đúng nhánh precedence đã ghi đè nó, không gỡ nhánh nào
    # khác. Xoá cả danh sách sẽ giấu mất các nhánh AN TOÀN đã bắn.
    restored = parsed.model_copy(update={"intent": llm_intent})
    adjustments[:] = [
        name for name in adjustments if name != "open_analytical_precedence"
    ]
    return restored, {
        "policy": "P-B", "reason": "deterministic_open", "llm_intent": llm_intent,
    }


def two_way_clarify(candidates: tuple[str, ...], allowed: frozenset[str]) -> tuple[str, str] | None:
    """Hai nhãn ứng viên đầu, nếu cả hai đều hợp lệ và khác nhau.

    Khi hai nhãn cùng hợp lệ, phản hồi đúng là ``clarify`` liệt kê **đúng hai**
    nhãn bằng lời — không phải một câu hỏi mở kiểu "bạn muốn hỏi gì?", vốn đẩy
    lại toàn bộ công việc cho người dùng ngay ở chỗ hệ thống đã biết gần hết.

    CHƯA CÓ provider nào phát ra danh sách ứng viên: giao thức ``parse_intent``
    hiện trả đúng một nhãn. Hàm này là phần thuần hàm của luật, kiểm được ngay,
    và nó nằm đây để nhánh đó không phải viết lại từ đầu khi giao thức đổi.
    """
    valid = [label for label in candidates if label in allowed]
    if len(valid) < 2 or valid[0] == valid[1]:
        return None
    return valid[0], valid[1]
