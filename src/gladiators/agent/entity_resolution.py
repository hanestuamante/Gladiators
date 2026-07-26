from __future__ import annotations

from rapidfuzz import fuzz, process

from gladiators.contracts import Candidate
from .parser import normalize_text


class EntityResolver:
    def __init__(self, products, embeddings=None):
        self.products = products.drop_duplicates("product_listing_key").reset_index(drop=True)
        self.names = self.products.product_name.fillna("").astype(str).tolist()
        self.key_to_index = {str(row.product_listing_key): idx for idx, row in self.products.iterrows()}
        self.embeddings = embeddings

    def resolve(self, query: str, limit: int = 20) -> list[Candidate]:
        direct = self.products.loc[self.products.product_listing_key.astype(str) == str(query).strip()]
        if direct.empty and str(query).strip().isdigit() and "item_id" in self.products:
            direct = self.products.loc[
                self.products.item_id.astype(str) == str(query).strip()
            ]
        if not direct.empty:
            return [
                Candidate(
                    listing_key=str(row.product_listing_key),
                    product_name=str(row.product_name),
                    lexical_score=1.0,
                    semantic_score=1.0 if self.embeddings else None,
                    final_score=1.0,
                )
                for _, row in direct.drop_duplicates("product_listing_key").head(limit).iterrows()
            ]
        if str(query).strip().isdigit():
            return []
        matches = process.extract(normalize_text(query), self.names, scorer=fuzz.WRatio, limit=limit, processor=normalize_text)
        semantic = self.embeddings.search(query, top_k=max(limit, 20)) if self.embeddings is not None else {}
        lexical = {idx: (name, score / 100) for name, score, idx in matches}
        indices = set(lexical) | {self.key_to_index[k] for k in semantic if k in self.key_to_index}
        result = []
        for idx in indices:
            row = self.products.iloc[idx]
            key = str(row.product_listing_key); dense = semantic.get(key)
            name, lex = lexical.get(idx, (str(row.product_name), 0.0))
            final = lex if self.embeddings is None else .45 * lex + .55 * max(0.0, dense or 0.0)
            result.append(Candidate(listing_key=key, product_name=name, lexical_score=lex, semantic_score=dense, final_score=final))
        return sorted(result, key=lambda x: x.final_score, reverse=True)[:limit]

    @staticmethod
    def ambiguous(candidates: list[Candidate], threshold: float = .65, margin: float = .05) -> bool:
        return not candidates or candidates[0].final_score < threshold or (len(candidates) > 1 and candidates[0].final_score - candidates[1].final_score < margin)
