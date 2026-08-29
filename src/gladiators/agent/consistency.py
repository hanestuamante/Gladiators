"""Bất biến số học trên evidence — Spec2308 §WP-B6.

Khoảng trống cụ thể: verifier hỏi *"số này có evidence không"*, alignment hỏi
*"có trả lời đúng câu hỏi không"* — **không lớp nào hỏi "các con số này có nhất
quán với nhau không"**.

Lỗi nghiêm trọng nhất trong lịch sử testcase — đếm **551** thay vì **577**
listing có voucher — chính là một vi phạm cộng tính: ``551 + 77 = 628 ≠ 668``.
Nguyên nhân gốc đã sửa, nhưng chưa lớp nào chặn khi lỗi CÙNG LOẠI tái xuất hiện
ở chỗ khác.

Số học thuần: không LLM (B6-R2), không truy vấn thêm (B6-R1).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# Khoá attrs định danh một phạm vi. Phân hoạch được nhận diện qua ĐÂY, không
# bằng cách đoán tên metric (B6-R3).
_SCOPE_KEYS = ("country", "observed_date", "plan_hash")

_RATIO_UNITS = frozenset({"share_0_1", "ratio_0_1"})
_COUNT_UNITS = frozenset({"listings", "shops", "items", "ratings", "labels"})


@dataclass(frozen=True)
class ConsistencyIssue:
    code: str
    detail: str
    metrics: tuple[str, ...] = ()


def _scope_of(item) -> tuple:
    return tuple(item.attrs.get(key) for key in _SCOPE_KEYS)


def _value_range_issues(evidence) -> list[ConsistencyIssue]:
    issues: list[ConsistencyIssue] = []
    for item in evidence:
        value = item.value
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        if item.unit == "percent" and not 0 <= value <= 100:
            issues.append(ConsistencyIssue(
                "percent_out_of_range",
                f"{item.metric} là phần trăm nhưng nằm ngoài khoảng cho phép",
                (item.metric,),
            ))
        if item.unit in _RATIO_UNITS and not 0 <= value <= 1:
            issues.append(ConsistencyIssue(
                "ratio_out_of_range",
                f"{item.metric} là tỷ lệ nhưng nằm ngoài khoảng cho phép",
                (item.metric,),
            ))
        # `unit` mô tả ĐẠI LƯỢNG ĐƯỢC ĐẾM, không phải "giá trị phải nguyên":
        # `mean_monthly_sold_proxy` mang unit "items" nhưng là TRUNG BÌNH, nên
        # phân số là đúng. Chỉ phép ĐẾM DÒNG mới bắt buộc nguyên.
        if str(item.metric).endswith("count") and (
            value < 0 or float(value) != int(value)
        ):
            issues.append(ConsistencyIssue(
                "count_not_a_whole_number",
                f"{item.metric} là phép đếm nhưng không phải số nguyên không âm",
                (item.metric,),
            ))
    return issues


def _order_issues(evidence) -> list[ConsistencyIssue]:
    """min ≤ median ≤ max khi cả ba cùng một đại lượng và cùng phạm vi."""
    buckets: dict[tuple, dict[str, float]] = {}
    for item in evidence:
        if not isinstance(item.value, (int, float)) or isinstance(item.value, bool):
            continue
        for kind in ("min", "median", "max"):
            if item.metric.startswith(f"{kind}_"):
                key = (_scope_of(item), item.metric[len(kind) + 1:])
                buckets.setdefault(key, {})[kind] = float(item.value)
    issues: list[ConsistencyIssue] = []
    for (_, base), values in buckets.items():
        low, mid, high = values.get("min"), values.get("median"), values.get("max")
        if low is not None and high is not None and low > high:
            issues.append(ConsistencyIssue(
                "min_above_max", f"{base}: giá trị nhỏ nhất lớn hơn giá trị lớn nhất",
            ))
        if mid is not None and low is not None and mid < low:
            issues.append(ConsistencyIssue(
                "median_below_min", f"{base}: trung vị nhỏ hơn giá trị nhỏ nhất",
            ))
        if mid is not None and high is not None and mid > high:
            issues.append(ConsistencyIssue(
                "median_above_max", f"{base}: trung vị lớn hơn giá trị lớn nhất",
            ))
    return issues


def _additivity_issues(evidence) -> list[ConsistencyIssue]:
    """Tổng các phần phải bằng tổng thể, sai số tuyệt đối 0 cho phép đếm.

    Đây là hình dạng của lỗi 551/77/668: hai nhóm cộng lại không ra tổng vì phép
    đếm thừa hưởng bộ lọc của phép đo.
    """
    counts: dict[tuple, list] = {}
    for item in evidence:
        if not str(item.metric).endswith("listing_count"):
            continue
        if not isinstance(item.value, (int, float)) or isinstance(item.value, bool):
            continue
        counts.setdefault(_scope_of(item), []).append(item)

    issues: list[ConsistencyIssue] = []
    for scope, items in counts.items():
        parts = [x for x in items if x.metric != "listing_count"]
        totals = [x for x in items if x.metric == "listing_count"]
        if len(parts) < 2 or len(totals) != 1:
            continue
        part_sum = sum(float(x.value) for x in parts)
        total = float(totals[0].value)
        if part_sum != total:
            issues.append(ConsistencyIssue(
                "partition_does_not_sum",
                "Tổng các nhóm không bằng tổng thể trong cùng phạm vi; "
                "thường là dấu hiệu phép đếm đã thừa hưởng bộ lọc của phép đo",
                tuple(sorted(x.metric for x in items)),
            ))
    return issues


def _share_issues(evidence) -> list[ConsistencyIssue]:
    """W11.2 §12.3.2 — một tỷ lệ phải KHỚP tử số và mẫu số của chính nó.

    Kiểm trên giá trị CHƯA làm tròn: renderer làm tròn sau verifier, không
    trước. Và ``0 <= tử <= mẫu`` — một tỷ lệ trên một trăm phần trăm là một
    phân hoạch hỏng.
    """
    by_id = {item.evidence_id: item for item in evidence}
    issues: list[ConsistencyIssue] = []
    for item in evidence:
        if item.attrs.get("derivation_op") != "share" or len(item.parent_evidence_ids) != 2:
            continue
        numerator = by_id.get(item.parent_evidence_ids[0])
        denominator = by_id.get(item.parent_evidence_ids[1])
        if numerator is None or denominator is None:
            issues.append(ConsistencyIssue(
                "share_parent_missing", "Evidence tỷ lệ trỏ tới tử/mẫu không tồn tại.",
                (item.metric,),
            ))
            continue
        num, den = float(numerator.value), float(denominator.value)
        if not (0 <= num <= den):
            issues.append(ConsistencyIssue(
                "share_partition_broken",
                f"Tử số nằm ngoài [0, mẫu số]: {num} / {den}.",
                (numerator.metric, denominator.metric),
            ))
            continue
        scale = float(item.attrs.get("scale") or 1)
        if den and abs(float(item.value) - scale * num / den) > 1e-9:
            issues.append(ConsistencyIssue(
                "share_arithmetic_mismatch",
                f"Tỷ lệ {item.value} không bằng {scale}*{num}/{den}.",
                (item.metric,),
            ))
    return issues


def check_evidence_arithmetic(evidence) -> tuple[ConsistencyIssue, ...]:
    """Toàn bộ bất biến số học. Rỗng = nhất quán."""
    if os.getenv("GLADIATORS_DISABLE_EVIDENCE_CONSISTENCY") == "1":
        # Van ngắt dành cho sự cố lúc demo, KHÔNG dành cho việc làm test xanh.
        return ()
    internal = [item for item in evidence if item.source_tier == "btc_dataset"]
    return tuple(
        _value_range_issues(internal)
        + _order_issues(internal)
        + _additivity_issues(internal)
        + _share_issues(internal)
    )
