#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.independent.oracle import build_oracle


def main() -> None:
    output = ROOT / "eval" / "independent" / "golden_v2.json"
    output.write_text(
        json.dumps(build_oracle(ROOT / "data" / "processed"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()
