"""Invariant registry — ultimate solution §3.8."""
from __future__ import annotations

import pytest

from gladiators.domain import invariants
from gladiators.domain.catalog import CATALOG
from gladiators.domain.invariant_handlers import INVARIANT_HANDLERS
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
        # §E3: cũ chỉ đòi validator_id "có dấu chấm" — mà mười một ID đều có dấu
        # chấm và không ID nào được dereference ở runtime. Contract giờ là: ID
        # phải resolve tới một handler thật, phủ đủ mọi stage nó khai.
        handler = INVARIANT_HANDLERS.get(spec.validator_id)
        assert handler is not None, f"{spec.invariant_id} -> {spec.validator_id}"
        assert set(spec.applies_to) <= handler.stages, spec.invariant_id
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


@pytest.mark.parametrize("field,value", [
    ("severity", "warning"),
    ("semantic_refs", ("dim.country",)),
    ("applies_to", ("plan",)),
    ("operators", ("Union",)),
    ("traps", (99,)),
    ("message_key", "invariant.something_else"),
    ("owner", "someone-else"),
    ("version", "9.9"),
])
def test_hash_changes_when_any_semantic_field_changes(field, value):
    """Hash gate cache, topic/decomposition artifact và proof pack.

    §E3.1: hash cũ chỉ ký ``id@version:severity:validator_id``, nên đổi
    ``semantic_refs``, ``applies_to``, ``operators``, ``traps``, ``message_key``
    hay ``owner`` giữ nguyên chữ ký — một bộ rule khác được phục vụ dưới danh
    nghĩa bộ rule đã ký. Test dùng chính hàm hash của registry thay vì chép lại
    công thức: một bản sao công thức trong test chỉ chứng minh test khớp test.
    """
    spec = INVARIANTS["INV-PRICE-SENTINEL-EXCLUDED"]
    changed = spec.model_copy(update={field: value})
    others = [s for s in INVARIANTS.values() if s.invariant_id != spec.invariant_id]
    mutated = {s.invariant_id: s for s in [changed, *others]}

    baseline = _digest(invariants.spec_payload(INVARIANTS))
    assert baseline == REGISTRY_HASH
    assert _digest(invariants.spec_payload(mutated)) != baseline


def _digest(payload) -> str:
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


def test_handler_version_reaches_the_binding_hash():
    """Đổi CÁCH một rule được thi hành cũng là đổi rule.

    ``invariants.REGISTRY_HASH`` chỉ phủ spec (handler nằm ở module khác, ký ở
    đó sẽ tạo import cycle). Chữ ký phủ cả hai là ``bindings.invariant_hash``.
    """
    from gladiators.domain.bindings import _invariant_payload

    payload = _invariant_payload(INVARIANTS)
    versions = {entry["id"]: entry["version"] for entry in payload["handlers"]}
    assert versions, "handler payload rỗng thì handler version không được ký"
    for spec in INVARIANTS.values():
        assert spec.validator_id in versions


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
