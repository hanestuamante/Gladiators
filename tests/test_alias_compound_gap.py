"""Theme E: a short surface must not win inside a longer phrase.

Longest-match only suppresses a nested surface when the longer phrase is *itself
indexed*.  Nothing handled the opposite case: the longer phrase appears in the
question but is absent from the index, so the short surface inside it matches
anyway, silently.

"giảm giá" is not an alias, so only "giá" matched -- the concept *discount*
vanished from the request and ``measure.price`` was bound to a question that
never asked about price.  A22 then blocked the plan for dropping a measure the
parse step had invented (bgk05).
"""
from __future__ import annotations

import pytest

from gladiators.domain.alias_index import default_alias_index, normalize_surface
from gladiators.planner.semantic_parser import DeterministicSemanticParser


@pytest.fixture(scope="module")
def index():
    return default_alias_index()


@pytest.mark.parametrize("question", [
    "co bao nhieu listing giam gia tren 50% tai viet nam ngay 03/07",
    "gia tri max cua images count la bao nhieu",
])
def test_a_compound_phrase_does_not_leak_the_price_measure(index, question):
    refs = {ref for match in index.find_in(normalize_surface(question)) for ref in match.refs}
    assert "measure.price" not in refs


def test_the_discount_concept_survives_the_parse(index):
    refs = {
        ref
        for match in index.find_in(normalize_surface("bao nhieu listing giam gia tren 50%"))
        for ref in match.refs
    }
    assert "derived.has_promo" in refs or "measure.discount_percent" in refs


def test_a_real_price_question_still_binds_price(index):
    refs = {
        ref for match in index.find_in(normalize_surface("gia trung vi cua listing tai vn"))
        for ref in match.refs
    }
    assert "measure.price" in refs


@pytest.mark.parametrize("question", [
    "Có bao nhiêu listing giảm giá trên 50% tại Việt Nam ngày 03/07?",
    "Giá trị max của images count là bao nhiêu?",
])
def test_the_production_binder_agrees_with_the_index(question):
    # The two binders are separate implementations (§3.2.1). The "giá trị" fix
    # was applied to one of them only, and the other still carried the bug --
    # which is exactly how two vocabularies for one concept drift apart.
    parsed = DeterministicSemanticParser().parse(question, "vi", "vn")
    assert "measure.price" not in {item.ref for item in parsed.requested_measures}


def test_production_binder_still_binds_a_real_price_question():
    parsed = DeterministicSemanticParser().parse(
        "Giá trung vị của listing tại Việt Nam ngày 03/07 là bao nhiêu?", "vi", "vn",
    )
    assert "measure.price" in {item.ref for item in parsed.requested_measures}
