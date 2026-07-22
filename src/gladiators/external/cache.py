"""Immutable content-addressed cache and local daily quota guard."""
from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .search_contracts import SearchResponse
from .search_provider import response_content_hash, response_core


class CacheIntegrityError(RuntimeError):
    pass


class CacheEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_id: str
    retrieved_at: datetime
    byte_size: int = Field(ge=0)
    media_type: str = "application/json"
    quarantined: bool = False
    quarantine_reason: str | None = None


class CacheManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.0"
    entries: tuple[CacheEntry, ...] = ()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


class ExternalCache:
    def __init__(self, root: str | Path = "data/external_cache"):
        self.root = Path(root)
        self.manifest_path = self.root / "manifest.json"
        self._lock = threading.Lock()

    def _path(self, content_hash: str) -> Path:
        if len(content_hash) != 64 or any(ch not in "0123456789abcdef" for ch in content_hash):
            raise ValueError("content_hash không hợp lệ.")
        return self.root / "sha256" / content_hash[:2] / f"{content_hash}.json"

    def _manifest(self) -> CacheManifest:
        if not self.manifest_path.exists():
            return CacheManifest()
        return CacheManifest.model_validate_json(self.manifest_path.read_text(encoding="utf-8"))

    def write(self, response: SearchResponse) -> SearchResponse:
        expected = response_content_hash(response_core(response))
        if response.content_hash != expected:
            raise CacheIntegrityError("SearchResponse content_hash không khớp normalized payload.")
        path = self._path(expected)
        stored = response.model_copy(update={"cache_path": str(path)})
        encoded = json.dumps(stored.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        with self._lock:
            if path.exists():
                if path.read_text(encoding="utf-8") != encoded:
                    raise CacheIntegrityError("Immutable cache collision: cùng hash nhưng bytes khác.")
            else:
                _atomic_write(path, encoded)
            manifest = self._manifest()
            if expected not in {item.content_hash for item in manifest.entries}:
                entry = CacheEntry(
                    content_hash=expected, source_id=stored.provider,
                    retrieved_at=stored.retrieved_at, byte_size=len(encoded.encode()),
                )
                updated = manifest.model_copy(update={"entries": (*manifest.entries, entry)})
                _atomic_write(
                    self.manifest_path,
                    json.dumps(updated.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                )
        return stored

    def read(self, content_hash: str) -> SearchResponse:
        path = self._path(content_hash)
        response = SearchResponse.model_validate_json(path.read_text(encoding="utf-8"))
        if response.content_hash != content_hash or response_content_hash(response_core(response)) != content_hash:
            raise CacheIntegrityError("Cache hash verification thất bại.")
        return response

    def find(self, query, provider: str | None = None) -> SearchResponse | None:
        """Find newest immutable response for an exact typed query; never fetches."""
        for entry in reversed(self._manifest().entries):
            if provider is not None and entry.source_id != provider:
                continue
            response = self.read(entry.content_hash)
            if response.query == query:
                return response
        return None

    def quarantine(self, response: SearchResponse, reason: str) -> Path:
        path = self.root / "quarantine" / f"{response.content_hash}.json"
        payload = {
            "content_hash": response.content_hash, "reason": reason,
            "quarantined_at": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_write(path, json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        return path


class QuotaGuard:
    def __init__(self, path: str | Path, daily_limit: int = 150):
        if daily_limit < 1:
            raise ValueError("daily_limit phải >= 1.")
        self.path = Path(path)
        self.daily_limit = daily_limit
        self._lock = threading.Lock()

    def _state(self, today: date) -> dict:
        if not self.path.exists():
            return {"date": today.isoformat(), "used": 0, "daily_limit": self.daily_limit}
        state = json.loads(self.path.read_text(encoding="utf-8"))
        if state.get("date") != today.isoformat():
            return {"date": today.isoformat(), "used": 0, "daily_limit": self.daily_limit}
        return state

    def used(self, today: date | None = None) -> int:
        return int(self._state(today or datetime.now(timezone.utc).date())["used"])

    def exhausted(self, cost: int = 1, today: date | None = None) -> bool:
        if cost < 1:
            raise ValueError("quota cost phải >= 1.")
        return self.used(today) + cost > self.daily_limit

    def consume(self, cost: int = 1, today: date | None = None) -> int:
        if cost < 1:
            raise ValueError("quota cost phải >= 1.")
        current_date = today or datetime.now(timezone.utc).date()
        with self._lock:
            state = self._state(current_date)
            if int(state["used"]) + cost > self.daily_limit:
                raise RuntimeError("live search quota exhausted")
            state["used"] = int(state["used"]) + cost
            state["daily_limit"] = self.daily_limit
            _atomic_write(self.path, json.dumps(state, sort_keys=True, indent=2) + "\n")
            return int(state["used"])
