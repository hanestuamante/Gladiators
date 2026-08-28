"""Dữ liệu phải có MỘT danh tính trong một tiến trình.

Lỗi đã đo được, và là lý do file này tồn tại: sửa CSV trên đĩa giữa hai lần hỏi
thì con số đổi **668 → 568** trong khi ``dataset_version`` vẫn đứng ở
``27de9bff…`` — bản mà ở đó đáp án là 668. Evidence khai một **xuất xứ sai**.

Nguyên nhân gốc: một tiến trình có HAI vòng đời cho cùng một dữ liệu.
``ArtifactRepository.read()`` không cache (nên ``QueryExecutor`` đọc lại đĩa mỗi
truy vấn), còn ``products``/``dataset_version`` là ``cached_property``. Cái nào
"mới" tuỳ tầng, nên chúng trôi khỏi nhau.

Bất biến mà bộ test này khoá lại: **con số và nhãn phiên bản luôn đến từ cùng một
bộ byte.**
"""
from __future__ import annotations

import json
import shutil

import pandas as pd
import pytest

from gladiators.data.repository import MANIFEST_NAME, ArtifactRepository

QUESTION = "Có bao nhiêu listing tại Việt Nam ngày 03/07?"


@pytest.fixture
def snapshot(tmp_path):
    root = tmp_path / "processed"
    shutil.copytree("data/processed", root)
    return root


def _drop_rows(root, count: int = 100) -> None:
    """Xoá thật vài dòng khỏi CSV trên đĩa, KHÔNG động vào tiến trình."""
    for name in ("products_clean.csv", "product_snapshot_metrics.csv"):
        frame = pd.read_csv(root / name, low_memory=False)
        target = frame[
            (frame.country_code == "vn") & (frame.date.astype(str) == "2026-07-03")
        ]
        frame.drop(target.index[:count]).to_csv(root / name, index=False)


def test_a_repository_is_one_snapshot_for_its_whole_life(snapshot):
    repo = ArtifactRepository(snapshot)
    before, version = len(repo.products), repo.dataset_version

    _drop_rows(snapshot)

    # Đọc lại qua CHÍNH object đó: phải thấy đúng ảnh chụp cũ. Nếu read() không
    # cache, dòng dưới thấy dữ liệu mới trong khi dataset_version vẫn là cũ.
    assert len(repo.read("products_clean.csv")) == before
    assert len(repo.products) == before
    assert repo.dataset_version == version


def test_a_new_repository_sees_the_new_data_and_a_new_version(snapshot):
    old = ArtifactRepository(snapshot)
    before, old_version = len(old.products), old.dataset_version

    _drop_rows(snapshot)

    fresh = ArtifactRepository(snapshot)
    assert len(fresh.products) < before
    assert fresh.dataset_version != old_version, (
        "dữ liệu đổi mà nhãn phiên bản không đổi ⇒ evidence khai xuất xứ sai"
    )


def test_the_answer_and_its_version_stamp_never_disagree(snapshot):
    """Kiểm ở tầng HÀNH VI, không ở tầng repository.

    Đây là phép kiểm thật sự quan trọng: người đọc không nhìn ``ArtifactRepository``,
    họ nhìn một con số kèm một nhãn phiên bản.
    """
    from gladiators.agent.workflow import AgentRuntime
    from gladiators.planner.plan_cache import PLAN_RESULT_CACHE

    PLAN_RESULT_CACHE.clear()
    runtime = AgentRuntime(data_dir=str(snapshot))
    first = runtime.run(QUESTION)
    assert first.evidence

    _drop_rows(snapshot)
    # Xoá cache kế hoạch: chính bước này đã phơi ra lỗi cũ, vì nó là thứ duy nhất
    # từng che con số mới lại.
    PLAN_RESULT_CACHE.clear()
    second = runtime.run(QUESTION)

    assert second.evidence[0].value == first.evidence[0].value
    assert second.evidence[0].dataset_version == first.evidence[0].dataset_version

    PLAN_RESULT_CACHE.clear()
    reloaded = AgentRuntime(data_dir=str(snapshot)).run(QUESTION)
    assert reloaded.evidence[0].value != first.evidence[0].value
    assert reloaded.evidence[0].dataset_version != first.evidence[0].dataset_version


def test_a_declared_manifest_wins_over_the_derived_hash(snapshot):
    """Phiên bản là thứ ĐƯỢC KHAI, không phải thứ suy ra.

    Băm lại CSV vẫn đúng, nhưng nó không có gì buộc phải khớp với bộ byte mà câu
    trả lời thật sự đọc. Manifest sinh ra CÙNG LÚC với dữ liệu nên nó không lệch
    được.
    """
    derived = ArtifactRepository(snapshot).dataset_version
    (snapshot / MANIFEST_NAME).write_text(
        json.dumps({"version_id": "v-test-0001"}), encoding="utf-8",
    )
    assert ArtifactRepository(snapshot).dataset_version == "v-test-0001" != derived


def test_a_broken_manifest_falls_back_instead_of_crashing(snapshot):
    """Manifest hỏng ⇒ quay về băm lại. Một file JSON cụt không được phép làm
    sập cả hệ khi dữ liệu vẫn đọc được bình thường."""
    derived = ArtifactRepository(snapshot).dataset_version
    (snapshot / MANIFEST_NAME).write_text("{ not json", encoding="utf-8")
    assert ArtifactRepository(snapshot).dataset_version == derived


def test_mutating_a_returned_frame_cannot_poison_the_snapshot(snapshot):
    """``read()`` trả bản copy: một consumer sửa frame tại chỗ sẽ làm mọi consumer
    sau đó thấy một dataset khác dataset đã đóng dấu."""
    repo = ArtifactRepository(snapshot)
    frame = repo.read("products_clean.csv")
    before = len(frame)
    frame.drop(frame.index[:50], inplace=True)
    assert len(repo.read("products_clean.csv")) == before
