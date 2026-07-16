from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class BGEIndex:
    """Version-pinned, in-memory BGE-M3 cosine index with lazy model loading."""
    def __init__(self, root: str | Path = "artifacts/embeddings"):
        root = Path(root)
        self.manifest = json.loads((root / "manifest.json").read_text())
        self.keys = json.loads((root / "listing_keys.json").read_text())
        self.matrix = np.load(root / "bge_m3.npy", mmap_mode="r")
        if self.matrix.shape != (len(self.keys), self.manifest["dimension"]):
            raise ValueError("Embedding matrix không khớp manifest/listing keys")
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.manifest["model_id"], revision=self.manifest["revision"], device="cpu", local_files_only=True)
        return self._model

    def search(self, query: str, top_k: int = 20) -> dict[str, float]:
        vector = self._load_model().encode([query], normalize_embeddings=True)[0]
        scores = np.asarray(self.matrix @ vector)
        indices = np.argpartition(scores, -min(top_k, len(scores)))[-top_k:]
        return {self.keys[i]: float(scores[i]) for i in indices}
