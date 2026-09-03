"""Request atoms and atomic feasibility — ultimate solution §3.4 / §8.3.

Atoms exist because every silent-wrong-answer this system produced was a dropped
constraint that left a coherent plan behind. Feasibility exists because the
obvious decomposition rule -- two topics means split -- is wrong, and splitting a
question that one join answers buys four times the cost and a new class of bug.
"""
from __future__ import annotations

import pytest

from gladiators.agent.context import RequestDigest
from gladiators.planner.atoms import (
    atomize_request,
    coverage_gap,
    make_atom,
    non_shareable,
)
from gladiators.planner.feasibility import AtomicFeasibility, analyze
from gladiators.planner.semantic_parser import DeterministicSemanticParser
from gladiators.planner.topic_router import TopicRouter


@pytest.fixture(scope="module")
def parser():
    return DeterministicSemanticParser()


@pytest.fixture(scope="module")
def router():
    return TopicRouter()


def digest(question: str, **kwargs) -> RequestDigest:
    base = dict(
        normalized_question=question, language="vi", intent="analytical",
        countries=("vn",), requested_output_shape="scalar",
    )
    base.update(kwargs)
    return RequestDigest(**base)


def atoms_for(parser, question: str, country: str = "vn"):
    request = parser.parse(question, "vi", country)
    return request, atomize_request(digest(question), request)


# --- atom identity --------------------------------------------------------

def test_atom_id_is_content_addressed_and_stable():
    """A uuid or timestamp here would make coverage incomparable across a
    repair or a replay -- the two places coverage matters most."""
    a = make_atom("measure", semantic_ref="measure.price")
    b = make_atom("measure", semantic_ref="measure.price")
    assert a.atom_id == b.atom_id
    assert a.atom_id != make_atom("measure", semantic_ref="measure.rating").atom_id


def test_only_scope_atoms_are_shareable():
    assert make_atom("country", value="vn").shareable
    assert make_atom("date", value="2026-07-03").shareable
    assert not make_atom("measure", semantic_ref="measure.price").shareable
    assert not make_atom("dimension", semantic_ref="dim.shop_name").shareable


def test_each_country_gets_its_own_atom():
    """A composite two-country atom would be 'covered' by a plan that answered
    one of them. That is the scope-drop bug, restated as a data structure."""
    request = type("R", (), {
        "filters": [type("P", (), {"field_ref": "dim.country", "value_binding": ["vn", "id"]})()],
    })()
    atoms = atomize_request(digest("q"), request)
    countries = [a for a in atoms if a.kind == "country"]
    assert {a.value for a in countries} == {"vn", "id"}


def test_ranking_direction_is_part_of_the_atom():
    """Asking for the lowest price and answering the highest was a ~3000x error."""
    ranking = type("Rank", (), {"order_by": "measure.price", "direction": "asc"})()
    request = type("R", (), {"ranking": ranking})()
    atoms = atomize_request(digest("q"), request)
    assert any("asc" in str(a.value) for a in atoms if a.kind == "aggregation")
    descending = type("R", (), {
        "ranking": type("Rank", (), {"order_by": "measure.price", "direction": "desc"})(),
    })()
    assert atomize_request(digest("q"), request) != atomize_request(digest("q"), descending)


def test_atomize_captures_measures_dimensions_and_dates(parser):
    _, atoms = atoms_for(parser, "Giá trung bình theo shop tại Việt Nam ngày 03/07")
    kinds = {a.kind for a in atoms}
    assert {"measure", "country", "output_shape_kind"} <= kinds


# --- coverage -------------------------------------------------------------

def test_coverage_gap_reports_dropped_and_invented_atoms(parser):
    _, atoms = atoms_for(parser, "Giá trung bình tại Việt Nam")
    required = non_shareable(atoms)
    dropped_one = frozenset(list(required)[1:])
    uncovered, unknown = coverage_gap(atoms, dropped_one)
    assert len(uncovered) == 1
    assert not unknown

    uncovered, unknown = coverage_gap(atoms, required | {"mea-deadbeef00"})
    assert not uncovered
    assert unknown == {"mea-deadbeef00"}


def test_shareable_atoms_are_not_required_coverage(parser):
    _, atoms = atoms_for(parser, "Giá trung bình tại Việt Nam ngày 03/07")
    required = non_shareable(atoms)
    assert all(not a.shareable for a in atoms if a.atom_id in required)


# --- feasibility ----------------------------------------------------------

def test_two_topics_still_use_one_atomic_plan(router, parser):
    """§8.3's own example: voucher rate by official shop is a join, not a split."""
    question = "Tỷ lệ có voucher theo shop chính hãng tại VN"
    request = parser.parse(question, "vi", "vn")
    routing = router.route(question, request)
    assert len(routing.domain_topic_ids) > 1
    assert analyze(request, routing, countries=("vn",)).feasible


def test_currency_across_markets_blocks_an_atomic_plan(router, parser):
    """VND and IDR have no exchange rate in this dataset; averaging them
    produces a number with no unit and no meaning."""
    question = "Giá trung bình tại Việt Nam và Indonesia"
    request = parser.parse(question, "vi", "vn")
    routing = router.route(question, request)
    result = analyze(request, routing, countries=("vn", "id"))
    assert "unit_incompatible" in result.blockers
    assert not result.feasible


def test_ambiguous_grain_refuses_rather_than_picking(router, parser):
    """No deterministic priority means no answer, not an arbitrary one.

    Choosing by path cost or name order would silently answer a different
    question, which is precisely the failure atoms exist to prevent.
    """
    question = "Giá trung bình tại Việt Nam"
    request = parser.parse(question, "vi", "vn")
    routing = router.route(question, request)
    result = analyze(request, routing, countries=("vn",), grain_priority={})
    if len(result.candidate_target_grains) > 1:
        assert "ambiguous_target_grain" in result.blockers
        assert result.target_grain is None


def test_context_that_does_not_fit_is_a_blocker(router, parser):
    question = "Giá trung bình tại Việt Nam"
    request = parser.parse(question, "vi", "vn")
    routing = router.route(question, request)
    result = analyze(request, routing, countries=("vn",), context_fits=False)
    assert "context_budget_unsatisfied" in result.blockers
    assert not result.feasible


def test_a_blocked_analysis_never_reports_a_target_grain(router, parser):
    """A grain alongside a blocker invites a caller to use it anyway."""
    question = "Giá trung bình tại Việt Nam và Indonesia"
    request = parser.parse(question, "vi", "vn")
    routing = router.route(question, request)
    result = analyze(request, routing, countries=("vn", "id"))
    assert result.blockers and result.target_grain is None


def test_feasibility_is_frozen():
    result = AtomicFeasibility(feasible=True)
    with pytest.raises((TypeError, ValueError)):
        result.feasible = False


def test_tool_computed_refs_do_not_drive_grain(router, parser):
    """Similarity refs have grain 'pair' but no column; letting them pick the
    target grain would make an ordinary question unplannable."""
    question = 'Sản phẩm nào tương tự "Chupa Chups"?'
    request = parser.parse(question, "vi", "vn")
    routing = router.route(question, request)
    assert "pair" not in analyze(request, routing, countries=("vn",)).candidate_target_grains
