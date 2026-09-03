"""W1 — literal đi lọc phải là giá trị có thật trong dữ liệu (SolutionSpec2808 §2.11).

Mọi ca hành vi chạy **qua runtime**, không gọi hàm cô lập (§0.3 mục 3): tám test
của WP-A11 từng xanh trên một nhánh chưa bao giờ chạy, và bài học đó nằm ngay
trong `CLAUDE.md` §5.1.

Thứ tự nghiệm thu không được đảo: ca giao rỗng chỉ có nghĩa **sau khi** hai
positive control trả đúng 96 và 120 — nghiệm thu bằng một số 0 mà chưa chứng
minh được hệ biết trả ra số khác 0 là nghiệm thu chính cái lỗi W1 sửa.
"""
from __future__ import annotations

from conftest import DATA_DIR

import json
from pathlib import Path

import pytest

from gladiators.agent import value_probe
from gladiators.agent.workflow import AgentRuntime
from gladiators.data.dataset_version import DatasetVersionError, compute_dataset_version
from gladiators.planner.query_ir import LogicalQueryPlan, OutputField, PlanNode, Predicate


@pytest.fixture(scope="module")
def runtime() -> AgentRuntime:
    return AgentRuntime()


# --- positive controls -----------------------------------------------------

def test_a_brand_count_binds_the_original_casing(runtime):
    """Bibica, VN, 03/07 → allow · 96 — positive control chiều brand.

    Trước W1: literal đi vào SQL là bản đã fold ``bibica``, dữ liệu ghi
    ``Bibica``, và 0 dòng đi qua mọi lớp kiểm như một "kết quả rỗng hợp lệ".
    """
    response = runtime.run(
        "Có bao nhiêu listing của thương hiệu Bibica tại Việt Nam ngày 03/07?",
    )
    assert response.gate.action == "allow"
    values = {item.metric: item.value for item in response.evidence}
    assert 96 in values.values()


def test_a_shop_count_binds_the_shop_name(runtime):
    """Richy - Chi nhánh Miền Nam, VN, 03/07 → allow · 120.

    W1 làm tên shop bind được thành predicate; W7 gỡ thang leo thang khỏi plan
    tất định để nó được CHẠY. Hai mảnh của cùng một câu trả lời.
    """
    response = runtime.run(
        'Có bao nhiêu listing của shop "Richy - Chi nhánh Miền Nam" '
        "tại Việt Nam ngày 03/07?",
    )
    assert response.gate.action == "allow"
    values = {item.metric: item.value for item in response.evidence}
    assert 120 in values.values()


def test_an_empty_intersection_is_a_result(runtime):
    """Bibica **tại** shop Richy → allow · 0 — zero-row THẬT.

    Ca này chỉ có nghĩa vì hai positive control ở trên đã trả đúng 96 và 120:
    nghiệm thu "không có kết quả cũng là một kết quả" bằng một số 0 mà chưa
    chứng minh được hệ biết trả ra số khác 0 là nghiệm thu chính cái lỗi W1 sửa.
    """
    response = runtime.run(
        "Có bao nhiêu listing của thương hiệu Bibica tại shop "
        '"Richy - Chi nhánh Miền Nam" tại Việt Nam ngày 03/07?',
    )
    assert response.gate.action == "allow"
    values = {item.metric: item.value for item in response.evidence}
    assert 0 in values.values()


def test_a_misspelled_brand_is_refused_not_widened(runtime):
    """Bibika → abstain · A-VALUE-NOT-FOUND, KHÔNG nới thành "tất cả brand".

    Đây là lỗ A4-R5 thứ hai: cùng câu hỏi đi lối analytical_query (không phải
    open_analytical) từng lọt qua vòng dò và trả về đếm trên TOÀN BỘ brand.
    """
    response = runtime.run(
        "Có bao nhiêu listing của thương hiệu Bibika tại Việt Nam ngày 03/07?",
    )
    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A-VALUE-NOT-FOUND"


