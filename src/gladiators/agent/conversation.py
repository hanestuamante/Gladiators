"""Bộ nhớ hội thoại ngắn hạn — Spec2308 §WP-A3.

``clarify`` chiếm 32% bộ đề chính và 52,5% của DR-40, và hôm nay là một **ngõ
cụt**: không trạng thái nào sống qua lượt, nên người dùng phải gõ lại cả câu chỉ
để thêm một chữ "VN".

Thứ được nhớ là **các ô đã điền**, không phải đoạn hội thoại. Đây là khác biệt
quyết định: nhớ văn bản rồi viết lại câu hỏi tạo ra một nguồn lỗi mới mà không
lớp nào đang kiểm (A3-R1).

Ba luật, thiếu một luật sẽ tạo lỗi **tệ hơn** ngõ cụt hiện tại:

1. Chỉ kế thừa ô đã phân giải CHẮC CHẮN. Nhớ một phỏng đoán sai nghĩa là không
   bao giờ hỏi lại nó nữa.
2. Ngữ cảnh phải hiển thị và huỷ được. Bộ nhớ vô hình là bộ nhớ không kiểm được.
3. Bộ nhớ chỉ **điền ô**, tuyệt đối không **cấp phép**. Lượt sau vẫn đi đủ 9
   chặng.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from gladiators.domain import topics
from gladiators.domain.invariant_handlers import GOVERNED_DATES

# Danh sách ĐÓNG. Không mở rộng bằng heuristic: mỗi ô thêm vào đây là một ô có
# thể được kế thừa sai, và một ô kế thừa sai không bao giờ được hỏi lại.
#
# Chia hai nhóm vì luật hết hạn theo chủ đề áp KHÁC nhau cho chúng:
#
# * Ô PHẠM VI trả lời câu "đang nói về lát cắt dữ liệu nào". "Thị trường VN" vẫn
#   đúng dù người dùng chuyển từ hỏi số listing sang hỏi giá — nó không thuộc về
#   chủ đề nào cả.
# * Ô GẮN CHỦ ĐỀ trỏ tới một đối tượng cụ thể. Mang một listing cụ thể sang một
#   chủ đề khác là trả lời câu mới bằng đối tượng của câu cũ, và đó đúng là thứ
#   luật hết hạn tồn tại để chặn.
#
# Spec §WP-A3 xoá TOÀN BỘ state khi đổi chủ đề. Đo thật cho thấy làm vậy khiến
# gần như mọi câu hỏi tiếp theo mất ngữ cảnh — một câu hỏi tiếp theo thường hỏi
# một measure khác, tức một chủ đề khác — nên WP không đạt được chính mục tiêu
# của nó. Giữ ô phạm vi qua ranh giới chủ đề là chệch khỏi spec CÓ CHỦ ĐÍCH; nó
# vẫn thoả cả ba luật: ô kế thừa được hiển thị và huỷ được, và nó chỉ điền ô chứ
# không cấp phép.
SCOPE_SLOTS = ("country", "countries", "date_range")
TOPIC_BOUND_SLOTS = ("entity_text",)
INHERITABLE_SLOTS = SCOPE_SLOTS + TOPIC_BOUND_SLOTS

MAX_TURN_AGE = 3
SESSION_CAPACITY = 512
SESSION_TTL_SECONDS = 30 * 60


def _topics_for(refs: frozenset[str]) -> frozenset[str]:
    """Topic id của các ref đã bind.

    ``domain/topics.py`` không phơi ra ``TOPIC_BY_REF`` như spec ghi; nó phơi
    ``effective_refs(topic_id)``. Dựng chiều ngược lại ở đây thay vì thêm một
    bảng thứ hai trong topics.py — hai bảng cho cùng một quan hệ là đúng cách
    chúng lệch nhau.
    """
    return frozenset(
        topic_id for topic_id in topics.TOPICS
        if refs & set(topics.effective_refs(topic_id))
    )


@dataclass(frozen=True)
class ConversationState:
    session_id: str
    turn: int = 0
    confirmed: dict[str, Any] = field(default_factory=dict)
    origin: dict[str, int] = field(default_factory=dict)
    topic_signature: frozenset[str] = frozenset()
    touched_at: float = 0.0


@dataclass(frozen=True)
class Inheritance:
    """Kết quả áp bộ nhớ: điền được gì, và phần nào bị bỏ vì quá hạn."""

    slots: dict[str, Any] = field(default_factory=dict)
    expired: bool = False
    dropped: tuple[str, ...] = ()

    def as_dict(self, state: ConversationState) -> dict[str, Any]:
        return {
            "session_id": state.session_id,
            "turn": state.turn + 1,
            # A3 luật 2: ô kế thừa phải HIỂN THỊ được, để UI dựng chip "đang
            # dùng: thị trường VN" kèm nút bỏ.
            "inherited": sorted(self.slots),
            "dropped": list(self.dropped),
            "expired": self.expired,
        }


class ConversationStore:
    """LRU trong bộ nhớ tiến trình. KHÔNG ghi đĩa.

    Câu hỏi người dùng là dữ liệu; trace đã có cơ chế redact riêng, và một bản
    sao thứ hai nằm ngoài cơ chế đó là một bản sao không ai redact.
    """

    def __init__(
        self, capacity: int = SESSION_CAPACITY, ttl_seconds: float = SESSION_TTL_SECONDS,
    ) -> None:
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self._sessions: OrderedDict[str, ConversationState] = OrderedDict()

    def get(self, session_id: str | None) -> ConversationState | None:
        if not session_id:
            return None
        state = self._sessions.get(session_id)
        if state is None:
            return None
        if monotonic() - state.touched_at > self.ttl_seconds:
            self._sessions.pop(session_id, None)
            return None
        self._sessions.move_to_end(session_id)
        return state

    def put(self, state: ConversationState) -> None:
        self._sessions[state.session_id] = state
        self._sessions.move_to_end(state.session_id)
        while len(self._sessions) > self.capacity:
            self._sessions.popitem(last=False)

    def reset(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def clear(self) -> None:
        self._sessions.clear()


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == () or value == [] or value == {}


def apply_to_request(
    request: Any, state: ConversationState | None, new_topics: frozenset[str],
) -> tuple[Any, Inheritance]:
    """Điền các ô CÒN TRỐNG của lượt này từ bộ nhớ. Không ghi đè bao giờ.

    A3-R4: chỉ điền chỗ trống. Ghi đè một ô lượt này đã tự điền là để một câu cũ
    lấn át câu người dùng vừa gõ.
    """
    if state is None:
        return request, Inheritance()

    # Đổi chủ đề ⇒ bỏ ô gắn chủ đề, giữ ô phạm vi. Xem ghi chú ở SCOPE_SLOTS.
    topic_changed = bool(
        new_topics and state.topic_signature
        and not (new_topics & state.topic_signature),
    )
    allowed = SCOPE_SLOTS if topic_changed else INHERITABLE_SLOTS

    filled: dict[str, Any] = {}
    dropped: list[str] = [
        slot for slot in TOPIC_BOUND_SLOTS
        if topic_changed and slot in state.confirmed
    ]
    for slot in allowed:
        if slot not in state.confirmed:
            continue
        if state.turn + 1 - state.origin.get(slot, state.turn) > MAX_TURN_AGE:
            dropped.append(slot)
            continue
        if not _is_empty(getattr(request, slot, None)):
            continue
        filled[slot] = state.confirmed[slot]
    if not filled:
        return request, Inheritance(expired=topic_changed, dropped=tuple(dropped))
    return request.model_copy(update=filled), Inheritance(
        slots=filled, expired=topic_changed, dropped=tuple(dropped),
    )


def update_from_response(
    state: ConversationState | None, session_id: str, request: Any,
    capabilities: dict[str, Any], entity_state: str | None,
    new_topics: frozenset[str],
) -> ConversationState:
    """Ghi lại các ô ĐÃ XÁC LẬP CHẮC CHẮN của lượt này.

    Điều kiện xác lập cố ý hẹp — đúng bảng trong §WP-A3. Một ô do LLM đoán, hay
    một entity còn mơ hồ, KHÔNG được vào đây: nhớ nó là quyết định thay người
    dùng một lần và không bao giờ hỏi lại.
    """
    turn = (state.turn if state else 0) + 1
    confirmed = dict(state.confirmed) if state else {}
    origin = dict(state.origin) if state else {}

    known_countries = set(capabilities.get("countries") or ())
    country = getattr(request, "country", None)
    if country and (not known_countries or country in known_countries):
        confirmed["country"], origin["country"] = country, turn
    countries = tuple(getattr(request, "countries", ()) or ())
    if countries and all(
        not known_countries or item in known_countries for item in countries
    ):
        # tuple cho countries, list cho date_range — StructuredRequest khai hai
        # kiểu KHÁC nhau, và nhớ nhầm kiểu chỉ lộ ra thành cảnh báo serialize
        # ở tận lúc dựng response.
        confirmed["countries"], origin["countries"] = countries, turn

    date_range = getattr(request, "date_range", None)
    if date_range and all(str(day) in GOVERNED_DATES for day in date_range):
        # list chứ không tuple: StructuredRequest.date_range khai list[str], và
        # một tuple ở đó làm pydantic cảnh báo serialize ở TẬN lúc dựng
        # response, cách xa chỗ gán.
        confirmed["date_range"], origin["date_range"] = list(date_range), turn

    # Chỉ entity đã phân giải CHẮC CHẮN. ambiguous_broad / invalid_extraction là
    # đúng thứ phải hỏi lại, không phải thứ phải nhớ.
    if entity_state == "resolved" and getattr(request, "entity_text", None):
        confirmed["entity_text"], origin["entity_text"] = request.entity_text, turn

    signature = new_topics or (state.topic_signature if state else frozenset())
    return ConversationState(
        session_id=session_id, turn=turn, confirmed=confirmed, origin=origin,
        topic_signature=signature, touched_at=monotonic(),
    )


def topics_of(request: Any) -> frozenset[str]:
    """Chữ ký chủ đề của một request, suy từ ref ĐÃ BIND."""
    analytical = getattr(request, "analytical", None) or {}
    refs: set[str] = set()
    for key in ("requested_measures", "requested_dimensions"):
        for item in analytical.get(key) or ():
            ref = item.get("ref") if isinstance(item, dict) else getattr(item, "ref", None)
            if ref:
                refs.add(str(ref))
    return _topics_for(frozenset(refs))
