"""AliasIndex — ultimate solution §3.2.

``CatalogObject.aliases`` is the single source of natural-language binding.  The
deterministic parser used to carry its own hard-coded ``MEASURES``/``DIMENSIONS``
seed lists, which meant a measure could be *exposed* in the catalogue yet
unreachable from a question, and nobody could tell which of the two lists was
authoritative.

Two properties matter more than lookup speed:

**Collisions surface as ambiguity, not as a winner.**  ``shop`` names both
``entity.shop`` and ``dim.shop_name``.  Resolving that by ref-name order would
pick one silently and answer a different question than the one asked; the index
returns both and lets the caller ask.

**The index is hashed.**  Prompt and cache versions include ``index_hash``, so a
changed alias set cannot be served from a cache built against the old one.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from .catalog import CATALOG, CatalogObject

# Aliases carrying a Vietnamese diacritic are Vietnamese; the rest are treated as
# English/Bahasa. Crude but honest -- the alternative is a language-detection
# dependency for a handful of words.
_VI_MARKERS = re.compile(r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]")


def normalize_surface(value: str) -> str:
    """Shared normaliser for parse, topic fallback and eval (§3.2).

    Unicode normalise, case-fold, fold diacritics, collapse whitespace. No
    stemming and no translation: both would silently equate surfaces the
    catalogue never said were equal.
    """
    value = value.lower().replace("đ", "d")
    stripped = "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", stripped).strip()


# Compound nouns whose meaning is not the meaning of the word inside them.
# Longest-match already suppresses a nested surface when the longer phrase is
# itself indexed; these are the cases where it is *not*, so nothing stopped the
# inner word from matching. Each entry here is a bug that was actually observed
# (CLAUDE.md §3.1), not a guess -- this is a named exception list, not a
# general-purpose tokeniser, and it should stay that way.
_COMPOUND_TRAPS: tuple[tuple[str, str], ...] = (
    ("gia tri", "gia"),      # "giá trị" = value, not the price measure
    ("danh gia", "gia"),     # "đánh giá" = to assess, not price
    ("giam gia", "gia"),     # "giảm giá" = discount, not price
    ("khuyen mai", "mai"),
)


def compound_shadowed(normalized_text: str, surface: str) -> bool:
    """True when ``surface`` only appears inside a compound that means something else.

    Returns False as soon as the surface occurs anywhere outside such a
    compound, so "giá trung vị của listing" still binds the price measure while
    "giảm giá" no longer does.
    """
    residual = normalized_text
    shadowed = False
    for compound, inner in _COMPOUND_TRAPS:
        if inner != surface or not _contains_word(residual, compound):
            continue
        shadowed = True
        residual = re.sub(
            rf"(?<![a-z0-9]){re.escape(compound)}(?![a-z0-9])", " ", residual,
        )
    return shadowed and not _contains_word(residual, surface)


@dataclass(frozen=True)
class AliasEntry:
    normalized_surface: str
    ref: str
    source_alias: str
    language: str


@dataclass(frozen=True)
class AliasMatch:
    refs: tuple[str, ...]
    surface: str
    ambiguous: bool


class AliasIndex:
    def __init__(self, catalog: dict[str, CatalogObject] | None = None):
        self.catalog = catalog or CATALOG
        entries: list[AliasEntry] = []
        for obj in self.catalog.values():
            # The canonical ref is always addressable, so a caller can always
            # bypass natural language when it already knows the ref.
            entries.append(AliasEntry(
                normalize_surface(obj.ref.split(".")[-1].replace("_", " ")),
                obj.ref, obj.ref, "canonical",
            ))
            for alias in obj.aliases:
                entries.append(AliasEntry(
                    normalize_surface(alias), obj.ref, alias,
                    "vi" if _VI_MARKERS.search(alias.lower()) else "en_id",
                ))
        self.entries = tuple(entries)
        self._by_surface: dict[str, list[str]] = {}
        for entry in self.entries:
            refs = self._by_surface.setdefault(entry.normalized_surface, [])
            if entry.ref not in refs:
                refs.append(entry.ref)
        self.index_hash = hashlib.sha256(
            "|".join(
                f"{entry.normalized_surface}>{entry.ref}"
                for entry in sorted(
                    self.entries, key=lambda e: (e.normalized_surface, e.ref),
                )
            ).encode("utf-8")
        ).hexdigest()[:16]

    def lookup(self, surface: str) -> AliasMatch | None:
        """Exact normalized-alias lookup; several refs means ambiguous."""
        refs = self._by_surface.get(normalize_surface(surface))
        if not refs:
            return None
        return AliasMatch(tuple(refs), normalize_surface(surface), len(refs) > 1)

    def find_in(self, normalized_text: str, kinds: frozenset[str] | None = None) -> list[AliasMatch]:
        """Longest-first alias occurrences inside an already-normalised text."""
        matches: list[AliasMatch] = []
        consumed = ""
        for surface in sorted(self._by_surface, key=len, reverse=True):
            if not surface or not _contains_word(normalized_text, surface):
                continue
            if _contains_word(consumed, surface):
                continue  # already covered by a longer alias
            if compound_shadowed(normalized_text, surface):
                continue  # only occurs inside a compound that means something else
            refs = self._by_surface[surface]
            if kinds is not None:
                refs = [ref for ref in refs if self.catalog[ref].kind in kinds]
                if not refs:
                    continue
            consumed += " " + surface
            matches.append(AliasMatch(tuple(refs), surface, len(refs) > 1))
        return matches

    def collisions(self) -> dict[str, tuple[str, ...]]:
        """Surfaces that bind more than one ref, i.e. need an ambiguity fixture."""
        return {
            surface: tuple(refs)
            for surface, refs in sorted(self._by_surface.items())
            if len(refs) > 1
        }

    def coverage(self) -> dict:
        """Per-object alias coverage for the CI report (§3.2)."""
        rows = []
        for obj in self.catalog.values():
            if obj.answerability in {"absent", "context_only"}:
                continue
            languages = {
                entry.language for entry in self.entries
                if entry.ref == obj.ref and entry.language != "canonical"
            }
            rows.append({
                "ref": obj.ref, "kind": obj.kind,
                "alias_count": len(obj.aliases),
                "has_vietnamese": "vi" in languages,
                "has_en_or_id": "en_id" in languages,
            })
        return {
            "index_hash": self.index_hash,
            "exposed_objects": len(rows),
            "missing_vietnamese": [r["ref"] for r in rows if not r["has_vietnamese"]],
            "missing_en_or_id": [r["ref"] for r in rows if not r["has_en_or_id"]],
            "collisions": {k: list(v) for k, v in self.collisions().items()},
            "rows": rows,
        }


def _contains_word(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text))


_DEFAULT: AliasIndex | None = None


def default_alias_index() -> AliasIndex:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = AliasIndex()
    return _DEFAULT
