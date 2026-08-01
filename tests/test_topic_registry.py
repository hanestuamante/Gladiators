"""Topic registry contract — ultimate solution §6.2 / §6.3 / §6.4.

The C1–C8 build-time checks run at import, so a broken card fails collection
rather than a query.  These tests exist for the part import cannot prove: that
the checks actually reject the mistakes they name, and that the ownership
decisions the registry encodes are the measured ones and not drift.
"""
from __future__ import annotations

import dataclasses

import pytest

from gladiators.domain import topics
from gladiators.domain.catalog import CATALOG
from gladiators.domain.invariants import INVARIANTS
from gladiators.domain.relations import RELATIONS
from gladiators.domain.topics import TopicCard, TopicRegistryError, TopicRelationPath


def _rebuild(cards):
    return topics._build(tuple(cards))


def _card(**overrides) -> TopicCard:
    base = {
        "id": "TX", "name": "TEST", "kind": "domain",
        "owner_refs": ("measure.rating", "measure.rating_count",
                       "measure.liked_count", "derived.rating_change"),
        "anchor_entities": ("ProductListing",),
    }
    base.update(overrides)
    return TopicCard(**base)


# --- structure ------------------------------------------------------------

def test_every_catalog_ref_has_exactly_one_owner():
    """C2 + C4 together: ownership is a partition of the catalogue.

    A ref with no owner is unreachable by any routed context; a ref with two
    owners makes routing order-dependent. Both are silent, so they are asserted.
    """
    assert set(topics.OWNER_BY_REF) == set(CATALOG)
    assert len(topics.OWNER_BY_REF) == len(CATALOG)


def test_cards_carry_no_trigger_lexicon():
    """§6.2: routing binds through AliasIndex, never a per-topic word list.

    Two vocabularies for the same job drift; §3.2 already made
    ``CatalogObject.aliases`` the single source.
    """
    forbidden = {"triggers", "keywords", "lexicon", "patterns", "trigger_terms"}
    assert forbidden.isdisjoint(TopicCard.model_fields)


def test_aspects_own_no_refs_except_external_context():
    """§6.3: aspects own shape/operator rules; refs belong to domains or CORE."""
    for card in topics.aspects():
        if card.id == "A5":
            assert card.owner_refs, "A5 phải sở hữu context.* để chặn chúng vào SQL"
            continue
        assert not card.all_refs(), f"{card.id} không được sở hữu ref"


def test_core_owns_universal_grouping_keys_not_a_domain():
    """The measured rule: universal keys in CORE keep single-topic questions single.

    ``dim.shop_name`` + ``derived.product_count`` under T5/a counting domain
    would make "shop nào nhiều listing nhất" look cross-topic. Measured on the
    tagged eval corpus, that mistake doubled the apparent two-topic share.
    """
    for ref in ("dim.country", "dim.date", "dim.shop_name", "derived.product_count"):
        assert topics.OWNER_BY_REF[ref] == "CORE", ref


def test_every_context_only_ref_is_declared_non_sql():
    """§6.3: a context_only ref reaching a plan would compile external prose."""
    context_only = {
        ref for ref, obj in CATALOG.items() if obj.answerability == "context_only"
    }
    assert context_only, "catalogue phải còn ref context_only"
    assert context_only <= topics.non_sql_refs()


def test_similarity_refs_are_non_sql_despite_being_exposed_measures():
    """The catalogue calls these ``exposed_as_measure``; they are tool-computed.

    ``derived.similarity_score`` and friends are produced by the similarity tool,
    not by a column, yet their catalogue answerability is indistinguishable from
    a real measure like ``measure.price``. Nothing in the compiler can tell them
    apart, so ``non_sql_refs()`` is the only thing standing between a similarity
    question and a plan that tries to SELECT a column that does not exist.
    """
    non_sql = topics.non_sql_refs()
    for ref in topics.TOPICS["T8"].owner_refs:
        assert CATALOG[ref].answerability == "exposed_as_measure"
        assert ref in non_sql, f"{ref} tool-computed nhưng chưa chặn khỏi SQL"


