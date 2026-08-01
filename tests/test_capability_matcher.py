"""CapabilitySpec matcher — ultimate solution §3.5 / §3.6."""
from __future__ import annotations

import pytest

from gladiators.agent.context import RequestDigest
from gladiators.domain.capability import match, nearest_answerable, rank, specs_from_macros
from gladiators.planner.macros import default_macro_registry


@pytest.fixture(scope="module")
def specs():
    return specs_from_macros(default_macro_registry())


def _digest(**updates) -> RequestDigest:
    values = {
        "normalized_question": "q", "language": "vi", "intent": "analytical_query",
        "countries": ("vn",), "requested_output_shape": "comparison",
    }
    values.update(updates)
    return RequestDigest(**values)


def test_specs_are_derived_from_the_macro_registry(specs):
    # §3.5: one source. A hand-written second list is how two registries drift.
    registry = default_macro_registry()
    assert {spec.capability_id for spec in specs} == set(registry.names())
    for spec in specs:
        assert spec.macro_name == spec.capability_id
        assert spec.tool_plan


def test_a_scalar_count_matches_no_comparison_macro(specs):
    # The DeepSeek smoke run routed "Có bao nhiêu listing ở VN?" to a coverage
    # macro, which answered the data's date range instead of a count. No macro
    # produces a scalar, so none may claim it.
    results = rank(_digest(
        requested_measures=("derived.product_count",), requested_output_shape="scalar",
    ), specs)
    assert not any(result.eligible for result in results)
    assert all("shape" in {b.code for b in r.blockers} for r in results)


def test_the_voucher_question_matches_its_own_capability(specs):
    results = rank(_digest(
        intent="promotion_effectiveness",
        requested_measures=("measure.monthly_sold",),
        requested_dimensions=("derived.has_structured_voucher",),
    ), specs)
    best = results[0]
    assert best.capability_id == "promotion_effectiveness"
    assert best.eligible and best.score > 0
    # Discrimination, not a tie: the runner-up must not score the same.
    assert best.score > results[1].score


def test_a_blocker_makes_a_capability_ineligible_however_high_it_scores(specs):
    spec = next(s for s in specs if s.forbidden_qualifiers)
    result = match(_digest(
        requested_measures=tuple(spec.required_measures),
        requested_dimensions=tuple(spec.allowed_grouping),
        qualifiers=tuple(spec.forbidden_qualifiers)[:1],
    ), spec)
    # "Closest available" is how a system answers something it was not asked.
    assert not result.eligible
    assert "qualifier" in {blocker.code for blocker in result.blockers}


def test_blockers_name_what_was_asked_and_what_is_supported(specs):
    spec = next(s for s in specs if s.required_measures)
    result = match(_digest(requested_measures=("measure.price",)), spec)
    blocker = next(b for b in result.blockers if b.code in {"measure", "measure_missing"})
    assert blocker.requested and blocker.supported


def test_suggestions_relax_exactly_one_axis(specs):
    # §3.6: a suggestion that changes two axes is a different question wearing
    # the original's clothes.
    digest = _digest(
        requested_measures=("measure.monthly_sold",),
        requested_dimensions=("derived.has_structured_voucher",),
        qualifiers=("mean_requested",),
    )
    for capability_id in nearest_answerable(digest, specs):
        result = next(r for r in rank(digest, specs) if r.capability_id == capability_id)
        assert len(result.blockers) == 1
