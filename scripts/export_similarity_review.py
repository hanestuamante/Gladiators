#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from gladiators.agent.workflow import AgentRuntime


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", default="artifacts/human_review/similarity_pairs.csv"); parser.add_argument("--queries", type=int, default=10); parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args(); runtime = AgentRuntime(); products = runtime.repo.products.drop_duplicates("product_listing_key").sort_values(["country_code", "product_listing_key"])
    sampled = products.groupby("country_code", group_keys=False).head(max(1, args.queries // 2)).head(args.queries)
    rows = []
    for _, source in sampled.iterrows():
        for candidate in runtime.resolver.resolve(str(source.product_name), limit=args.top_k + 1):
            if candidate.listing_key == str(source.product_listing_key): continue
            rows.append({"source_listing_key": source.product_listing_key, "source_name": source.product_name, "candidate_listing_key": candidate.listing_key, "candidate_name": candidate.product_name, "system_score": candidate.final_score, "human_relevance_0_2": "", "reviewer": "", "review_notes": ""})
            if sum(r["source_listing_key"] == source.product_listing_key for r in rows) >= args.top_k: break
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
    print(f"Đã tạo {len(rows)} cặp cần human review tại {out}")


if __name__ == "__main__": main()
