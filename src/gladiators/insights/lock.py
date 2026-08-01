"""Build lock — ultimate solution §12.1, step 1.

One builder per ``dataset_version`` at a time.  Without it two concurrent builds
each stage a bundle, each find the destination absent, and both rename -- on
Windows the second rename fails with a bare OSError, and on POSIX the second
silently replaces the first. Either way the immutability guarantee that every
downstream reader depends on was decided by a race.

The lock is a directory, not a file. ``mkdir`` is atomic on every filesystem
this runs on, whereas "check then create" is exactly the race being prevented.

A stale lock (a builder that crashed) is broken only after ``stale_after``, and
breaking one is logged rather than silent: if a lock is routinely stale, the
builds are failing and that is the thing to fix.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_STALE_AFTER_S = 3600.0
DEFAULT_TIMEOUT_S = 0.0


class InsightLockError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class BuildLock:
    """Cooperative inter-process lock keyed by dataset version."""

    def __init__(
        self, root: str | Path, dataset_version: str, *,
        stale_after_s: float = DEFAULT_STALE_AFTER_S,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        poll_s: float = 0.25,
    ):
        self.root = Path(root)
        self.dataset_version = dataset_version
        self.path = self.root / f".lock-{dataset_version}"
        self.stale_after_s = stale_after_s
        self.timeout_s = timeout_s
        self.poll_s = poll_s
        self.broke_stale_lock = False
        self._held = False

    def acquire(self) -> "BuildLock":
        self.root.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout_s
        while True:
            try:
                # Atomic on every supported filesystem, unlike check-then-create.
                self.path.mkdir()
                self._held = True
                self._write_owner()
                return self
            except FileExistsError:
                if self._break_if_stale():
                    continue
                if time.monotonic() >= deadline:
                    raise InsightLockError(
                        "INSIGHT_BUILD_LOCKED",
                        f"Một build khác đang chạy cho dataset_version "
                        f"{self.dataset_version}. Không chạy song song hai builder "
                        "vì tính bất biến của bundle sẽ do một cuộc đua quyết định.",
                    ) from None
                time.sleep(self.poll_s)

    def release(self) -> None:
        if not self._held:
            return
        try:
            (self.path / "owner.json").unlink(missing_ok=True)
            self.path.rmdir()
        except OSError:
            pass
        self._held = False

    def __enter__(self) -> "BuildLock":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()

    # -- internals ---------------------------------------------------------

    def _write_owner(self) -> None:
        try:
            (self.path / "owner.json").write_text(
                json.dumps({
                    "pid": os.getpid(),
                    "dataset_version": self.dataset_version,
                    "acquired_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            # An unwritable owner file does not invalidate the lock itself; the
            # directory is the lock, this is only for diagnosing a stale one.
            pass

    def _break_if_stale(self) -> bool:
        try:
            age = time.time() - self.path.stat().st_mtime
        except OSError:
            return True  # vanished between the mkdir failure and here
        if age < self.stale_after_s:
            return False
        try:
            (self.path / "owner.json").unlink(missing_ok=True)
            self.path.rmdir()
        except OSError:
            return False
        # Recorded rather than silent: a routinely stale lock means builds are
        # crashing, and that is the problem worth surfacing.
        self.broke_stale_lock = True
        return True
