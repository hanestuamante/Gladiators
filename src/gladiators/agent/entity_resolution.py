"""Entity resolution with a typed outcome — ultimate solution §4.2."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from rapidfuzz import fuzz, process

from gladiators.contracts import Candidate
from .parser import normalize_text

ResolutionState = Literal["resolved", "not_found", "invalid_extraction", "ambiguous_broad"]

# §4.2 stop lexicon, versioned, covering the groups the spec names: cause, time,
# price, forecast, negation and competitor. These words carry no product
# identity, so they must not earn a match on their own -- rapidfuzz WRatio is
# generous with partial token overlap and scored a nonsense query 0.855 against
# a listing purely because both contained the negation "không".
STOP_LEXICON_VERSION = "v1"
_STOP_TOKENS = frozenset({
    # negation
    "khong", "chua", "chang", "no", "not", "tanpa", "bukan",
    # cause
    "vi", "sao", "tai", "ly", "do", "nguyen", "nhan", "why", "karena",
    # time
    "ngay", "tuan", "thang", "nam", "snapshot", "hom", "qua", "nay", "truoc",
    "sau", "date", "week", "month", "hari", "minggu", "bulan",
    # price
    "gia", "price", "harga", "tien", "dong", "vnd", "idr",
    # forecast
    "du", "bao", "doan", "forecast", "ramalan", "prediksi",
    # competitor / comparison
    "doi", "thu", "canh", "tranh", "competitor", "pesaing", "so", "voi",
    "hon", "kem", "compare", "vs",
    # generic question scaffolding
    "cua", "la", "co", "cho", "toi", "ban", "hang", "san", "pham", "listing",
    "bao", "nhieu", "the", "nao", "gi", "which", "what", "product", "produk",
    "kiem", "tra", "phan", "tich", "danh", "gia", "ton", "tai",
})
_MIN_DISTINCTIVE_LEN = 3


def distinctive_tokens(normalized: str) -> set[str]:
    """Tokens that could actually name a product, per the §4.2 stop lexicon."""
    return {
        token for token in normalized.split()
        if len(token) >= _MIN_DISTINCTIVE_LEN and token not in _STOP_TOKENS
    }


@dataclass(frozen=True)
class ResolutionThresholds:
    """Typed config, so the numbers live in one reviewable place (§4.2).

    Bootstrap values from the spec; they are meant to be tuned against fixtures
    rather than guessed again at each call site, and they never appear in a
    user-facing message.
    """

    accept_score: float = 0.50
    min_margin: float = 0.05
    top_k: int = 3


class ResolutionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str
    display_name: str
    shop_name: str | None = None
    listing_key: str | None = None
    score: float
    score_breakdown: dict[str, float] = Field(default_factory=dict)


class EntityResolutionResult(BaseModel):
    """Why resolution ended the way it did, not merely that it failed.

    ``ambiguous()`` used to collapse "nothing extracted", "extracted but nothing
    matched" and "several equally good matches" into one boolean, so the gate
    could only ever say the same thing.  Each state now carries a different
    remedy: a missing span is a parsing problem, a weak top score means the text
    does not name anything in the catalogue, and a thin margin means the user has
    to disambiguate.
    """

    model_config = ConfigDict(extra="forbid")
    state: ResolutionState
    extracted_text: str
    normalized_text: str
    candidates: tuple[ResolutionCandidate, ...] = ()
    top1_score: float | None = None
    top2_score: float | None = None
    margin: float | None = None
    resolution_source: str = "lexical"


class EntityResolver:
    # A token in at most this share of listings names something specific; above
    # it the word is just vocabulary for the category. Measured from the corpus
    # rather than listed by hand: a stop lexicon cannot know that "kẹo" is
    # generic in a confectionery dataset while "chupa" is not.
    _RARE_TOKEN_MAX_SHARE = 0.05

    def __init__(self, products, embeddings=None):
        self.products = products.drop_duplicates("product_listing_key").reset_index(drop=True)
        self.names = self.products.product_name.fillna("").astype(str).tolist()
        self.key_to_index = {str(row.product_listing_key): idx for idx, row in self.products.iterrows()}
        self.embeddings = embeddings
        self._token_share = self._build_token_share()

    def _build_token_share(self) -> dict[str, float]:
        """Share of listings whose name contains each token."""
        from collections import Counter

        counts: Counter[str] = Counter()
        for name in self.names:
            counts.update(distinctive_tokens(normalize_text(name)))
        total = max(1, len(self.names))
        return {token: count / total for token, count in counts.items()}

    def _rare_token_indices(self, normalized: str, limit: int) -> set[int]:
        """Listings whose name carries every rare token the query offers."""
        rare = self.rare_tokens(distinctive_tokens(normalized))
        if not rare:
            return set()
        hits = {
            idx for idx, name in enumerate(self.names)
            if rare <= distinctive_tokens(normalize_text(name))
        }
        # Bounded: a single very rare token could otherwise pull in a long tail.
        return set(sorted(hits)[: max(limit, 20)])

    def rare_tokens(self, wanted: set[str]) -> set[str]:
        """The subset of query tokens that actually narrow the corpus."""
        return {
            token for token in wanted
            if self._token_share.get(token, 0.0) <= self._RARE_TOKEN_MAX_SHARE
        }

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
        # Rare tokens must RECALL candidates, not merely filter them. Fuzzy
        # ranking scores whole strings, so a query dominated by category words
        # ("kẹo dẻo", "bánh quy") can fill its top-N with the wrong brand and
        # never surface the listing the rare token names. Filtering that list
        # then throws everything away and reports "not found" for a product that
        # plainly exists. Pulling the rare-token matches in first fixes both.
        indices |= self._rare_token_indices(normalize_text(query), limit)
        result = []
        for idx in indices:
            row = self.products.iloc[idx]
            key = str(row.product_listing_key); dense = semantic.get(key)
            name, lex = lexical.get(idx, (str(row.product_name), 0.0))
            final = lex if self.embeddings is None else .45 * lex + .55 * max(0.0, dense or 0.0)
            result.append(Candidate(listing_key=key, product_name=name, lexical_score=lex, semantic_score=dense, final_score=final))
        return sorted(result, key=lambda x: x.final_score, reverse=True)[:limit]

    def classify(
        self, entity_text: str | None, candidates: list[Candidate] | None = None,
        thresholds: ResolutionThresholds = ResolutionThresholds(),
    ) -> EntityResolutionResult:
        """Resolve into one of four states (§4.2), never a bare boolean.

        Ordering matters and follows the spec: no span at all is ``not_found``;
        a span that matches nothing convincing is ``invalid_extraction``; a
        convincing top score that is not convincingly *better* than the runner-up
        is ``ambiguous_broad``, and carries the top-3 so the question can be put
        back to the user.  Nothing here ever picks the best-selling listing to
        break a tie -- §4.2 forbids that, and it would turn "which one did you
        mean" into a confident wrong answer.
        """
        text = (entity_text or "").strip()
        normalized = normalize_text(text) if text else ""
        if not text:
            return EntityResolutionResult(
                state="not_found", extracted_text="", normalized_text="",
                resolution_source="no_span",
            )

        ranked = list(candidates if candidates is not None else self.resolve(text))
        source = "embedding+lexical" if self.embeddings is not None else "lexical"

        # WRatio is generous with partial token overlap, so a listing that shares
        # only stop-lexicon words can outrank the products the user actually
        # named -- "bánh quy Kinh Đô" ranked a NESTLÉ gift item first at 0.855
        # while the real Kinh Đô listings sat below it. Drop candidates that share
        # no distinctive token, then rank what is left. Used as a filter rather
        # than a veto: when the query does name something real, the answer is
        # "which of these", not "not found".
        wanted = distinctive_tokens(normalized)
        by_identifier = text.isdigit() or any(
            item.listing_key == text for item in ranked[:1]
        )
        if wanted and not by_identifier:
            # Deliberately a broad OR over distinctive tokens. Narrowing it to
            # the rarest token was tried and rejected: a rare token that names a
            # brand appearing in one product *title* then eliminated every
            # candidate for a query whose brand lives in a separate column, and
            # "which of these" became "not found" for a product that exists.
            # Recall above is where rare tokens do their work.
            relevant = [
                item for item in ranked
                if wanted & distinctive_tokens(normalize_text(item.product_name))
            ]
            if relevant:
                ranked = relevant
                source += "+token_filtered"
            else:
                ranked = []
                source += "+no_distinctive_match"
        top = [
            ResolutionCandidate(
                entity_id=item.listing_key, display_name=item.product_name,
                listing_key=item.listing_key, score=round(item.final_score, 6),
                score_breakdown={
                    "lexical": round(item.lexical_score, 6),
                    **({"semantic": round(item.semantic_score, 6)}
                       if item.semantic_score is not None else {}),
                },
            )
            for item in ranked[: thresholds.top_k]
        ]
        top1 = ranked[0].final_score if ranked else None
        top2 = ranked[1].final_score if len(ranked) > 1 else None
        margin = None if top1 is None or top2 is None else round(top1 - top2, 6)

        if top1 is None or top1 < thresholds.accept_score:
            state: ResolutionState = "invalid_extraction"
        elif margin is not None and margin < thresholds.min_margin:
            state = "ambiguous_broad"
        else:
            state = "resolved"
        return EntityResolutionResult(
            state=state, extracted_text=text, normalized_text=normalized,
            candidates=tuple(top),
            top1_score=None if top1 is None else round(top1, 6),
            top2_score=None if top2 is None else round(top2, 6),
            margin=margin, resolution_source=source,
        )

    @staticmethod
    def ambiguous(candidates: list[Candidate], threshold: float = .65, margin: float = .05) -> bool:
        """Legacy boolean kept for callers not yet reading the typed result."""
        return not candidates or candidates[0].final_score < threshold or (len(candidates) > 1 and candidates[0].final_score - candidates[1].final_score < margin)


# --- WP-A10 · ràng buộc loại entity ----------------------------------------
# `AnalyticalRequest.resolved_entities` đã có trường `entity_type` với đúng năm
# giá trị, nhưng chưa ai dùng nó làm RÀNG BUỘC. Không có bước nào hỏi "câu này
# đang cần một thực thể thuộc loại nào?".

# A10-R2: chỉ suy loại từ ref ĐÃ BIND qua registry, không từ văn bản tự do.
ENTITY_TYPE_BY_REF: dict[str, str] = {
    "dim.platform_category_name": "category",
    "entity.platform_category": "category",
    "dim.shop_category_name": "shelf",
    "entity.shop_category": "shelf",
    "dim.shop_name": "shop",
    "entity.shop": "shop",
    "dim.brand": "brand",
    "entity.brand": "brand",
}


def expected_entity_types(request) -> tuple[str, ...]:
    """Loại thực thể mà các ref đã bind ngụ ý. Rỗng ⇒ giữ nguyên hành vi cũ."""
    refs = {
        item.ref
        for item in (*request.requested_measures, *request.requested_dimensions)
        if item.ref and not item.unresolved
    }
    refs |= {predicate.field_ref for predicate in request.filters}
    return tuple(sorted({
        ENTITY_TYPE_BY_REF[ref] for ref in refs if ref in ENTITY_TYPE_BY_REF
    }))
