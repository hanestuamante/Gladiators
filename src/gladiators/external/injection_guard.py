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
)


def _fold(text: str) -> str:
    text = text.lower().replace("đ", "d")
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")


def sanitize_and_check(value: str, *, max_chars: int = 4000) -> GuardResult:
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