# --- schema v2 loader ------------------------------------------------------

def test_a_v1_index_is_rejected_by_the_v2_loader(tmp_path, monkeypatch):
    """Chỉ mục v1 (list) nạp bằng loader v2 (dict) phải ra ``{}``, không phải
    một index đọc list thành iterable của ký tự rồi bind literal một chữ cái."""
    v1 = {
        "schema_version": "value-index.v1",
        "values": {"dim.brand": {"vn": ["bibica", "richy"]}},
    }
    path = tmp_path / "value_index.json"
    path.write_text(json.dumps(v1), encoding="utf-8")
    monkeypatch.setattr(value_probe, "VALUE_INDEX_PATH", path)
    value_probe._payload.cache_clear()
    try:
        assert value_probe._index() == {}
        assert value_probe.original_of("dim.brand", "vn", "bibica") is None
    finally:
        value_probe._payload.cache_clear()


# --- preflight -------------------------------------------------------------

def test_a_version_mismatched_index_fails_the_preflight(tmp_path, monkeypatch):
    """Chỉ mục lệch dataset_version là thông tin SAI, không phải thiếu —
    ``AgentRuntime.__init__`` phải nổ, không im lặng bỏ qua."""
    stale = {
        "schema_version": value_probe.INDEX_SCHEMA_VERSION,
        "dataset_version": "0000000000000000",
        "values": {},
        "ambiguous": {},
    }
    path = tmp_path / "value_index.json"
    path.write_text(json.dumps(stale), encoding="utf-8")
    monkeypatch.setattr(value_probe, "VALUE_INDEX_PATH", path)
    with pytest.raises(DatasetVersionError):
        AgentRuntime()


def test_a_wrong_schema_index_fails_the_preflight(tmp_path, monkeypatch):
    """§2.5: thiếu file → im lặng; có file mà schema sai → nổ. Loader trả ``{}``
    cho schema sai là hành vi RUNTIME đã dựng xong; lúc DỰNG thì một file có mặt
    nhưng không đọc được chính là cấu hình hỏng."""
    path = tmp_path / "value_index.json"
    path.write_text(json.dumps({"schema_version": "value-index.v1"}), encoding="utf-8")
    monkeypatch.setattr(value_probe, "VALUE_INDEX_PATH", path)
    with pytest.raises(DatasetVersionError):
        value_probe.assert_index_matches("whatever")


def test_a_missing_index_keeps_the_quiet_skip(tmp_path, monkeypatch):
    monkeypatch.setattr(value_probe, "VALUE_INDEX_PATH", tmp_path / "absent.json")
    value_probe.assert_index_matches("whatever")  # không raise


# --- zero-row: verified vs unverified --------------------------------------

def _brand_filter_plan(brand_value: str, extra: tuple[Predicate, ...] = ()) -> LogicalQueryPlan:
    output = (
        OutputField(name="brand", type="string", semantic_ref="dim.brand"),
        OutputField(name="rating", type="number", semantic_ref="measure.rating"),
    )
    return LogicalQueryPlan(
        plan_id=f"open:value_binding:{brand_value}",
        time_scope=("2026-07-03",), output_node="n3", requested_output_shape=output,
        nodes=(
            PlanNode(node_id="n1", op="Scan", source="products_clean.csv",
                     refs=("dim.brand", "measure.rating"), input_grain="listing_snapshot",
                     output_grain="listing_snapshot", expected_schema=output,
                     expected_cardinality="<=3341"),
            PlanNode(node_id="n2", op="Filter", inputs=("n1",), predicates=(
                Predicate(ref="dim.country", op="eq", parameter="country", value="vn"),
                Predicate(ref="dim.date", op="eq", parameter="date", value="2026-07-03"),
                Predicate(ref="dim.brand", op="eq", parameter="brand", value=brand_value),
                *extra,
            ), input_grain="listing_snapshot", output_grain="listing_snapshot",
                expected_schema=output, expected_cardinality="0"),
            PlanNode(node_id="n3", op="Project", inputs=("n2",), refs=("dim.brand", "measure.rating"),
                     input_grain="listing_snapshot", output_grain="listing_snapshot",
                     expected_schema=output, expected_cardinality="0"),
        ),
    )


