"""Build the insight sidecar bundle — ultimate solution §12.1.

    python scripts/build_insight_mart.py \
      --processed-dir data/processed \
      --output-root artifacts/insights \
      --config configs/insights.yaml

Writes atomically and refuses to overwrite: same dataset version with different
content is ``IMMUTABLE_INSIGHT_COLLISION``, never a silent replacement.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd  # noqa: E402

from gladiators.insights.builder import (  # noqa: E402
    InsightBuildError,
    build_scorecard,
    load_inputs,
    write_bundle,
)
from gladiators.insights.miners import MinerConfig, mine_all  # noqa: E402
from gladiators.insights.pam import PamConfig  # noqa: E402


def load_config(path: str | None) -> dict:
    defaults = {
        "min_cohort_size": 20, "top_k": 5, "price_drop_pct": -10.0,
        "pam_weights": [0.30, 0.40, 0.30], "min_voucher_group_size": 10,
    }
    if not path or not Path(path).exists():
        return defaults
    try:
        import yaml
        loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except Exception:
        return defaults
    defaults.update({k: v for k, v in loaded.items() if k in defaults})
    return defaults


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed-dir", default=str(REPO / "data" / "processed"))
    parser.add_argument("--output-root", default=str(REPO / "artifacts" / "insights"))
    parser.add_argument("--config", default=str(REPO / "configs" / "insights.yaml"))
    parser.add_argument("--dataset-version", default=None)
    parser.add_argument("--as-of-date", default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    inputs = load_inputs(args.processed_dir)

    dataset_version = args.dataset_version or _dataset_version(args.processed_dir, inputs)
    pam_config = PamConfig(
        min_cohort_size=int(config["min_cohort_size"]),
        weights=tuple(float(w) for w in config["pam_weights"]),
    )
    miner_config = MinerConfig(
        top_k=int(config["top_k"]), price_drop_pct=float(config["price_drop_pct"]),
        min_group_size=int(config["min_voucher_group_size"]),
    )

    try:
        scorecard = build_scorecard(
            inputs, as_of_date=args.as_of_date, config=pam_config,
            dataset_version=dataset_version,
        )
    except InsightBuildError as error:
        print(f"FAIL {error.code}: {error}")
        return 1

    as_of = str(scorecard["as_of_date"].iloc[0])
    sentinel = frozenset(
        scorecard.loc[
            scorecard["price_sentinel_excluded"].astype(bool), "product_listing_key"
        ].astype(str)
    )
    category_of = dict(zip(
        scorecard["product_listing_key"].astype(str),
        scorecard["platform_category_id"].astype("object"),
    ))
    mined = mine_all(
        snapshots=inputs.snapshots, transitions=inputs.transitions,
        issues=inputs.quality_issues, as_of_date=as_of, dataset_version=dataset_version,
        config=miner_config, sentinel_listings=sentinel,
        category_of={k: (str(v) if pd.notna(v) else None) for k, v in category_of.items()},
    )

    try:
        destination = write_bundle(
            args.output_root, dataset_version, scorecard=scorecard,
            cards=mined.cards, evidence=mined.evidence, as_of_date=as_of,
            source_files=inputs.source_files, parameters=config,
        )
    except InsightBuildError as error:
        print(f"FAIL {error.code}: {error}")
        return 1

    segments = scorecard["pam_segment"].value_counts().to_dict()
    print(f"Bundle -> {destination}")
    print(f"  as_of_date       {as_of}")
    print(f"  dataset_version  {dataset_version}")
    print(f"  scorecard rows   {len(scorecard):,}")
    print(f"  cards / evidence {len(mined.cards)} / {len(mined.evidence)}")
    print(f"  segments         {segments}")
    return 0


def _dataset_version(processed_dir: str, inputs) -> str:
    manifest = Path(processed_dir) / "semantic_coverage_manifest.json"
    if manifest.exists():
        try:
            import json
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            version = payload.get("dataset_version")
            if version:
                return str(version)
        except Exception:
            pass
    joined = "|".join(f"{k}:{v}" for k, v in sorted(inputs.source_files.items()))
    import hashlib
    return "ds-" + hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]


if __name__ == "__main__":
    raise SystemExit(main())
