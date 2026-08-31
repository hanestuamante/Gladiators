"""AliasIndex — ultimate solution §3.2."""
from __future__ import annotations

import pytest

from gladiators.domain.alias_index import AliasIndex, default_alias_index, normalize_surface
from gladiators.domain.catalog import CATALOG


@pytest.fixture(scope="module")
def index() -> AliasIndex:
    return default_alias_index()


def test_every_exposed_object_is_reachable_in_both_language_groups(index):
    # §3.2: a measure with only a technical name exists in the catalogue and is
    # unreachable from a question -- exposed on paper, absent in practice.
    coverage = index.coverage()
    assert coverage["missing_vietnamese"] == []
    assert coverage["missing_en_or_id"] == []


def test_index_is_hashed_for_prompt_and_cache_versioning(index):
    assert len(index.index_hash) == 16
    # A different alias set must produce a different hash, or a cache built
    # against the old aliases would still be served.
    trimmed = {ref: obj for ref, obj in list(CATALOG.items())[:20]}
    assert AliasIndex(trimmed).index_hash != index.index_hash


def test_a_surface_binding_two_refs_reports_ambiguity(index):
    collisions = index.collisions()
    assert collisions, "expected entity/dimension surfaces to overlap"
    surface, refs = next(iter(collisions.items()))
    match = index.lookup(surface)
    # Resolving by ref-name order would silently answer a different question.
    assert match.ambiguous and set(match.refs) == set(refs)


def test_canonical_ref_is_always_addressable(index):
    match = index.lookup("price")
    assert match is not None and "measure.price" in match.refs


@pytest.mark.parametrize("surface, ref", [
    ("giá bán", "measure.price"),
    ("tỷ lệ huỷ đơn của shop", "measure.shop_cancellation_rate"),
    ("số lượt thích", "measure.liked_count"),
    ("doanh thu ước tính", "derived.estimated_recent_revenue"),
    ("harga", "measure.price"),
    ("response rate", "measure.shop_response_rate"),
])
def test_enriched_aliases_bind_the_intended_ref(index, surface, ref):
    match = index.lookup(surface)
    assert match is not None, surface
    assert ref in match.refs


def test_normalizer_folds_but_never_stems_or_translates():
    assert normalize_surface("Giá Bán") == "gia ban"
    assert normalize_surface("  ĐÁNH   giá ") == "danh gia"
    # No stemming: singular and plural stay distinct surfaces.
    assert normalize_surface("ratings") != normalize_surface("rating")


def test_find_in_prefers_the_longest_alias(index):
    matches = index.find_in(normalize_surface("tỷ lệ huỷ đơn của shop tại VN"))
    refs = {ref for match in matches for ref in match.refs}
    assert "measure.shop_cancellation_rate" in refs


# --- WP-A4.1 · bảng ưu tiên là nguồn duy nhất phân giải surface mơ hồ -------

# W8.3: surface mơ hồ KHÔNG ưu tiên không còn bị nuốt — _link nổi
# SemanticAmbiguity và câu fail-closed A-ANALYTICAL-AMBIGUITY. Va chạm voucher
# là CÓ CHỦ ĐÍCH (hai khái niệm, cấm chọn thầm — cấm cả thêm vào
# PREFERRED_REF_BY_SURFACE); mọi va chạm khác vẫn phải có ưu tiên tường minh.
# Surface CỐ Ý mơ hồ: chúng phải fail-closed, và có ưu tiên cho chúng là chọn
# hộ người dùng giữa hai câu hỏi khác nhau.
#
# `so san pham cua shop` thêm vào ngày 01/09: đo được trên cùng một shop, cùng
# một ngày, "số sản phẩm của shop Bibica Official Store" trả 95 còn "có bao
# nhiêu sản phẩm của shop Bibica Official Store" trả 92. 95 là số hàng shop TỰ
# KHAI trên sàn (`shop_info.item_count`), 92 là số listing bộ dữ liệu thu được
# — hai tập hợp khác nhau, và cách nói quyết định ngầm người hỏi nhận cái nào.
DELIBERATE_COLLISIONS = {
    "co voucher", "voucher", "has voucher", "so san pham cua shop",
}


def test_preferred_ref_covers_every_ambiguous_surface(index):
    """Va chạm ngoài danh sách chủ đích phải có ưu tiên — và danh sách chủ đích
    KHÔNG được có ưu tiên (chọn thầm là chính lỗi W8.3 đóng)."""
    from gladiators.domain.alias_index import PREFERRED_REF_BY_SURFACE

    uncovered = sorted(
        set(index.collisions()) - set(PREFERRED_REF_BY_SURFACE)
        - DELIBERATE_COLLISIONS,
    )
    assert uncovered == [], f"surface mơ hồ chưa có ưu tiên: {uncovered}"
    assert not DELIBERATE_COLLISIONS & set(PREFERRED_REF_BY_SURFACE), (
        "surface voucher không được có ưu tiên — nó phải fail-closed"
    )


def test_preferred_ref_points_only_at_real_refs(index):
    from gladiators.domain.alias_index import PREFERRED_REF_BY_SURFACE

    for surface, ref in PREFERRED_REF_BY_SURFACE.items():
        assert ref in index.catalog, f"{surface!r} trỏ ref không tồn tại: {ref}"
        assert ref in index.collisions().get(surface, (ref,)), (
            f"{surface!r} ưu tiên {ref} nhưng ref đó không nằm trong tập va chạm"
        )


def test_parser_no_longer_carries_its_own_alias_seeds():
    r"""A4.1 — ba bộ khớp alias gộp thành một.

    `grep -n "MEASURES\|DIMENSIONS"` trên `semantic_parser.py` phải rỗng; đây là
    tiêu chí nghiệm thu của WP, khoá lại bằng test để nó không lặng lẽ quay về.
    """
    from gladiators.planner.semantic_parser import DeterministicSemanticParser

    assert not hasattr(DeterministicSemanticParser, "MEASURES")
    assert not hasattr(DeterministicSemanticParser, "DIMENSIONS")


def test_both_measures_bind_when_the_question_names_both(index):
    """Suppression phải theo residual, không theo chuỗi tích luỹ.

    "Rating count và rating" hỏi CẢ HAI. Bản tích luỹ chặn `rating` vì nó nằm
    trong `rating count` đã nhận, làm mất một measure người dùng nêu tường minh.
    """
    matches = index.find_in(normalize_surface("Rating count và rating theo brand tại VN"))
    refs = {ref for match in matches for ref in match.refs}
    assert "measure.rating_count" in refs
    assert "measure.rating" in refs
