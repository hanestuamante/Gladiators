"""Controlled recording for live search — ultimate solution §16 P12.

Takes a small, fixed set of queries against the real provider once and stores
them as cassettes so every later run replays deterministically.

Deliberately small and fixed: a recording sweep that grows with the codebase
turns into an ongoing spend and a moving baseline. The queries below are
context-only lookups -- campaign windows and market events -- which is all §12
permits external search to inform. Nothing recorded here ever enters a
calculation.

    python scripts/record_search_cassettes.py            # record
    python scripts/record_search_cassettes.py --verify   # replay x3, no network
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from gladiators.external.record_replay import (  # noqa: E402
    CassetteStore,
    RecordingSearchProvider,
    ReplayMiss,
    ReplaySearchProvider,
    verify_determinism,
)
from gladiators.external.search_contracts import SearchQuery  # noqa: E402

CASSETTE_DIR = REPO / "artifacts" / "search_cassettes"

# Part of the cassette key, so record and replay must agree on it. They did not
# at first -- recording asked for 3 results and verification for the default 5,
# and replay correctly refused to serve a different request shape rather than
# returning a near match.
MAX_RESULTS = 3

# Fixed set. Context-only purposes; never anything a number depends on.
QUERIES = (
    SearchQuery(query="Shopee 7.7 sale campaign Vietnam 2026", market="vn",
                purpose="campaign_context", recency_days=90),
    SearchQuery(query="Shopee Indonesia promo 7.7 2026", market="id",
                purpose="campaign_context", recency_days=90),
    SearchQuery(query="Vietnam e-commerce market event July 2026", market="vn",
                purpose="market_event", recency_days=90),
    # Ba query dưới đây thêm ngày 27/08/2026 để đạt mốc §A12.3 (≥6 cassette đã
    # duyệt). Vẫn đúng phạm vi cũ: chỉ campaign_context và market_event, tức chỉ
    # những thứ §12 cho phép nguồn ngoài soi sáng. Không query nào ở đây chạm tới
    # một con số mà câu trả lời phụ thuộc vào.
    SearchQuery(query="Indonesia e-commerce market event July 2026", market="id",
                purpose="market_event", recency_days=90),
    SearchQuery(query="Shopee 8.8 sale campaign Vietnam 2026", market="vn",
                purpose="campaign_context", recency_days=90),
    SearchQuery(query="Shopee Indonesia kampanye 8.8 2026", market="id",
                purpose="campaign_context", recency_days=90),
)


def record() -> int:
    from gladiators.external.search_provider import TavilyProvider

    store = CassetteStore(CASSETTE_DIR)
    try:
        provider = RecordingSearchProvider(TavilyProvider(), store)
    except RuntimeError as error:
        print(f"SKIP: {error}")
        return 0

    for query in QUERIES:
        try:
            response = provider.search(query, max_results=MAX_RESULTS)
        except Exception as error:  # provider outage is a recording concern only
            print(f"  FAIL  {query.query[:44]!r}: {type(error).__name__}: {error}")
            continue
        print(f"  ok    {query.query[:44]!r} -> {len(response.items)} kết quả")
    print(f"Cassettes: {len(store.keys())} trong {CASSETTE_DIR.relative_to(REPO)}")
    print(f"Đã ghi mới lần này: {len(provider.recorded)}")
    return 0


MANIFEST_SCHEMA_VERSION = "search-cassette-manifest.v1"


def verify() -> int:
    """Bảy bước, dừng ở lỗi đầu tiên, trả khác 0 — W2 (SolutionSpec2808 §3.3).

    Nhánh "kho rỗng ⇒ SKIP ⇒ 0" cũ bị XOÁ: CI xanh trên một kho rỗng là chính
    khoảng trống W2 tồn tại để đóng — ba khẳng định của bản bàn giao (replay
    6/6, chạy khi chặn socket, guard sạch) không tái lập được từ checkout.
    """
    import hashlib

    from gladiators.external.injection_guard import sanitize_and_check
    from gladiators.external.record_replay import (
        CASSETTE_SCHEMA_VERSION,
        cassette_key,
    )

    # 1 · manifest tồn tại, đúng schema.
    manifest_path = CASSETTE_DIR / "MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("FAIL MANIFEST_MISSING: không đọc được MANIFEST.json.")
        return 1
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        print("FAIL MANIFEST_MISSING: schema_version không khớp.")
        return 1

    # 2 · tập key của QUERIES == tập key trong manifest.
    expected_keys = {cassette_key(q, max_results=MAX_RESULTS) for q in QUERIES}
    manifest_keys = {entry["key"] for entry in manifest.get("cassettes", ())}
    if expected_keys != manifest_keys:
        print("FAIL QUERY_SET_MISMATCH: "
              f"thiếu {sorted(expected_keys - manifest_keys)}, "
              f"thừa {sorted(manifest_keys - expected_keys)}.")
        return 1

    for entry in manifest["cassettes"]:
        path = CASSETTE_DIR / f"{entry['key']}.json"
        # 3 · file có mặt trên đĩa.
        if not path.exists():
            print(f"FAIL CASSETTE_MISSING: {entry['key']}")
            return 1
        payload_bytes = path.read_bytes()
        # 4 · parse được, đúng schema.
        try:
            payload = json.loads(payload_bytes)
        except json.JSONDecodeError:
            print(f"FAIL CASSETTE_SCHEMA: {entry['key']} không parse được.")
            return 1
        if payload.get("schema_version") != CASSETTE_SCHEMA_VERSION:
            print(f"FAIL CASSETTE_SCHEMA: {entry['key']} schema_version lệch.")
            return 1
        # 5 · hash file khớp manifest.
        if hashlib.sha256(payload_bytes).hexdigest()[:16] != entry["sha256_16"]:
            print(f"FAIL CASSETTE_HASH: {entry['key']}")
            return 1
        # 7 · guard sạch trên phần chữ THẬT SỰ đi vào prompt (title + snippet).
        # Quét cả JSON làm cả 6 cassette dính A17_PII_PHONE trên hiện vật
        # metadata (điểm liên quan 0.86..., content_hash, khoá URL) — metadata
        # không bao giờ chạm prompt. Đã đo, ghi lại để lần sau không mất công.
        for item in payload.get("response", {}).get("items", ()):
            for field in ("title", "snippet"):
                guard = sanitize_and_check(str(item.get(field) or ""))
                if not guard.safe:
                    print(f"FAIL GUARD_HIT: {entry['key']} {field}: {guard.hits}")
                    return 1

    # 6 · replay x3, không mạng, ổn định.
    store = CassetteStore(CASSETTE_DIR)
    provider = ReplaySearchProvider(store)
    try:
        report = verify_determinism(provider, QUERIES, runs=3, max_results=MAX_RESULTS)
    except ReplayMiss as miss:
        print(f"FAIL REPLAY_UNSTABLE: {miss.code}: {miss}")
        return 1
    if not report["stable"]:
        print("FAIL REPLAY_UNSTABLE: content hash đổi giữa các lần chạy.")
        return 1
    print(f"OK — {report['queries']} query replay {report['runs']} lần, "
          "manifest/hash/guard đều khớp.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true",
                        help="replay x3 từ cassette, không gọi mạng")
    args = parser.parse_args()
    return verify() if args.verify else record()


if __name__ == "__main__":
    raise SystemExit(main())
