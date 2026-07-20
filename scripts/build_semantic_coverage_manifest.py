from __future__ import annotations

import argparse

from gladiators.data.coverage import validate_manifest, write_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build semantic coverage manifest từ physical CSV headers.")
    parser.add_argument("--data-dir", default="data/processed")
    args = parser.parse_args()
    path = write_manifest(args.data_dir)
    summary = validate_manifest(args.data_dir, path)
    print(f"Wrote {path}: {summary['artifacts']} artifacts, {summary['columns']} columns")


if __name__ == "__main__":
    main()
