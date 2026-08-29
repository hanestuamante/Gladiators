"""Một chuẩn predicate operator từ parser tới compiler — W11.1 (SolutionSpec2808 §12.2.1).

Sống ở ``domain`` (spec đặt ở ``planner``) vì ``metrics.py`` cũng phải import
nó, mà ``planner/__init__`` kéo theo validator → catalog → metrics — một vòng.
``planner.predicate_ops`` vẫn tồn tại như một re-export để call site theo spec
không đổi.

Source từng có ba dialect không khớp nhau: ``AnalyticalPredicate`` nói
``le/ge/between/isnull``, Query IR và catalog nói ``lte/gte``, còn
``MetricConstraint`` tự khai một type thứ ba. Một bộ nhận dạng so sánh sinh
``ge`` sẽ bị synthesizer từ chối ngay ở ``op not in allowed_filters`` — từ chối
vì đúng lý do sai.

Luật: ``le/ge`` chỉ được nhận ở BIÊN đọc payload cũ rồi lưu thành ``lte/gte``;
không object nội bộ nào được giữ legacy op. ``between`` phải được parser tách
thành ``gte`` + ``lte`` trước khi dựng model. ``isnull`` chưa có compiler
semantics nên phải vào ``unsupported_operators`` và fail-closed ``A19-OP`` —
không bao giờ biến thành ``eq None``.
"""
from __future__ import annotations

from typing import Literal, get_args

ExecutablePredicateOp = Literal[
    "eq", "ne", "lt", "lte", "gt", "gte", "in", "contains",
]

EXECUTABLE_OPS: frozenset[str] = frozenset(get_args(ExecutablePredicateOp))
ORDERED_OPS: frozenset[str] = frozenset({"lt", "lte", "gt", "gte"})
LEGACY_ALIASES: dict[str, str] = {"le": "lte", "ge": "gte"}


def canonicalize_predicate_op(value: str) -> ExecutablePredicateOp:
    """Op khả thi duy nhất cho một chuỗi op — hoặc ``ValueError``.

    ``ValueError`` chứ không phải một fallback: một op không canonicalize được
    là một predicate không ai biết nghĩa, và thứ đó phải hỏng Ở ĐÂY chứ không
    phải trong một câu SQL chạy sai trong im lặng.
    """
    canonical = LEGACY_ALIASES.get(value, value)
    if canonical not in EXECUTABLE_OPS:
        raise ValueError(f"Predicate op không canonicalize được: {value!r}")
    return canonical  # type: ignore[return-value]
