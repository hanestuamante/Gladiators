"""Deterministic pre-LLM sanitization and A17 span verification."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser

from .contracts import SourceSpan


class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


@dataclass(frozen=True)
class GuardResult:
    text: str
    hits: tuple[str, ...]

    @property
    def safe(self) -> bool:
        return not self.hits


PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("A17_IGNORE_INSTRUCTIONS", re.compile(r"\b(ignore|disregard|abaikan|bo qua)\b.{0,40}\b(instructions?|chi dan|instruksi)\b", re.I)),
    ("A17_SYSTEM_PROMPT", re.compile(r"\b(system prompt|developer message|prompt he thong)\b", re.I)),
    ("A17_ROLE_OVERRIDE", re.compile(r"\b(you are now|act as|hay dong vai|anda sekarang)\b", re.I)),
    ("A17_FAKE_CITATION", re.compile(r"\[ev:[^\]]*\]", re.I)),
    ("A17_PII_EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("A17_SECRET_TOKEN", re.compile(r"\b(?:tvly-[A-Za-z0-9_-]{12,}|bearer\s+[A-Za-z0-9._-]{12,})\b", re.I)),
    ("A17_PII_PHONE", re.compile(r"(?<!\d)(?:\+?\d[\s.-]?){9,14}(?!\d)")),
)


def _fold(text: str) -> str:
    text = text.lower().replace("đ", "d")
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")


def sanitize_and_check(value: str, *, max_chars: int = 4000) -> GuardResult:
    value = unicodedata.normalize("NFKC", value)
    parser = _TextOnly()
    parser.feed(value)
    text = " ".join(parser.parts)
    text = "".join(ch if ch in "\n\t" or unicodedata.category(ch)[0] != "C" else " " for ch in text)
    text = re.sub(r"[ \t]+", " ", text).strip()[:max_chars]
    folded = _fold(text)
    hits = tuple(pattern_id for pattern_id, pattern in PATTERNS if pattern.search(folded))
    return GuardResult(text=text, hits=hits)


def spans_match_utf8(text: str, spans: tuple[SourceSpan, ...]) -> bool:
    raw = text.encode("utf-8")
    return all(
        span.end <= len(raw) and raw[span.start:span.end] == span.text.encode("utf-8")
        for span in spans
    )


def normalize_bound_raw_value(raw_value: str) -> str:
    """Conservative deterministic normalizer used after byte binding passes."""
    return re.sub(r"\s+", " ", raw_value).strip()


def fields_match_utf8(text: str, fields) -> bool:
    """Verify field ownership, raw reconstruction, bounds and non-overlap."""
    occupied: list[tuple[int, int]] = []
    for name, field in fields.items():
        spans = tuple(field.spans)
        if not spans or any(span.field != name for span in spans):
            return False
        if not spans_match_utf8(text, spans):
            return False
        ordered = sorted(spans, key=lambda span: (span.start, span.end))
        if any(left.end > right.start for left, right in zip(ordered, ordered[1:])):
            return False
        reconstructed = "".join(span.text for span in ordered)
        if normalize_bound_raw_value(reconstructed) != normalize_bound_raw_value(field.raw_value):
            return False
        occupied.extend((span.start, span.end) for span in ordered)
        expected = normalize_bound_raw_value(field.raw_value)
        if field.normalized_value is not None and str(field.normalized_value) != expected:
            return False
    occupied.sort()
    return not any(left[1] > right[0] for left, right in zip(occupied, occupied[1:]))
