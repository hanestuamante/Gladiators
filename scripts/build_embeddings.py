#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psutil
import torch
from huggingface_hub import model_info
from sentence_transformers import SentenceTransformer


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("--input", default="data/processed/products_clean.csv")
    ap.add_argument("--output", default="artifacts/embeddings")
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(args.input).drop_duplicates("product_listing_key")
    if args.limit: frame = frame.head(args.limit)
    revision = model_info(args.model).sha
    model = SentenceTransformer(args.model, revision=revision, device="cpu")
    before = psutil.Process().memory_info().rss
    start = time.perf_counter()
    matrix = model.encode(frame.product_name_clean.fillna("").tolist(), batch_size=args.batch_size, normalize_embeddings=True, show_progress_bar=True)
    elapsed = time.perf_counter() - start
    matrix = np.asarray(matrix, dtype=np.float32)
    matrix_path = out / "bge_m3.npy"; np.save(matrix_path, matrix)
    (out / "listing_keys.json").write_text(json.dumps(frame.product_listing_key.astype(str).tolist(), ensure_ascii=False), encoding="utf-8")
    manifest = {
        "model_id": args.model, "revision": revision, "rows": len(frame), "dimension": matrix.shape[1],
        "dtype": str(matrix.dtype), "matrix_sha256": hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
        "cpu": platform.processor() or platform.machine(), "torch_version": torch.__version__,
        "elapsed_seconds": round(elapsed, 3), "rows_per_second": round(len(frame) / elapsed, 3),
        "rss_delta_mb": round((psutil.Process().memory_info().rss - before) / 1048576, 2),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__": main()

