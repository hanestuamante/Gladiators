"""Invariant registry — ultimate solution §3.8."""
from __future__ import annotations

import pytest

from gladiators.domain import invariants
from gladiators.domain.catalog import CATALOG
from gladiators.domain.invariants import (
    INVARIANTS,
    REGISTRY_HASH,
    InvariantSpec,
    hard_invariants,
)


def test_registry_builds_and_is_hashed():
    assert INVARIANTS and len(REGISTRY_HASH) == 16


def test_every_invariant_points_at_a_real_handler_and_message_key():
    for spec in INVARIANTS.values():
        # A rule whose handler or message is a placeholder is prose wearing a
        # schema; §3.8 exists to stop deciding anything from prose.
        assert spec.validator_id and "." in spec.validator_id
        assert spec.message_key.startswith("invariant.")
        assert spec.owner


def test_semantic_refs_exist_in_the_catalog():
    for spec in INVARIANTS.values():
        for ref in spec.semantic_refs:
            assert ref in CATALOG, f"{spec.invariant_id} -> {ref}"


def test_duplicate_ids_fail_the_build():
    spec = next(iter(INVARIANTS.values()))
    with pytest.raises(invariants.InvariantRegistryError, match="trùng ID"):
        invariants._build((spec, spec))


def test_unknown_semantic_ref_fails_the_build():
    broken = InvariantSpec(
        invariant_id="INV-BROKEN", version="1.0", severity="hard",
        applies_to=("plan",), semantic_refs=("measure.does_not_exist",),
        validator_id="x.y", message_key="invariant.x", owner="qa",
    )
    with pytest.raises(invariants.InvariantRegistryError, match="không tồn tại"):
        invariants._build((broken,))


def test_hash_changes_when_a_rule_changes():
    # The hash gates caches, topic/decomposition artifacts and the proof pack, so
    # it must move when severity or handler moves.
    spec = next(iter(INVARIANTS.values()))
    changed = spec.model_copy(update={"severity": "warning"})
    import hashlib

    def digest(specs):
        return hashlib.sha256("|".join(
            f"{s.invariant_id}@{s.version}:{s.severity}:{s.validator_id}"
            for s in sorted(specs, key=lambda i: i.invariant_id)
        ).encode()).hexdigest()[:16]

    assert digest(INVARIANTS.values()) == REGISTRY_HASH
    assert digest([changed, *[s for s in INVARIANTS.values() if s.invariant_id != spec.invariant_id]]) != REGISTRY_HASH


@pytest.mark.parametrize("stage", ["request", "plan", "execution", "evidence", "answer"])
def test_every_stage_has_at_least_one_invariant(stage):
    assert invariants.for_stage(stage), stage


def test_hard_invariants_are_addressable_as_a_set():
    hard = hard_invariants()
    assert hard and all(INVARIANTS[i].severity == "hard" for i in hard)
    # §3.8: a critic may not downgrade or skip these; naming them as a set is
    # what makes that rule checkable rather than aspirational.
    assert "INV-CURRENCY-NO-MIX" in hard
    assert "INV-DEDUPE-BEFORE-AGGREGATE" in hard


def test_existing_traps_are_mapped_to_invariants_not_reparsed_from_prose():
    mapped = {trap for spec in INVARIANTS.values() for trap in spec.traps}
    assert {2, 3, 4, 5, 12}.issubset(mapped)
