"""Similarity constraints — ultimate solution §4.6.

Title-only similarity matched across the whole catalogue, so a coffee listing
could be "similar" to a cosmetics listing whenever their titles shared marketing
noise.  §4.6 fixes the comparison in two ways:

**Category containment.**  A candidate must share the platform category level-1
with the source; leaf and deeper path only reorder within that.  The path comes
from the certified ``in_platform_category`` relation.  Shop shelves are never
joined to platform taxonomy -- there is no certified edge between them, so any
such join would be inventing one.

**Status-phrase normalisation.**  Marketplace titles carry decoration
("[GIVEAWAY]", "chính hãng", "freeship", "sale") that is identical across
unrelated products and therefore inflates title similarity.  Those phrases are
removed from the compared text and reported in the evidence, so a reviewer can
see what the score was actually computed on.

A listing with no category mapping is *not* matched against the whole catalogue:
it returns a caveat instead, because "similar to everything" is not an answer.
"""
from __future__ import annotations

import ast
import hashlib
import re

# Versioned so evidence can name the registry that produced a normalisation.
STATUS_PHRASE_REGISTRY_VERSION = "status-phrases.v1"

# Reviewed decoration phrases. Written accent-free: matching happens on folded
# text. Ordered longest-first so a specific phrase wins over a substring.
_STATUS_PHRASES: tuple[str, ...] = (
    "qua tang khong ban", "gift not for sale", "not for sale",
    "hang tang kem", "hang tang", "khong ban",
    "bao bi giao ngau nhien", "giao ngau nhien",
    "doc quyen", "chinh hang", "freeship", "free ship",
    "flash sale", "sale", "hot", "new", "bestseller", "best seller",
    "giveaway", "free gift", "combo", "tang kem",
)

STATUS_PHRASE_REGISTRY_HASH = hashlib.sha256(
    "|".join(_STATUS_PHRASES).encode("utf-8")
).hexdigest()[:16]

_BRACKETED = re.compile(r"[\[\(][^\]\)]{0,60}[\]\)]")
_WHITESPACE = re.compile(r"\s+")


def strip_status_phrases(folded_title: str) -> tuple[str, tuple[str, ...]]:
    """Return the title without decoration, plus the phrases removed.

    Takes text that is already lowercased and accent-folded; the caller owns
    normalisation so this stays a pure registry lookup.
    """
    removed: list[str] = []
    text = folded_title
    for bracket in _BRACKETED.findall(text):
        inner = bracket[1:-1].strip()
        if any(phrase in inner for phrase in _STATUS_PHRASES):
            removed.append(inner)
            text = text.replace(bracket, " ")
    for phrase in _STATUS_PHRASES:
        if phrase in text:
            removed.append(phrase)
            text = text.replace(phrase, " ")
    return _WHITESPACE.sub(" ", text).strip(), tuple(dict.fromkeys(removed))


def parse_category_path(global_catids) -> tuple[int, ...]:
    """Platform category path, root first.

    ``global_catids`` is stored as a JSON-ish list; ``catid_num`` alone is the
    top level. An unparseable or empty value yields ``()`` so the caller can
    treat the listing as unmapped rather than guessing a category for it.
    """
    if global_catids is None:
        return ()
    if isinstance(global_catids, (list, tuple)):
        values = list(global_catids)
    else:
        text = str(global_catids).strip()
        if not text or text.lower() in {"nan", "none"}:
            return ()
        try:
            values = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return ()
        if not isinstance(values, (list, tuple)):
            return ()
    path: list[int] = []
    for item in values:
        try:
            path.append(int(item))
        except (TypeError, ValueError):
            return ()
    return tuple(path)


def category_overlap(source: tuple[int, ...], candidate: tuple[int, ...]) -> dict:
    """How far down the taxonomy two listings agree."""
    return {
        "same_level1": bool(source) and bool(candidate) and source[0] == candidate[0],
        "same_level2": len(source) > 1 and len(candidate) > 1 and source[:2] == candidate[:2],
        "same_leaf": bool(source) and bool(candidate) and source[-1] == candidate[-1],
        "shared_depth": sum(
            1 for a, b in zip(source, candidate) if a == b
        ),
    }
