"""AliasIndex — ultimate solution §3.2.

``CatalogObject.aliases`` is the single source of natural-language binding, and
``PREFERRED_REF_BY_SURFACE`` below is the single place a colliding surface is
resolved.

This docstring used to claim the deterministic parser's hard-coded
``MEASURES``/``DIMENSIONS`` seeds had already been removed.  That claim was
false for months: the seeds were still there, still consulted first, and a fix
applied to one binder never reached the other.  A docstring that asserts an
architectural property nobody re-checks is worse than a missing feature, so the
statement is only made here now that WP-A4 has actually deleted them.

Two properties matter more than lookup speed:

**Collisions surface as ambiguity, not as a winner.**  ``shop`` names both
``entity.shop`` and ``dim.shop_name``.  Resolving that by ref-name order would
pick one silently and answer a different question than the one asked; the index
returns both and lets the caller ask.

**The index is hashed.**  Prompt and cache versions include ``index_hash``, so a
changed alias set cannot be served from a cache built against the old one.
"""
from __future__ import annotations

import json
from pathlib import Path

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


# WP-B11.3 — lớp overlay: một cách gọi MỚI trỏ tới một ref ĐÃ CÓ.
#
# Vì sao overlay an toàn: nó **không thể** tạo ra một metric mới, một định nghĩa
# mới hay một quan hệ mới. Đó chính là ranh giới giữa "bảo trì từ vựng" và "sinh
# định nghĩa nghiệp vụ" — và ranh giới đó là thứ khiến vòng bảo trì này không
# phải là một hệ tự sửa.
ALIAS_OVERLAY_PATH = Path(__file__).resolve().parent / "alias_overlay.json"


class AliasOverlayError(ValueError):
    """Overlay sai ⇒ fail Ở IMPORT, như mọi registry khác trong hệ."""


def load_alias_overlay(
    path: Path | None = None, catalog: dict[str, CatalogObject] | None = None,
) -> tuple[dict[str, object], ...]:
    """Mục overlay đã kiểm. Thiếu file ⇒ rỗng; file sai ⇒ lỗi.

    B11-R1: ``approved_by`` rỗng là lỗi, không phải mặc định. Một mục không có
    người ký là đúng thứ vòng duyệt này tồn tại để chặn — cho nó chạy im lặng sẽ
    biến "có người duyệt" thành một lời hứa không ai kiểm.

    B11-R2: ``ref`` phải tồn tại trong catalog. Overlay chỉ ánh xạ, không tạo.
    """
    target = path or ALIAS_OVERLAY_PATH
    known = catalog if catalog is not None else CATALOG
    if not target.exists():
        return ()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AliasOverlayError(f"alias_overlay.json không đọc được: {exc}") from exc
    if not isinstance(payload, list):
        raise AliasOverlayError("alias_overlay.json phải là một danh sách")
    for entry in payload:
        if not isinstance(entry, dict):
            raise AliasOverlayError("mỗi mục overlay phải là một object")
        surface = str(entry.get("surface") or "").strip()
        ref = str(entry.get("ref") or "")
        if not surface:
            raise AliasOverlayError("mục overlay thiếu surface")
        if ref not in known:
            raise AliasOverlayError(f"overlay trỏ ref không tồn tại: {ref}")
        if not str(entry.get("approved_by") or "").strip():
            raise AliasOverlayError(f"mục overlay thiếu approved_by: {surface}")
        if not str(entry.get("approved_at") or "").strip():
            raise AliasOverlayError(f"mục overlay thiếu approved_at: {surface}")
    return tuple(payload)


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
        # Overlay nạp SAU catalog: nó chỉ thêm cách gọi, không ghi đè cách gọi
        # nào đã có, nên thứ tự này giữ cho catalog luôn là nguồn sự thật.
        self.overlay = load_alias_overlay(catalog=self.catalog)
        for entry in self.overlay:
            entries.append(AliasEntry(
                normalize_surface(str(entry["surface"])), str(entry["ref"]),
                str(entry["surface"]), "overlay",
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
        """Longest-first alias occurrences inside an already-normalised text.

        Suppression dùng **residual** -- văn bản đã xoá các span đã nhận -- chứ
        không dùng một chuỗi tích luỹ các surface đã nhận. Hai cách chỉ giống
        nhau khi surface ngắn xuất hiện đúng một lần.

        "Rating count và rating theo brand" hỏi CẢ HAI. Bản tích luỹ chặn
        ``rating`` vì nó nằm trong ``rating count`` đã nhận, nên câu hỏi mất một
        measure người dùng nêu tường minh. Residual xoá đúng span đã nhận rồi
        hỏi lại: ``rating`` vẫn còn ở chỗ khác thì vẫn bind.
        """
        matches: list[AliasMatch] = []
        residual = normalized_text
        for surface in sorted(self._by_surface, key=len, reverse=True):
            if not surface or not _contains_word(normalized_text, surface):
                continue
            if not _contains_word(residual, surface):
                continue  # mọi lần xuất hiện đều đã nằm trong một alias dài hơn
            if compound_shadowed(normalized_text, surface):
                continue  # only occurs inside a compound that means something else
            refs = self._by_surface[surface]
            if kinds is not None:
                refs = [ref for ref in refs if self.catalog[ref].kind in kinds]
                if not refs:
                    continue
            residual = re.sub(
                rf"(?<![a-z0-9]){re.escape(surface)}(?![a-z0-9])", " ", residual,
            )
            matches.append(AliasMatch(tuple(refs), surface, len(refs) > 1))
        return matches

    def surfaces(self) -> frozenset[str]:
        """Mọi TỪ ĐƠN xuất hiện trong một alias đã biết.

        W17-R1 cần nó để trả lời "token này đã là một alias chưa?" trước khi thử
        dạng số ít — fallback chỉ được chạy khi khớp thẳng đã thất bại.
        """
        return frozenset(
            word for surface in self._by_surface for word in surface.split()
        )

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


# WP-A4.1 · Surface trỏ nhiều ref: thứ tự này là quyết định nghiệp vụ đã được
# kiểm bằng eval, không phải mặc định của thuật toán. Giữ ở MỘT chỗ vì hai bảng
# ưu tiên chắc chắn sẽ lệch nhau.
#
# Nạp NGUYÊN VĂN hành vi cũ (A4-R1): chín surface đầu đến từ seed
# ``DIMENSIONS``; sáu surface còn lại trước đây được phân giải bằng thứ tự chữ
# cái của tên ref ("dim." < "entity."), tức một tai nạn sắp xếp — nay ghi thành
# quyết định tường minh, cùng kết quả.
PREFERRED_REF_BY_SURFACE: dict[str, str] = {
    "shop": "entity.shop",
    "cua hang": "entity.shop",
    "toko": "entity.shop",
    "quoc gia": "dim.country",
    "country": "dim.country",
    "negara": "dim.country",
    "brand": "dim.brand",
    "thuong hieu": "dim.brand",
    "merek": "dim.brand",
    "danh muc san": "dim.platform_category_name",
    "platform category": "dim.platform_category_name",
    "ke shop": "dim.shop_category_name",
    "shop shelf": "dim.shop_category_name",
    "san pham": "dim.product_name",
    "produk": "dim.product_name",
}


def _contains_word(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text))


_DEFAULT: AliasIndex | None = None


def default_alias_index() -> AliasIndex:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = AliasIndex()
    return _DEFAULT
