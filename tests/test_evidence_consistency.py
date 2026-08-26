"""WP-B6 — bất biến số học trên evidence.

Verifier hỏi "số này có evidence không", alignment hỏi "có trả lời đúng câu hỏi
không" — **không lớp nào hỏi "các con số này có nhất quán với nhau không"**.

Lỗi nghiêm trọng nhất trong lịch sử testcase, đếm 551 thay vì 577 listing có
voucher, CHÍNH LÀ một vi phạm cộng tính: 551 + 77 = 628 ≠ 668. Nguyên nhân gốc
đã sửa; lớp này chặn khi lỗi cùng loại tái xuất hiện ở chỗ khác.
"""
from __future__ import annotations

import json

import pytest

from gladiators.agent.consistency import check_evidence_arithmetic
from gladiators.agent.workflow import AgentRuntime
from gladiators.contracts import Evidence
from gladiators.external.contracts import SourceLocator

SCOPE = {"country": "vn", "observed_date": "2026-07-03", "plan_hash": "h"}


def _ev(metric: str, value, unit: str = "listings", **attrs) -> Evidence:
    return Evidence(
        evidence_id=f"ev:t:{metric}", source_tier="btc_dataset", metric=metric,
        value=value, unit=unit,
        source_locator=SourceLocator(kind="internal", value="products_clean.csv#k"),
        dataset_version="v", attrs={**SCOPE, **attrs},
    )


def test_additivity_catches_bgk03_shape():
    """551 + 77 = 628 ≠ 668 — đúng hình dạng lỗi đã xảy ra thật."""
    issues = check_evidence_arithmetic([
        _ev("with_voucher_listing_count", 551),
        _ev("without_voucher_listing_count", 77),
        _ev("listing_count", 668),
    ])
    assert [item.code for item in issues] == ["partition_does_not_sum"]


def test_correct_partition_passes():
    """577 + 91 = 668 — con số đúng phải đi qua."""
    assert check_evidence_arithmetic([
        _ev("with_voucher_listing_count", 577),
        _ev("without_voucher_listing_count", 91),
        _ev("listing_count", 668),
    ]) == ()


def test_ratio_range():
    issues = check_evidence_arithmetic([_ev("voucher_rate", 1.2, unit="share_0_1")])
    assert [item.code for item in issues] == ["ratio_out_of_range"]


def test_percent_range():
    issues = check_evidence_arithmetic([_ev("discount_percent", 140.0, unit="percent")])
    assert [item.code for item in issues] == ["percent_out_of_range"]


def test_median_between_min_max():
    issues = check_evidence_arithmetic([
        _ev("min_price", 10.0, unit="local_currency"),
        _ev("median_price", 500.0, unit="local_currency"),
        _ev("max_price", 100.0, unit="local_currency"),
    ])
    # min=10 ≤ max=100 vốn nhất quán; chỉ trung vị 500 nằm ngoài khoảng.
    assert [item.code for item in issues] == ["median_above_max"]


def test_min_above_max_is_caught_separately():
    issues = check_evidence_arithmetic([
        _ev("min_price", 900.0, unit="local_currency"),
        _ev("max_price", 100.0, unit="local_currency"),
    ])
    assert [item.code for item in issues] == ["min_above_max"]


def test_a_mean_of_countable_things_may_be_fractional():
    """`unit` mô tả đại lượng được đếm, không phải "giá trị phải nguyên".

    `mean_monthly_sold_proxy` mang unit "items" nhưng là TRUNG BÌNH — phân số là
    đúng. Bản kiểm đầu tiên báo sai đúng chỗ này trên cả hai suite voucher.
    """
    assert check_evidence_arithmetic([
        _ev("with_voucher_mean_monthly_sold_proxy", 2059.66, unit="items"),
    ]) == ()


def test_external_evidence_is_out_of_scope():
    """Tier ngoài đã có A20-TIER / A21-PROV lo."""
    assert check_evidence_arithmetic([]) == ()


# --- B6-R5 · không dương tính giả trên bộ đề thật ------------------------

@pytest.mark.parametrize("suite", [
    "questions", "questions_v2", "questions_a19", "questions_boundaries",
    "questions_ambiguity", "questions_counting", "questions_critic",
])
def test_no_false_positive_on_real_suites(tmp_path, suite):
    runtime = AgentRuntime(trace_dir=tmp_path)
    for case in json.loads(open(f"eval/{suite}.json", encoding="utf-8").read()):
        response = runtime.run(case["question"])
        issues = check_evidence_arithmetic(response.evidence)
        assert issues == (), f"{suite}:{case['id']} -> {[i.code for i in issues]}"