class _InjectedPlanner:
    provider, model, prompt_version = "test", "value-binding", "p8-test"

    def __init__(self, plan: LogicalQueryPlan):
        self._plan = plan

    def plan_analytical(self, payload):
        return self._plan.model_dump(mode="json")


def test_an_unverified_zero_row_is_refused(tmp_path):
    """Literal chưa verified + zero-row → abstain · A-EMPTY-RESULT-UNVERIFIED.

    Cửa sau "empty_result thì miễn kiểm" đã đóng: một số 0 sinh ra từ một
    literal không tồn tại trong value index không phải là một kết quả.
    """
    plan = _brand_filter_plan("__brand_does_not_exist__")
    runtime = AgentRuntime(trace_dir=tmp_path, llm_client=_InjectedPlanner(plan))
    response = runtime.run("Rating theo brand không tồn tại tại VN")
    assert response.gate.action == "abstain"
    assert response.gate.rule_id == "A-EMPTY-RESULT-UNVERIFIED"
    assert response.evidence == []
    fired = response.planning["empty_result"]["handler_fired"]
    assert fired == {"zero_row_relaxed": False, "filter_literal": True}
    # Không chữ số trong câu từ chối — verifier.scan_numbers (CLAUDE.md §3.1).
    assert not any(char.isdigit() for char in response.gate.reason)


def test_a_verified_zero_row_is_still_a_result(tmp_path):
    """Mọi literal verified + zero-row → allow: đây mới là "không có kết quả
    cũng là một kết quả". Predicate số (rating > mức không tồn tại) không phải
    "giá trị dữ liệu" nên không cần chỉ mục chứng minh."""
    plan = _brand_filter_plan(
        "Bibica",
        extra=(Predicate(ref="measure.rating", op="gt", parameter="rating_floor", value=6),),
    )
    runtime = AgentRuntime(trace_dir=tmp_path, llm_client=_InjectedPlanner(plan))
    response = runtime.run("Rating theo brand không tồn tại tại VN")
    assert response.gate.action == "allow"
    assert len(response.evidence) == 1
    assert response.evidence[0].metric == "result_count"
    assert response.evidence[0].value == 0
    attrs = response.evidence[0].attrs
    assert attrs["executed_predicate_count"] == attrs["planned_predicate_count"] == 4
    assert dict(attrs["filter_bindings"])["dim.brand"] is True
    assert attrs["relaxed_filters"] is False
    fired = response.planning["empty_result"]["handler_fired"]
    assert fired == {"zero_row_relaxed": False, "filter_literal": False}


# --- chỉ mục tự nhất quán ---------------------------------------------------

def test_the_index_round_trips_every_key():
    """``_fold(original) == folded`` cho MỌI khoá — chỉ mục tự nhất quán, và
    ``original_of`` không bao giờ trả một chuỗi không thuộc dataset."""
    index = value_probe._index()
    if not index:
        pytest.skip("artifacts/value_index.json chưa dựng")
    for ref, per_country in index.items():
        for country, mapping in per_country.items():
            for folded, original in mapping.items():
                assert value_probe._fold(original) == folded, (ref, country, original)
                assert value_probe.original_of(ref, country, folded) == original


def test_the_index_matches_the_repository_dataset_version():
    if not value_probe.index_is_available():
        pytest.skip("artifacts/value_index.json chưa dựng")
    assert value_probe.index_dataset_version() == compute_dataset_version(
        Path(DATA_DIR),
    )