def test_inheritance_widens_refs_without_duplicating_ownership():
    effective = topics.effective_refs("T8")
    assert set(topics.TOPICS["T8"].all_refs()) < set(effective)
    assert "measure.price" in effective, "T8 kế thừa T1 để so giá đối thủ"
    assert topics.OWNER_BY_REF["measure.price"] == "T1", "kế thừa không chuyển quyền sở hữu"


def test_relation_paths_reference_declared_relations_and_grains():
    for card in topics.TOPICS.values():
        for path in card.relation_paths:
            spec = RELATIONS[path.relation_ids[0]]
            assert path.input_grain == spec.input_grain
            assert path.output_grain == spec.output_grain


def test_invariant_ids_resolve_and_hard_rules_are_covered():
    """Every hard invariant must be attached to at least one topic.

    An unattached hard rule is one no routed context will ever surface.
    """
    attached = {i for card in topics.TOPICS.values() for i in card.invariant_ids}
    assert attached <= set(INVARIANTS)
    from gladiators.domain.invariants import hard_invariants
    missing = sorted(set(hard_invariants()) - attached)
    assert missing in ([], ["INV-COUNTRY-COVERAGE", "INV-NO-INTERNAL-VOCABULARY"]), missing


def test_registry_hash_is_stable_and_sensitive():
    assert len(topics.REGISTRY_HASH) == 16
    assert topics.REGISTRY_HASH == topics.REGISTRY_HASH


# --- the C-checks reject what they claim to reject -------------------------

def test_c1_rejects_unknown_ref():
    with pytest.raises(TopicRegistryError, match="C1"):
        _rebuild([_card(owner_refs=("measure.no_such_thing",) )])


def test_c1_rejects_unknown_invariant():
    with pytest.raises(TopicRegistryError, match="C1"):
        _rebuild([_card(invariant_ids=("INV-DOES-NOT-EXIST",))])


def test_c2_rejects_two_owners_for_one_ref():
    with pytest.raises(TopicRegistryError, match="C2"):
        _rebuild([_card(id="TX"), _card(id="TY", name="OTHER")])


def test_c3_rejects_domain_that_is_too_narrow_or_too_wide():
    with pytest.raises(TopicRegistryError, match="C3"):
        _rebuild([_card(owner_refs=("measure.rating",))])
    wide = tuple(list(CATALOG)[: topics.MAX_DOMAIN_REFS + 1])
    with pytest.raises(TopicRegistryError, match="C3"):
        _rebuild([_card(owner_refs=wide)])


def test_c4_rejects_a_catalog_ref_with_no_owner():
    with pytest.raises(TopicRegistryError, match="C4"):
        _rebuild([_card()])


def test_c5_rejects_fanout_path_without_dedupe_policy():
    fanout = next(r for r in RELATIONS.values() if r.fanout_effect != "none")
    path = TopicRelationPath(
        path_id="p", anchor_entity="ProductListing", relation_ids=(fanout.name,),
        input_grain=fanout.input_grain, output_grain=fanout.output_grain,
        dedupe_policy_id=None,
    )
    with pytest.raises(TopicRegistryError, match="C5"):
        _rebuild([_card(relation_paths=(path,))])


def test_c7_rejects_inheritance_cycle():
    with pytest.raises(TopicRegistryError, match="C7"):
        _rebuild([
            _card(id="TX", inherits=("TY",)),
            _card(id="TY", name="OTHER", inherits=("TX",), owner_refs=(
                "measure.price", "measure.price_original",
                "measure.discount_percent", "derived.discount_bucket",
            )),
        ])


def test_c7_rejects_inheriting_a_topic_that_does_not_exist():
    with pytest.raises(TopicRegistryError, match="C7"):
        _rebuild([_card(inherits=("T99",))])


def test_checked_in_topic_projections_match_the_registry():
    """A hand-edited copy of a card is a second source of truth.

    The drift is invisible until a reviewer signs off against the stale copy, so
    CI checks it rather than trusting that nobody edited a generated file.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/render_topic_prompts.py", "--check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_cards_are_frozen():
    card = topics.TOPICS["T1"]
    with pytest.raises((TypeError, ValueError, dataclasses.FrozenInstanceError)):
        card.id = "mutated"
