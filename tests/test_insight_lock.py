"""Build lock — ultimate solution §12.1, step 1.

Without a lock, two concurrent builds each stage a bundle, each find the
destination absent, and both rename. Which one survives is then decided by a
race, and immutability is exactly what every downstream reader trusts.

The builder docstring claimed this lock existed before the lock did, which is
worse than the missing feature: a false claim about a safety property is one
nobody re-checks.
"""
from __future__ import annotations

import os
import time

import pandas as pd
import pytest

from gladiators.insights.builder import write_bundle
from gladiators.insights.lock import BuildLock, InsightLockError
from tests.test_insight_builder import card, evidence, scorecard


def build(root, dataset_version="ds-1", **overrides):
    kwargs = dict(
        scorecard=scorecard(dataset_version=dataset_version), cards=[card()],
        evidence=[evidence()], as_of_date="2026-07-03",
        source_files={"products_clean.csv": "abc"}, parameters={"top_k": 5},
    )
    kwargs.update(overrides)
    return write_bundle(root, dataset_version, **kwargs)


# --- mutual exclusion -----------------------------------------------------

def test_a_second_builder_is_refused_while_one_holds_the_lock(tmp_path):
    with BuildLock(tmp_path, "ds-1"):
        with pytest.raises(InsightLockError) as excinfo:
            BuildLock(tmp_path, "ds-1").acquire()
    assert excinfo.value.code == "INSIGHT_BUILD_LOCKED"


def test_different_dataset_versions_do_not_block_each_other(tmp_path):
    """The lock is per dataset version; unrelated builds must not serialise."""
    with BuildLock(tmp_path, "ds-1"):
        with BuildLock(tmp_path, "ds-2"):
            pass


def test_the_lock_is_released_on_exit(tmp_path):
    with BuildLock(tmp_path, "ds-1"):
        pass
    BuildLock(tmp_path, "ds-1").acquire().release()


def test_the_lock_is_released_even_when_the_build_raises(tmp_path):
    lock = BuildLock(tmp_path, "ds-1")
    with pytest.raises(RuntimeError):
        with lock:
            raise RuntimeError("build hỏng")
    BuildLock(tmp_path, "ds-1").acquire().release()


def test_a_directory_is_the_lock_not_a_flag_file(tmp_path):
    """``mkdir`` is atomic; check-then-create is the race being prevented."""
    lock = BuildLock(tmp_path, "ds-1").acquire()
    assert lock.path.is_dir()
    lock.release()
    assert not lock.path.exists()


# --- stale locks ----------------------------------------------------------

def test_a_stale_lock_is_broken_and_the_break_is_recorded(tmp_path):
    """A routinely stale lock means builds are crashing -- that is the finding."""
    abandoned = BuildLock(tmp_path, "ds-1").acquire()
    old = time.time() - 7200
    os.utime(abandoned.path, (old, old))

    fresh = BuildLock(tmp_path, "ds-1", stale_after_s=3600).acquire()
    assert fresh.broke_stale_lock is True
    fresh.release()


def test_a_fresh_lock_is_never_broken(tmp_path):
    held = BuildLock(tmp_path, "ds-1").acquire()
    with pytest.raises(InsightLockError):
        BuildLock(tmp_path, "ds-1", stale_after_s=3600).acquire()
    held.release()


def test_waiting_acquires_once_the_holder_releases(tmp_path):
    holder = BuildLock(tmp_path, "ds-1").acquire()
    holder.release()
    waiter = BuildLock(tmp_path, "ds-1", timeout_s=1.0).acquire()
    waiter.release()


# --- integration with the builder ----------------------------------------

def test_write_bundle_takes_the_lock(tmp_path):
    holder = BuildLock(tmp_path, "ds-1").acquire()
    try:
        with pytest.raises(InsightLockError) as excinfo:
            build(tmp_path)
        assert excinfo.value.code == "INSIGHT_BUILD_LOCKED"
    finally:
        holder.release()


def test_write_bundle_releases_the_lock_afterwards(tmp_path):
    build(tmp_path)
    assert not (tmp_path / ".lock-ds-1").exists()
    BuildLock(tmp_path, "ds-1").acquire().release()


def test_a_failed_build_still_releases_the_lock(tmp_path):
    from gladiators.insights.builder import InsightBuildError

    with pytest.raises(InsightBuildError):
        build(tmp_path, scorecard=scorecard().drop(columns=["pam_score"]))
    assert not (tmp_path / ".lock-ds-1").exists()


def test_the_lock_directory_is_not_mistaken_for_a_bundle(tmp_path):
    """``latest_bundle_dir`` scans this root; a lock must not look like a bundle."""
    from gladiators.insights.repository import latest_bundle_dir

    build(tmp_path)
    holder = BuildLock(tmp_path, "ds-2").acquire()
    try:
        assert latest_bundle_dir(tmp_path).name == "ds-1"
    finally:
        holder.release()
