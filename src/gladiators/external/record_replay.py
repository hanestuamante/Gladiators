"""Record and replay for live search — ultimate solution §16 P12.

A live provider cannot be part of a regression suite: it is rate-limited,
costs money, and returns different results tomorrow.  So a controlled recording
is taken once and replayed deterministically afterwards.

The design turns on one distinction that is easy to get wrong: **a replay miss
must be an error, not a fallback to the network.** A replay suite that quietly
reaches the internet when a cassette is absent stops being a regression test the
moment anyone adds a case, and nothing about the passing run would say so.

Cassette keys are content hashes of the query, so a changed query is a different
cassette rather than a stale hit -- the same reasoning as everywhere else in this
codebase: a lookup that silently returns the wrong thing is worse than one that
fails.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .search_contracts import SearchQuery, SearchResponse

CASSETTE_SCHEMA_VERSION = "search-cassette.v1"


class ReplayMiss(RuntimeError):
    """No cassette for this query. Terminal by design."""

    code = "SEARCH_REPLAY_MISS"

    def __init__(self, key: str, query: str):
        super().__init__(
            f"{self.code}: chưa có cassette cho query '{query}' (key={key}). "
            "Replay không được phép gọi mạng để bù."
        )
        self.key = key
        self.query = query


def cassette_key(query: SearchQuery, *, max_results: int = 5) -> str:
    """Content hash of everything that changes the answer.

    ``recency_days`` is included because it changes the request window; a run
    date is not, because a cassette recorded yesterday must still replay today.
    """
    payload = {
        "query": query.query,
        # Market is part of the key: the same words asked of the VN and ID
        # markets are two different questions with two different answers.
        "market": getattr(query, "market", None),
        "purpose": getattr(query, "purpose", None),
        "recency_days": getattr(query, "recency_days", None),
        "max_results": max_results,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:20]


class CassetteStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def path_for(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def has(self, key: str) -> bool:
        return self.path_for(key).exists()

    def read(self, key: str) -> dict[str, Any] | None:
        path = self.path_for(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def write(self, key: str, response: SearchResponse, query: SearchQuery) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": CASSETTE_SCHEMA_VERSION,
            "key": key,
            "query": query.model_dump(mode="json"),
            "response": response.model_dump(mode="json"),
            # Metadata only. Never part of the key, or a cassette would expire.
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        path = self.path_for(key)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def keys(self) -> tuple[str, ...]:
        if not self.root.exists():
            return ()
        return tuple(sorted(p.stem for p in self.root.glob("*.json")))


class RecordingSearchProvider:
    """Delegates to a real provider and saves what came back."""

    provider_id = "recording"

    def __init__(self, inner, store: CassetteStore, *, overwrite: bool = False):
        self.inner = inner
        self.store = store
        self.overwrite = overwrite
        self.recorded: list[str] = []

    def search(self, query: SearchQuery, *, max_results: int = 5,
               timeout_s: float = 10.0) -> SearchResponse:
        key = cassette_key(query, max_results=max_results)
        if not self.overwrite and self.store.has(key):
            return _response_from(self.store.read(key))
        response = self.inner.search(query, max_results=max_results, timeout_s=timeout_s)
        self.store.write(key, response, query)
        self.recorded.append(key)
        return response


class ReplaySearchProvider:
    """Serves only from cassettes. A miss raises rather than reaching out."""

    provider_id = "replay"

    def __init__(self, store: CassetteStore):
        self.store = store
        self.served: list[str] = []

    def search(self, query: SearchQuery, *, max_results: int = 5,
               timeout_s: float = 10.0) -> SearchResponse:
        key = cassette_key(query, max_results=max_results)
        payload = self.store.read(key)
        if payload is None:
            # Falling back to the network here would silently turn a regression
            # suite into a live integration test, and the passing run would
            # look identical.
            raise ReplayMiss(key, query.query)
        self.served.append(key)
        return _response_from(payload)


def _response_from(payload: dict[str, Any]) -> SearchResponse:
    return SearchResponse.model_validate(payload["response"])


def verify_determinism(provider: ReplaySearchProvider, queries, *, runs: int = 3) -> dict:
    """Replay N times and assert the content hash never moves (§16 P12).

    Comparing content hashes rather than object equality is deliberate: the
    hash is what the cache and the trace key off, so that is what must be stable.
    """
    observed: dict[str, set[str]] = {}
    for _ in range(runs):
        for query in queries:
            response = provider.search(query)
            observed.setdefault(query.query, set()).add(response.content_hash)
    unstable = {q: sorted(h) for q, h in observed.items() if len(h) > 1}
    return {
        "runs": runs,
        "queries": len(observed),
        "stable": not unstable,
        "unstable": unstable,
    }
