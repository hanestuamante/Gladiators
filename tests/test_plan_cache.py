"""Cache kết quả kế hoạch — Spec2308 §A6.2.

Cache này an toàn vì khoá của nó là **mã kế hoạch đã qua validator** cộng
**phiên bản dữ liệu**, không phải câu chữ người dùng gõ. Ba test dưới đây kiểm
đúng ba cách nó có thể nói dối.
"""
from __future__ import annotations

import gladiators.agent.workflow  # noqa: F401
from gladiators.planner.plan_cache import CachedResult, PlanResultCache


def _result(frame="FRAME", rows=3, tie=False) -> CachedResult:
    return CachedResult(frame=frame, row_count=rows, rank_tie_at_cut=tie)


def test_the_same_plan_on_the_same_dataset_hits():
    cache = PlanResultCache()
    assert cache.get("h1", "v1") is None
    cache.put("h1", "v1", _result())
    hit = cache.get("h1", "v1")
    assert hit is not None and hit.row_count == 3
    assert cache.stats()["hits"] == 1


def test_a_different_dataset_version_is_a_miss_not_a_hit():
    """A6-R1. Không có dataset_version trong khoá, cache sống sót qua một lần
    đổi dữ liệu và trả số của dataset cũ dưới tên dataset mới."""
    cache = PlanResultCache()
    cache.put("h1", "v1", _result())
    assert cache.get("h1", "v2") is None


def test_a_tie_at_the_cut_is_never_cached():
    """A6-R3. Trạng thái hoà ở mép cắt phụ thuộc DỮ LIỆU, không phụ thuộc plan,
    nên nó không phải hàm của khoá."""
    cache = PlanResultCache()
    assert cache.put("h1", "v1", _result(tie=True)) is False
    assert cache.get("h1", "v1") is None


def test_the_cache_evicts_least_recently_used():
    cache = PlanResultCache(capacity=2)
    cache.put("a", "v1", _result())
    cache.put("b", "v1", _result())
    cache.get("a", "v1")                      # 'a' vừa được dùng ⇒ 'b' là cũ nhất
    cache.put("c", "v1", _result())
    assert cache.get("b", "v1") is None
    assert cache.get("a", "v1") is not None


def test_the_runtime_reuses_the_frame_on_a_repeated_question():
    """Kiểm bằng HÀNH VI, không bằng cấu trúc: chạy hai lần và xem verdict cache.

    Một cache có mặt trong code và một cache thật sự được tra trông giống hệt
    nhau từ ngoài (CLAUDE.md §5.1.1).
    """
    from gladiators.agent.workflow import AgentRuntime
    from gladiators.planner.plan_cache import PLAN_RESULT_CACHE

    PLAN_RESULT_CACHE.clear()
    runtime = AgentRuntime()
    question = "Có bao nhiêu listing tại Việt Nam ngày 03/07?"
    first = runtime.run(question)
    second = runtime.run(question)

    assert first.planning["plan_cache"]["hit"] is False
    assert second.planning["plan_cache"]["hit"] is True
    # Kết quả phải GIỐNG NHAU: một cache đổi câu trả lời là một cache hỏng.
    assert [item.value for item in first.evidence] == [
        item.value for item in second.evidence
    ]
