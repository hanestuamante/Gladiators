"""Ngân sách độ trễ và phép đo theo chặng — Spec2308 §WP-A6.

Điều kiện cần của mọi tối ưu là **đo được**. Trước module này không có phép đo
thời gian theo chặng ở bất kỳ đâu trong ``workflow.run``, nên "chậm ở đâu" là
một cảm nhận chứ không phải một con số.

Ngân sách đặt theo **p50/p95**, không theo trung bình: trung bình che mất đuôi
xấu, và người xem demo sẽ gặp đúng cái đuôi đó.
"""
from __future__ import annotations

from time import perf_counter

# §A6.3. Vượt ngân sách ⇒ về đúng lối từ chối cũ (A19-PLAN hoặc
# A-VERIFICATION-FINAL tuỳ chặng), KHÔNG có lối thoát mới và không "trả lời tạm".
P50_BUDGET_SECONDS = 8.0
P95_BUDGET_SECONDS = 15.0

# Một lần gọi LLM tốn 6,76 giây trung bình (đo trên 142 lần gọi), nên 15 giây chỉ
# đủ cho tối đa hai lần gọi TUẦN TỰ. Đây là chỉ số cần tối ưu, không phải số giây:
# hai nhánh chạy song song tính là MỘT bước trên đường tới hạn.
MAX_LLM_CALLS_CRITICAL = 2

STAGES: tuple[str, ...] = (
    "parse", "route", "entity", "gate", "plan",
    "execute", "generate", "verify", "gate_out",
)


class StageTimer:
    """Đo theo chặng bằng ``perf_counter``, ghi thẳng vào ``planning_meta``.

    Không log, không print: một phép đo chỉ hữu ích khi nó nằm cùng chỗ với
    quyết định mà nó giải thích.

    Cùng một chặng được vào nhiều lần thì thời gian **cộng dồn** — đường chạy có
    nhánh, và một chặng bị đo mất phần thứ hai là một chặng bị báo nhanh hơn nó
    thật sự.
    """

    __slots__ = ("_marks", "_open", "_start")

    def __init__(self) -> None:
        self._marks: dict[str, float] = {}
        self._open: dict[str, float] = {}
        self._start = perf_counter()

    def enter(self, stage: str) -> None:
        self._open[stage] = perf_counter()

    def leave(self, stage: str) -> None:
        started = self._open.pop(stage, None)
        if started is None:
            return
        self._marks[stage] = self._marks.get(stage, 0.0) + (perf_counter() - started)

    def stage(self, name: str) -> "_StageScope":
        return _StageScope(self, name)

    def as_dict(self) -> dict[str, float]:
        """Mili-giây theo chặng, cộng ``total``.

        ``total`` đo từ lúc dựng timer chứ không phải tổng các chặng: thời gian
        rơi ngoài mọi chặng vẫn là thời gian người dùng chờ, và giấu nó đi làm
        bảng ngân sách nói dối.
        """
        timing = {stage: round(self._marks.get(stage, 0.0) * 1000, 3) for stage in STAGES}
        timing["total"] = round((perf_counter() - self._start) * 1000, 3)
        return timing


class _StageScope:
    __slots__ = ("_timer", "_name")

    def __init__(self, timer: StageTimer, name: str) -> None:
        self._timer, self._name = timer, name

    def __enter__(self) -> "_StageScope":
        self._timer.enter(self._name)
        return self

    def __exit__(self, *exc_info: object) -> bool:
        # Chặng ném exception vẫn phải được ghi thời gian: một chặng hỏng thường
        # là chặng chậm nhất, và bỏ nó khỏi bảng là bỏ đúng ca cần nhìn.
        self._timer.leave(self._name)
        return False


def within_budget(timing: dict[str, float], llm_calls_critical: int) -> bool:
    """Một lượt chạy có nằm trong ngân sách hay không.

    Dùng cho phép kiểm ở tầng báo cáo, không phải để đổi hành vi giữa chừng: cắt
    ngang một câu trả lời đang đúng để kịp giờ là đổi tính đúng đắn lấy tốc độ.
    """
    return (
        timing.get("total", 0.0) <= P95_BUDGET_SECONDS * 1000
        and llm_calls_critical <= MAX_LLM_CALLS_CRITICAL
    )
