"""Bốn con số, bốn cái tên — W9.1 (SolutionSpec2808 §10.1).

Hai script từng giữ hai bản của cùng công thức dưới CÙNG một cái tên
``coverage`` với HAI mẫu số khác nhau (answered/labelled so với
answered∩answerable/answerable) — đó là lý do cùng một hệ được mô tả lúc
45,45% lúc 52,63%. Hai bản là lý do hai công thức trôi khỏi nhau; từ giờ cả
hai script gọi MỘT hàm này.
"""
from __future__ import annotations


def rate(numerator: int, denominator: int) -> float | None:
    """``None`` khi mẫu số rỗng — KHÔNG phải 0.0.

    ``CLAUDE.md`` §3.1: điền 0 làm "không đo được" trông giống hệt "đo được và
    bằng 0". Một suite không có case answerable mà báo coverage 0.0 sẽ đọc
    thành "hệ không phủ được gì", trong khi sự thật là không có gì để phủ.
    """
    return numerator / denominator if denominator else None


def selective_metric_names() -> tuple[str, ...]:
    return (
        "answer_rate_all", "answerable_coverage", "risk",
        "over_refusal_rate", "over_answer_rate",
        "refusal_precision", "refusal_recall",
    )


def compute_selective_metrics(
    *,
    answerable: set[str],
    unanswerable: set[str],
    answered: set[str],
    refused: set[str],
    correct: set[str],
    unscored_answered: set[str] = frozenset(),
) -> dict[str, float | None]:
    """Từ điển bắt buộc của §10.1 — mọi tập đã lọc về case CÓ NHÃN.

    ``risk`` và ``over_answer_rate`` xuất hiện CẠNH mọi con số coverage: tách
    rời chúng là mở đường cho việc tối ưu coverage bằng đoán bừa.
    """
    labelled = answerable | unanswerable
    answered = set(answered) & labelled
    refused = set(refused) & labelled
    correct = set(correct) & labelled
    unscored = set(unscored_answered) & labelled
    return {
        "answer_rate_all": rate(len(answered), len(labelled)),
        "answerable_coverage": rate(len(answered & answerable), len(answerable)),
        "risk": rate(len(answered - correct - unscored), len(answered - unscored)),
        "over_refusal_rate": rate(len(refused & answerable), len(answerable)),
        "over_answer_rate": rate(len(answered & unanswerable), len(unanswerable)),
        "refusal_precision": rate(len(refused & unanswerable), len(refused)),
        "refusal_recall": rate(len(refused & unanswerable), len(unanswerable)),
    }
