"""Entity resolution states and the stop lexicon — ultimate solution §4.2."""
from __future__ import annotations

import pytest

from gladiators.agent.entity_resolution import (
    STOP_LEXICON_VERSION,
    EntityResolver,
    ResolutionThresholds,
    distinctive_tokens,
)
from gladiators.agent.parser import normalize_text
from gladiators.data.repository import ArtifactRepository


@pytest.fixture(scope="module")
def resolver() -> EntityResolver:
    return EntityResolver(ArtifactRepository().products)


@pytest.mark.parametrize("text, expected", [
    ("", "not_found"),                              # nothing extracted
    ("   ", "not_found"),
    ("zzzzzzzz", "invalid_extraction"),             # span, nothing matches
    ("111222333444", "invalid_extraction"),         # id-shaped, no such id
    ("Collagen", "ambiguous_broad"),                # many equally good matches
    ("id:1112776376:46456356622", "resolved"),      # exact identifier
])
def test_four_states_are_distinguished(resolver, text, expected):
    assert resolver.classify(text).state == expected


def test_stop_lexicon_words_alone_never_earn_a_match(resolver):
    # rapidfuzz WRatio scored this 0.855 against a listing whose only overlap was
    # the negation "không". A score earned that way is not evidence of identity.
    result = resolver.classify("xyzabc không tồn tại 12345")
    assert result.state == "invalid_extraction"
    assert result.candidates == ()


def test_a_real_product_phrase_is_ambiguous_not_missing(resolver):
    # "bánh quy Kinh Đô" names something that exists, so the answer is "which of
    # these", never "not found" -- and never a silent pick.
    result = resolver.classify("banh quy kinh do")
    assert result.state == "ambiguous_broad"
    assert len(result.candidates) > 1
    wanted = distinctive_tokens(normalize_text("banh quy kinh do"))
    for candidate in result.candidates:
        # normalize_text strips accents; a plain .lower() leaves "bánh" != "banh".
        assert wanted & distinctive_tokens(normalize_text(candidate.display_name))


def test_ambiguous_result_carries_a_shortlist_and_never_auto_picks(resolver):
    result = resolver.classify("Collagen")
    assert result.state == "ambiguous_broad"
    # §4.2: top-3 handed back so the user disambiguates. Auto-picking the
    # best-selling listing is forbidden; nothing here consults sales at all.
    assert 1 < len(result.candidates) <= ResolutionThresholds().top_k
    assert all(item.listing_key for item in result.candidates)


def test_scores_and_margin_stay_in_the_result_for_the_trace(resolver):
    result = resolver.classify("Collagen")
    assert result.top1_score is not None and result.top2_score is not None
    assert result.margin == pytest.approx(result.top1_score - result.top2_score)
    assert result.candidates[0].score_breakdown  # lexical/semantic split kept
    assert result.resolution_source


def test_stop_lexicon_covers_the_groups_the_spec_names():
    assert STOP_LEXICON_VERSION
    # §4.2 names these groups explicitly: negation, cause, time, price,
    # forecast, competitor.
    for word in ("khong", "sao", "ngay", "gia", "bao", "canh"):
        assert not distinctive_tokens(word), f"{word} should be a stop token"
    # ...and must not swallow words that do name products.
    for word in ("collagen", "nescafe", "milo"):
        assert distinctive_tokens(word) == {word}


def test_thresholds_are_config_not_message_text(resolver):
    thresholds = ResolutionThresholds()
    assert 0 < thresholds.accept_score < 1 and 0 < thresholds.min_margin < 1
    # §4.2: "Không hard-code threshold trong message."
    result = resolver.classify("Collagen")
    assert str(thresholds.accept_score) not in str(result.state)
