"""Vòng R — nới lát cắt ngữ cảnh rồi thử lại đúng một lần (Spec2308 §A5.2).

Vòng này tồn tại vì từ phía planner, một ref BỊ CẮT khỏi lát cắt và một ref
KHÔNG TỒN TẠI trông giống hệt nhau. Chỉ việc nới ra rồi thử lại mới phân biệt
được — và nếu không phân biệt được, việc tối ưu token trở thành một nguồn từ
chối oan mới.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# open_planner nạp gladiators.agent.context, mà gói agent nạp ngược lại
# open_planner. Nạp workflow trước để vòng khép ở đúng một hướng — vòng này có
# sẵn trong cây import, không phải do test tạo ra.
import gladiators.agent.workflow  # noqa: F401
from gladiators.planner.open_planner import (
    OpenAnalyticalPlanner,
    OpenPlannerError,
    RELAX_CATALOG_LIMIT,
    _missing_refs,
)
from gladiators.planner.query_ir import LogicalQueryPlan
from gladiators.planner.synthesizer import synthesize
from gladiators.planner.semantic_parser import DeterministicSemanticParser


def _valid_plan_for(request) -> LogicalQueryPlan:
    """Plan hợp lệ THẬT, do chính synthesizer sinh.

    Viết tay một plan ở đây là viết tay một thứ validator chưa chắc chấp nhận —
    và test sẽ đỏ vì plan sai, không vì vòng R sai.
    """
    synthesized = synthesize(request, "vn")
    assert synthesized is not None
    return synthesized.plan


class _CountingPlanner:
    """Trả cùng một plan mỗi lần, và đếm số lần bị gọi."""

    provider, model, prompt_version = "test", "relax", "p8-relax"

    def __init__(self, plan: LogicalQueryPlan):
        self.calls = 0
        self.plan = plan
        self.slice_sizes: list[int] = []

    def plan_analytical(self, payload):
        self.calls += 1
        self.slice_sizes.append(len(payload["catalog_slice"]))
        return self.plan.model_dump(mode="json")


@pytest.fixture
def request_obj() -> AnalyticalRequest:
    # Dùng chính parser thật thay vì bịa một request bằng tay: một fixture lệch
    # schema sẽ kiểm một hình dạng request không bao giờ xảy ra ở runtime.
    return DeterministicSemanticParser().parse(
        "Rating trung vị theo brand tại VN", "vi", "vn",
    )


def test_narrow_slice_is_widened_once_and_the_plan_survives(request_obj):
    """Lát cắt hẹp tới mức thiếu ref ⇒ nới một lần ⇒ plan qua được."""
    client = _CountingPlanner(_valid_plan_for(request_obj))
    planner = OpenAnalyticalPlanner(client, catalog_limit=3, use_synthesizer=False)
    result = planner.plan("Rating trung vị theo brand tại VN", request_obj, "vn")

    assert result.mode == "llm_semantic_plan"
    assert result.context_relax is not None
    assert result.context_relax["attempted"] is True
    assert result.context_relax["widened_to"] == RELAX_CATALOG_LIMIT
    # Ref bị báo thiếu phải được NÊU TÊN trong telemetry: "đã nới" mà không nói
    # nới thêm cái gì thì không kiểm lại được.
    assert result.context_relax["added_refs"]
    # Lát cắt lượt hai phải RỘNG HƠN lượt một — nếu bằng nhau thì vòng R chỉ là
    # một lần thử lại y hệt, và nó không giải thích được điều gì.
    assert client.slice_sizes[-1] > client.slice_sizes[0]


def test_the_relax_loop_runs_at_most_once(request_obj):
    """A5-R1: nới đúng một lần. Plan hỏng vĩnh viễn không được nới vòng hai."""

    class AlwaysInvalid:
        provider, model, prompt_version = "test", "bad", "p8-bad"

        def __init__(self):
            self.calls = 0

        def plan_analytical(self, payload):
            self.calls += 1
            return {"plan": {"nonsense": True}}

    client = AlwaysInvalid()
    planner = OpenAnalyticalPlanner(client, catalog_limit=3, use_synthesizer=False)
    with pytest.raises(OpenPlannerError):
        planner.plan("Rating trung vị theo brand tại VN", request_obj, "vn")
    # Hai lần sửa của lượt một; schema hỏng KHÔNG phải missing_semantic_object
    # nên vòng R không được kích hoạt.
    assert client.calls == 2


def test_missing_refs_only_widens_for_refs_named_by_name():
    """Không nêu tên ref thì không nới: nới mù là nới validator, không phải slice."""
    named = _missing_refs([{
        "code": "missing_semantic_object",
        "message": "Ref nằm ngoài catalog slice: measure.rating",
    }])
    assert named == {"measure.rating"}

    assert _missing_refs([{
        "code": "missing_semantic_object", "message": "thiếu ref nhưng không nêu tên",
    }]) == set()
    # Code khác không kích hoạt vòng R.
    assert _missing_refs([{
        "code": "schema_invalid", "message": "measure.rating",
    }]) == set()
