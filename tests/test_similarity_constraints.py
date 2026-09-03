"""Similarity category containment and status phrases — ultimate solution §4.6."""
from __future__ import annotations

import itertools

import pytest

from gladiators.agent.entity_resolution import EntityResolver
from gladiators.analytics import AnalyticsTools
from gladiators.analytics.similarity import (
    STATUS_PHRASE_REGISTRY_HASH,
    STATUS_PHRASE_REGISTRY_VERSION,
    category_overlap,
    parse_category_path,
    strip_status_phrases,
)
from gladiators.data.repository import ArtifactRepository
from gladiators.planner.semantic_parser import normalize


@pytest.fixture(scope="module")
def tools() -> AnalyticsTools:
    repo = ArtifactRepository()
    counter = itertools.count(1)
    return AnalyticsTools(
        repo, EntityResolver(repo.products), lambda: f"ev:tttttttttttt:{next(counter):04d}",
    )


@pytest.fixture(scope="module")
def a_mapped_listing(tools) -> str:
    products = tools.repo.products.drop_duplicates("product_listing_key")
    for row in products.itertuples():
        if parse_category_path(row.global_catids):
            return str(row.product_listing_key)
    pytest.skip("no listing carries a platform category path")


def test_candidates_share_the_source_level1_category(tools, a_mapped_listing):
    # §4.6: level-1 containment is a hard constraint, not a ranking preference.
    evidence = [
        item for item in tools.similar_products(a_mapped_listing)
        if item.metric == "similarity_score"
    ]
    assert evidence
    products = tools.repo.products.drop_duplicates("product_listing_key")
    row = products.loc[
        products.product_listing_key.astype(str) == a_mapped_listing
    ].iloc[0]
    source_level1 = parse_category_path(row.global_catids)[0]
    for item in evidence:
        assert item.attrs["platform_category_path"][0] == source_level1
        assert item.attrs["same_level1"] is True


def test_evidence_carries_path_components_and_registry_version(tools, a_mapped_listing):
    evidence = [
        item for item in tools.similar_products(a_mapped_listing)
        if item.metric == "similarity_score"
    ]
    for item in evidence:
        for key in (
            "platform_category_path", "same_level1", "same_level2", "same_leaf",
            "lexical_score", "status_tokens_removed",
        ):
            assert key in item.attrs, key
        assert item.attrs["status_registry_version"] == STATUS_PHRASE_REGISTRY_VERSION
        assert item.attrs["status_registry_hash"] == STATUS_PHRASE_REGISTRY_HASH


def test_unmapped_listing_returns_a_caveat_not_a_catalogue_wide_match(tools):
    products = tools.repo.products.drop_duplicates("product_listing_key")
    unmapped = next(
        (str(row.product_listing_key) for row in products.itertuples()
         if not parse_category_path(row.global_catids)),
        None,
    )
    if unmapped is None:
        pytest.skip("every listing has a category path in this dataset")
    evidence = tools.similar_products(unmapped)
    # "similar to everything" is not an answer; the caveat is the answer.
    assert [item.metric for item in evidence] == ["similarity_unavailable"]


@pytest.mark.parametrize("title, expected_removed", [
    ("[GIVEAWAY] ZOICY Tea Tree Toner", "giveaway"),
    ("[Quà tặng không bán] Gấu trúc NUTREN", "qua tang khong ban"),
    ("Bánh Quy AFC chính hãng", "chinh hang"),
    ("FLASH SALE MOOI Collagen", "flash sale"),
])
def test_status_phrases_are_stripped_and_reported(title, expected_removed):
    # These phrases repeat across unrelated products, so leaving them in inflates
    # title similarity between things that have nothing to do with each other.
    cleaned, removed = strip_status_phrases(normalize(title))
    assert expected_removed in removed
    assert expected_removed not in cleaned


def test_a_real_product_word_is_never_stripped():
    cleaned, removed = strip_status_phrases(normalize("NESCAFÉ Café Việt"))
    assert "nescafe" in cleaned and removed == ()


def test_category_overlap_reports_depth():
    assert category_overlap((1, 2, 3), (1, 2, 3)) == {
        "same_level1": True, "same_level2": True, "same_leaf": True, "shared_depth": 3,
    }
    shallow = category_overlap((1, 2, 3), (1, 9, 9))
    assert shallow["same_level1"] and not shallow["same_level2"]


def test_unparseable_category_is_empty_not_guessed():
    # An unreadable value must not be coerced into a category, which would place
    # the listing in a taxonomy it was never assigned to.
    for bad in (None, "", "nan", "not-a-list", "[1, 'x']"):
        assert parse_category_path(bad) == ()
