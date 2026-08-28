"""Bản dữ liệu là một artifact CÓ TÊN — Spec bổ sung 28/08.

Ba vấn đề tưởng riêng biệt hoá ra là một: notebook phải bấm tay, server phải dựng
lại, và ``dataset_version`` từng khai sai xuất xứ. Cả ba đều bắt nguồn từ chỗ
**không ai đặt tên cho bản dữ liệu**, nên không có gì để CI gọi, để đổi con trỏ
tới, hay để rollback về.
"""
from __future__ import annotations

import json
import shutil

import pandas as pd
import pytest

from gladiators.data import versions
from gladiators.data.coverage import write_manifest
from gladiators.data.repository import ArtifactRepository

QUESTION = "Có bao nhiêu listing tại Việt Nam ngày 03/07?"


@pytest.fixture
def built(tmp_path):
    """Một thư mục dữ liệu hợp lệ, chép từ bản đang chạy."""
    root = tmp_path / "built"
    shutil.copytree("data/processed", root)
    return root


@pytest.fixture
def data_root(tmp_path):
    return tmp_path / "data"


def _variant(source, target, drop: int = 100):
    shutil.copytree(source, target)
    for name in ("products_clean.csv", "product_snapshot_metrics.csv"):
        frame = pd.read_csv(target / name, low_memory=False)
        rows = frame[
            (frame.country_code == "vn") & (frame.date.astype(str) == "2026-07-03")
        ]
        frame.drop(rows.index[:drop]).to_csv(target / name, index=False)
    write_manifest(target)
    return target


def test_the_version_id_is_a_function_of_the_bytes(built, tmp_path):
    """Cùng nội dung ⇒ cùng id; đổi một dòng ⇒ đổi id. Nếu không, "bản dữ liệu"
    chỉ là một cái tên tuỳ tiện."""
    first = versions.compute_version_id(built)
    twin = tmp_path / "twin"
    shutil.copytree(built, twin)
    assert versions.compute_version_id(twin) == first

    changed = _variant(built, tmp_path / "changed")
    assert versions.compute_version_id(changed) != first


def test_publishing_twice_does_not_duplicate(built, data_root):
    one = versions.publish(built, data_root)
    two = versions.publish(built, data_root)
    assert one.version_id == two.version_id
    assert len(versions.list_versions(data_root)) == 1


def test_a_published_version_carries_its_provenance(built, data_root):
    version = versions.publish(built, data_root, raw_snapshot="data/raw", notes="thử")
    manifest = versions.read_manifest(version.root)
    assert manifest["version_id"] == version.version_id
    # Thiếu nguồn raw thì bản này không tái lập được, và một bản không tái lập
    # được là một giai thoại.
    assert manifest["raw_snapshot"] == "data/raw"
    assert manifest["built_at"] and manifest["artifacts"]


def test_tampering_with_a_published_version_is_detected(built, data_root):
    """Bất biến phải là điều KIỂM ĐƯỢC, không phải một quy ước."""
    version = versions.publish(built, data_root)
    assert versions.verify(version.root) == ()

    target = version.root / "products_clean.csv"
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert "products_clean.csv" in versions.verify(version.root)

    with pytest.raises(versions.DatasetVersionError):
        versions.switch(data_root, version.version_id)


def test_the_pointer_selects_which_version_is_served(built, data_root, tmp_path):
    first = versions.publish(built, data_root).version_id
    second = versions.publish(_variant(built, tmp_path / "v2"), data_root).version_id

    versions.switch(data_root, first)
    assert versions.current_version_id(data_root) == first
    assert ArtifactRepository(data_root).dataset_version == first

    versions.switch(data_root, second)
    assert ArtifactRepository(data_root).dataset_version == second


def test_a_pointer_to_a_missing_version_fails_loudly(data_root):
    data_root.mkdir(parents=True, exist_ok=True)
    versions.pointer_path(data_root).write_text("khong-ton-tai\n", encoding="utf-8")
    with pytest.raises(versions.DatasetVersionError):
        versions.resolve(data_root)


