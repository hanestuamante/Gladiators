"""W22 — khái niệm dataset KHÔNG CÓ, khai một chỗ và fail ở import.

Vấn đề đóng (Spec3008 §9): lý do từ chối hôm nay do THỨ TỰ LUẬT quyết định, không
do thứ đã chặn. Một câu hỏi về **NPS** thiếu country nhận được lời khuyên *"hãy
chọn thị trường"* — một hành động **không thể làm cột NPS tồn tại**.
``refusal_reason_accuracy`` 0.583/0.625 chính là con số đó.

Cơ chế: ``BindingLedger.significant()`` mang những cụm mà KHÔNG binder nào nhận.
Trước W16 chúng bị vứt không dấu vết, nên không lớp nào phía sau trả lời được câu
*"cụm này có được biểu diễn hay đã bị bỏ rơi?"*. Nay chúng có kiểu, và registry
này biến một cụm còn dư thành một lời từ chối NÓI ĐÚNG TRỞ NGẠI.

**Fail ở import** theo đúng khuôn ``_build_catalog`` / ``VALUE_DIMENSION_BY_UNIT``:
gõ sai một ``capability_key`` phải nổ lúc nạp module, không đợi tới lúc một câu
hỏi chạm vào — một ID trông hợp lệ mà không resolve tới đâu nguy hơn thiếu
registry, vì người đọc tin rule đã được thi hành.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RefusalClass = Literal[
    "missing_field", "missing_grain", "forecast_unsupported", "external_data",
]


class AbsentConceptError(ValueError):
    """Registry mâu thuẫn — hỏng ở import, không đợi một câu hỏi chạm vào."""


@dataclass(frozen=True)
class AbsentConcept:
    concept_id: str
    surfaces: tuple[str, ...]          # đã fold, đa ngôn ngữ
    refusal_class: RefusalClass
    capability_key: str | None = None  # khoá trong gate.CAPABILITY_MESSAGES
    reason: str = ""                   # câu nói với người dùng, KHÔNG chữ số


ABSENT_CONCEPTS: tuple[AbsentConcept, ...] = (
    AbsentConcept(
        "nps", ("nps", "net promoter"), "missing_field",
        reason="Dữ liệu nội bộ không quan sát điểm NPS của shop.",
    ),
    AbsentConcept(
        "headcount", ("nhan vien", "employee", "karyawan", "staff"), "missing_field",
        reason="Dữ liệu nội bộ không quan sát nhân sự của shop.",
    ),
    AbsentConcept(
        "pageview",
        ("luot xem trang", "pageview", "page view", "traffic", "luot truy cap"),
        "missing_field",
        reason="Dữ liệu nội bộ không quan sát lượt xem trang.",
    ),
    AbsentConcept(
        "profit", ("loi nhuan", "profit", "margin", "laba"), "missing_field",
        capability_key="profit",
    ),
    AbsentConcept(
        "inventory", ("ton kho", "inventory", "stok"), "missing_field",
        capability_key="inventory",
    ),
    AbsentConcept(
        "conversion", ("chuyen doi", "conversion"), "missing_field",
        capability_key="conversion",
    ),
    AbsentConcept(
        "ads", ("quang cao", "impression", "click", "ad spend"), "missing_field",
        capability_key="ads",
    ),
    AbsentConcept(
        "sku", ("sku", "bien the", "variant"), "missing_grain",
        capability_key="sku",
    ),
    AbsentConcept(
        "orders", ("don hang", "order", "pesanan"), "missing_grain",
        capability_key="orders",
    ),
    AbsentConcept(
        "hourly",
        ("theo gio", "tung gio", "hourly", "per jam", "theo phut"),
        "missing_grain",
        reason=(
            "Dữ liệu nội bộ được thu theo từng đợt trong ngày, không theo giờ, "
            "nên không có quan sát nào ở mức đó."
        ),
    ),
    AbsentConcept(
        "forecast",
        ("du bao", "forecast", "predict", "prediction", "ramalan",
         "next week", "tuan toi", "thang sau"),
        "forecast_unsupported",
        capability_key="forecast",
    ),
    # `competitor` KHÔNG có ở đây, và phép kiểm W22-R4 là thứ phát hiện ra: nó
    # là alias của `derived.similarity_score`, tức hệ CÓ khái niệm đó. Khai nó
    # vắng mặt sẽ từ chối một câu hỏi hệ trả lời được — đúng loại lỗi mà việc
    # gộp hai registry vào một phép kiểm tồn tại để chặn.
    AbsentConcept(
        "market_price", ("gia thi truong",), "external_data",
        capability_key="external",
    ),
)


def _check_registry() -> None:
    """LUẬT W22-R1 — registry fail ở import.

    Hai kiểm, và mỗi kiểm đóng một cách lệch đã xảy ra thật ở repo này:

    * ``capability_key`` phải tồn tại trong ``gate.CAPABILITY_MESSAGES`` — một ID
      không dereference tới đâu là prose mặc schema (§E3 của Metadata layer).
    * ``AbsentConcept`` KHÔNG được chồng lấn catalog (W22-R4): một khái niệm CÓ
      ref là một khái niệm hệ hiểu; nếu artifact của nó chưa thu thì đó là việc
      của W31, và hai registry cùng trả lời "không dùng được" bằng hai lý do
      khác nhau là cách chúng lệch nhau.
    """
    from gladiators.agent.gate import CAPABILITY_MESSAGES
    from gladiators.domain.catalog import CATALOG

    seen: set[str] = set()
    alias_index = {
        alias
        for obj in CATALOG.values()
        for alias in obj.aliases
    }
    for concept in ABSENT_CONCEPTS:
        if concept.concept_id in seen:
            raise AbsentConceptError(f"concept trùng: {concept.concept_id}")
        seen.add(concept.concept_id)
        if not concept.surfaces:
            raise AbsentConceptError(f"{concept.concept_id}: không có surface nào")
        if concept.capability_key and concept.capability_key not in CAPABILITY_MESSAGES:
            raise AbsentConceptError(
                f"{concept.concept_id}: capability_key {concept.capability_key!r} "
                "không có trong gate.CAPABILITY_MESSAGES",
            )
        if not concept.capability_key and not concept.reason:
            raise AbsentConceptError(
                f"{concept.concept_id}: không có capability_key thì phải tự khai "
                "`reason` — một lời từ chối không có nội dung là một lời từ chối "
                "người dùng không hành động được",
            )
        overlap = sorted(set(concept.surfaces) & alias_index)
        if overlap:
            raise AbsentConceptError(
                f"{concept.concept_id}: surface {overlap} vừa khai là VẮNG MẶT "
                "vừa là alias của một ref có thật (W22-R4)",
            )


_SURFACE_TO_CONCEPT: dict[str, AbsentConcept] = {
    surface: concept for concept in ABSENT_CONCEPTS for surface in concept.surfaces
}


def match(folded_span: str) -> AbsentConcept | None:
    """Cụm còn dư này có phải một khái niệm đã khai là VẮNG MẶT không?

    Khớp CHÍNH XÁC hoặc theo cụm con nguyên từ — không fuzzy. Một lời từ chối
    dựa trên phép đoán gần đúng là một lời từ chối không kiểm lại được.
    """
    if not folded_span:
        return None
    if folded_span in _SURFACE_TO_CONCEPT:
        return _SURFACE_TO_CONCEPT[folded_span]
    words = folded_span.split()
    for surface, concept in _SURFACE_TO_CONCEPT.items():
        parts = surface.split()
        if len(parts) > len(words):
            continue
        for start in range(len(words) - len(parts) + 1):
            if words[start:start + len(parts)] == parts:
                return concept
    return None


# Gọi ở CUỐI module import ``gate``, không ở đây: ``gate`` import module này để
# dùng ``match``, nên kiểm ngay lúc nạp sẽ tạo vòng import. Vẫn là "fail ở
# import" theo đúng nghĩa — nó chạy khi gate được nạp, và không câu hỏi nào tới
# được gate mà không nạp gate.
check_registry = _check_registry