def test_reload_swaps_the_data_without_restarting_the_process(built, data_root, tmp_path):
    """Đây là phép kiểm mà cả WP này tồn tại để đạt: đổi dữ liệu **trong một tiến
    trình**, và nhãn phiên bản đi theo."""
    from gladiators.agent.workflow import AgentRuntime
    from gladiators.planner.plan_cache import PLAN_RESULT_CACHE

    first = versions.publish(built, data_root).version_id
    second = versions.publish(_variant(built, tmp_path / "v2"), data_root).version_id

    PLAN_RESULT_CACHE.clear()
    versions.switch(data_root, first)
    runtime = AgentRuntime(data_dir=str(data_root))
    before = runtime.run(QUESTION)

    versions.switch(data_root, second)
    assert runtime.reload() == second
    after = runtime.run(QUESTION)

    assert after.evidence[0].value != before.evidence[0].value
    assert after.evidence[0].dataset_version == second

    versions.switch(data_root, first)
    runtime.reload()
    rolled_back = runtime.run(QUESTION)
    assert rolled_back.evidence[0].value == before.evidence[0].value


def test_reload_clears_the_plan_cache(built, data_root, tmp_path):
    """Khoá cache là ``(plan_hash, dataset_version)``. Không xoá thì một mục cũ
    vẫn khớp khoá khi hai bản tình cờ cùng version, và nửa dữ liệu cũ sống sót
    qua lần nạp lại."""
    from gladiators.agent.workflow import AgentRuntime
    from gladiators.planner.plan_cache import PLAN_RESULT_CACHE

    versions.switch(data_root, versions.publish(built, data_root).version_id)
    runtime = AgentRuntime(data_dir=str(data_root))
    runtime.run(QUESTION)
    PLAN_RESULT_CACHE.put("h", "v", type("R", (), {
        "frame": None, "row_count": 0, "rank_tie_at_cut": False,
    })())
    runtime.reload()
    assert PLAN_RESULT_CACHE.stats()["size"] == 0


def test_a_plain_directory_still_works_unchanged():
    """Thay đổi hạ tầng bắt mọi người sửa lệnh ngay hôm đó là thay đổi không ai
    áp dụng. ``data/processed`` phải chạy y như cũ."""
    repo = ArtifactRepository("data/processed")
    assert len(repo.products) > 0
    assert repo.dataset_version


# --- kho raw bất biến ---------------------------------------------------------

def test_an_ingested_raw_drop_is_immutable_and_stamped(tmp_path):
    import sys
    sys.path.insert(0, "scripts")
    from ingest_raw import WATERMARK_NAME, ingest, verify

    source = tmp_path / "drop"
    source.mkdir()
    (source / "a.csv").write_text("x\n1\n", encoding="utf-8")

    data_root = tmp_path / "data"
    mark = ingest(source, data_root, label="thử")
    snapshot = data_root / "raw_snapshots" / mark["snapshot_id"]

    assert mark["file_count"] == 1 and mark["ingested_at"]
    assert (snapshot / WATERMARK_NAME).exists()
    assert verify(snapshot) == ()

    (snapshot / "a.csv").write_text("x\n2\n", encoding="utf-8")
    assert verify(snapshot) == ("a.csv",)


def test_ingesting_the_same_snapshot_id_twice_is_refused(tmp_path):
    import sys
    sys.path.insert(0, "scripts")
    from ingest_raw import ingest

    source = tmp_path / "drop"
    source.mkdir()
    (source / "a.csv").write_text("x\n", encoding="utf-8")
    data_root = tmp_path / "data"
    ingest(source, data_root, ingested_at="20260828T000000Z")
    with pytest.raises(FileExistsError):
        ingest(source, data_root, ingested_at="20260828T000000Z")
