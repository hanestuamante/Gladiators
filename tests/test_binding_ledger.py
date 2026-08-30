"""W16 — Binding Ledger.

Kiểm HÀNH VI của lattice, không kiểm cấu trúc: một ledger claim sai vẫn có đủ
field, đủ kiểu, đủ khoá telemetry. Thứ phân biệt được là *token nào bị ai chiếm*
và *phần dư được xếp loại ra sao*.
"""
from __future__ import annotations

import pytest

from gladiators.domain.function_words import function_words, is_function_word
from gladiators.planner.spans import (
    BindingLedger,
    LedgerBuilder,
    ResidualKind,
    classify_residual,
    fold,
    tokenize,
)


# --- W16-R1: chuẩn hoá theo TOKEN, giữ ánh xạ về câu gốc --------------------


def test_tokens_keep_their_offsets_into_the_original_question():
    """``value_probe`` từng phải quét lại ``raw_question`` bằng một regex thứ hai
    để hỏi "token này có viết hoa không", vì ``normalize()`` chạy trên cả câu và
    huỷ ánh xạ về vị trí gốc. Sau W16 câu hỏi đó trả lời được tại chỗ."""
    question = 'Thương hiệu ORION có bao nhiêu listing?'
    for token in tokenize(question):
        assert question[token.char_start:token.char_end] == token.raw


def test_folding_is_per_token_not_per_sentence():
    assert fold("Điểm Đánh Giá") == "diem danh gia"
    assert [t.normalized for t in tokenize("Giá trị")] == ["gia", "tri"]


def test_a_capital_at_the_start_of_a_sentence_is_not_a_proper_name():
    """Mọi câu đều bắt đầu bằng chữ hoa. Không tách hai thứ này thì "Điểm NPS…"
    cho ``Điểm`` là ``proper_name``, và W22 từ chối oan một câu chỉ thiếu
    measure."""
    tokens = {t.raw: t for t in tokenize("Điểm NPS của shop?  Shop Richy thì sao?")}
    assert tokens["Điểm"].sentence_initial and not tokens["Điểm"].name_shaped
    assert tokens["NPS"].name_shaped
    # Sau dấu hỏi là một câu mới — chữ hoa ở đó cũng không phải tên riêng.
    assert tokens["Shop"].sentence_initial and not tokens["Shop"].name_shaped
    assert tokens["Richy"].name_shaped


def test_quoted_spans_are_marked_even_with_curly_quotes():
    tokens = tokenize('Sản phẩm “Thùng Sữa MILO” có bao nhiêu lượt đánh giá?')
    assert [t.raw for t in tokens if t.quoted] == ["Thùng", "Sữa", "MILO"]


def test_an_unclosed_quote_marks_nothing_rather_than_guessing():
    assert not any(t.quoted for t in tokenize('Sản phẩm "Thùng Sữa MILO'))


# --- W16-R2: một token chỉ được claim MỘT lần ------------------------------


def test_a_token_can_only_be_claimed_once():
    builder = LedgerBuilder("bao nhieu listing tai vn")
    first = builder.claim(2, 3, "alias", ref="entity.product_listing")
    assert first is not None
    assert builder.claim(2, 3, "value", ref="dim.brand") is None
    assert builder.claim(1, 3, "frame") is None, "chồng lấn cũng phải bị từ chối"


def test_a_longer_span_wins_when_it_claims_first():
    """Luật `residual` của ``AliasIndex.find_in`` nâng lên thành tính chất của
    lattice: bộ gọi claim dài trước, và span ngắn nằm trong nó không claim được."""
    builder = LedgerBuilder("rating count va rating theo brand")
    assert builder.claim(*builder.find_free("rating count"), "alias",
                         ref="measure.rating_count") is not None
    # ``rating`` vẫn còn ở chỗ KHÁC nên vẫn bind được — đây đúng là ca mà bản
    # tích luỹ (khác bản residual) làm mất một measure người dùng nêu tường minh.
    pos = builder.find_free("rating")
    assert pos == (3, 4)
    assert builder.claim(*pos, "alias", ref="measure.rating") is not None


def test_find_free_skips_occurrences_already_claimed():
    builder = LedgerBuilder("shop a va shop b")
    builder.claim(*builder.find_free("shop"), "alias", ref="entity.shop")
    assert builder.find_free("shop") == (3, 4)


# --- W16-R3: từ chức năng là registry --------------------------------------


def test_function_words_are_one_registry_not_three_local_sets():
    for word in ("cua", "tai", "theo", "la"):
        assert is_function_word(word)
    for word in ("dari", "yang", "untuk"):
        assert is_function_word(word)
    for word in ("the", "of", "with"):
        assert is_function_word(word)


def test_a_mixed_language_question_still_recognises_its_connectives():
    """Câu thật trộn ngôn ngữ ("berapa listing tại VN"), và một từ nối tiếng
    Indonesia trong câu tiếng Việt vẫn là một từ nối."""
    assert is_function_word("dari", language=None)
    assert function_words("vi") < function_words(None)


def test_market_names_never_read_as_unknown_concepts():
    for word in ("vn", "indonesia", "viet", "nam"):
        assert is_function_word(word)


# --- W16-R4: phân loại phần dư là hàm TOÀN PHẦN ----------------------------


def test_every_unclaimed_token_gets_exactly_one_kind():
    builder = LedgerBuilder('Thương hiệu ORION giảm 50% theo giờ ngày 30/06 vì mất một nửa')
    ledger = builder.build()
    kinds = set(ResidualKind.__args__)
    assert len(ledger.residual) == len([t for t in ledger.tokens if not t.is_punct])
    assert all(item.kind in kinds for item in ledger.residual)
    assert all(item.evidence for item in ledger.residual), "mỗi phân loại phải nêu vì sao"


@pytest.mark.parametrize(("question", "surface", "kind"), [
    ("Doanh thu theo giờ tại VN", "gio", "grain_term"),
    ("Việt Nam mất một nửa số listing", "nua", "magnitude_claim"),
    ("Điểm NPS của shop", "nps", "proper_name"),
    ("Có bao nhiêu SKU", "sku", "grain_term"),
])
def test_residual_kinds_separate_reasons_that_need_different_answers(question, surface, kind):
    """"Hệ không hiểu từ này" khác "hệ hiểu, dữ liệu không có grain đó" — hai
    loại dẫn tới hai lời từ chối khác nhau ở W22."""
    ledger = LedgerBuilder(question).build()
    found = {item.span.normalized: item.kind for item in ledger.residual}
    assert found.get(surface) == kind, found


def test_unknown_concept_is_the_floor():
    ledger = LedgerBuilder("zzzq wibble").build()
    assert {item.kind for item in ledger.residual} == {"unknown_concept"}


# --- telemetry: "đã đo" phải khác "đã chạy" --------------------------------


def test_the_digest_counts_what_actually_fired():
    """CLAUDE.md §5.1.3: mỗi nhánh có điều kiện phải mang một khoá đếm số lần nó
    THẬT SỰ bắn. Không có nó thì "ledger đã chạy" và "ledger chạy mà không claim
    gì" là hai bảng số giống hệt nhau."""
    builder = LedgerBuilder("bao nhieu listing tai vn")
    builder.claim(*builder.find_free("listing"), "alias", ref="entity.product_listing")
    digest = builder.build().digest()
    assert digest["claims_by_producer"] == {"alias": 1}
    assert 0.0 < digest["coverage"] <= 1.0
    assert digest["residual_kinds"]

    empty = LedgerBuilder("bao nhieu listing tai vn").build().digest()
    assert empty["claims_by_producer"] == {}
    assert empty != digest, "ledger không claim gì phải ĐỌC RA KHÁC ledger có claim"


def test_significant_excludes_function_words():
    """Cho W22 nhìn cả từ chức năng sẽ biến mỗi từ nối chưa vào registry thành
    một ``unknown_concept``, và ``over_refusal_rate`` tăng vọt — đúng rủi ro mà
    nghiệm thu W22 khoá bằng "over_refusal_rate không được tăng"."""
    ledger = LedgerBuilder("cua tai theo la nps").build()
    assert [item.span.normalized for item in ledger.significant()] == ["nps"]


def test_coverage_is_one_when_everything_is_claimed_or_a_connective():
    builder = LedgerBuilder("bao nhieu listing tai vn")
    for surface in ("bao", "nhieu", "listing"):
        pos = builder.find_free(surface)
        builder.claim(*pos, "alias")
    assert builder.build().coverage() == pytest.approx(1.0)


# --- tích hợp: parse thật gắn ledger vào request ---------------------------


def test_the_parser_attaches_a_ledger_that_names_what_it_could_not_bind():
    from gladiators.planner.semantic_parser import DeterministicSemanticParser

    parser = DeterministicSemanticParser()
    understood = parser.parse("Có bao nhiêu listing tại Việt Nam ngày 03/07?", "vi", "vn")
    assert understood.binding_ledger["coverage"] == pytest.approx(1.0)
    assert understood.unbound_spans == ()

    unknown = parser.parse("Điểm NPS của shop là bao nhiêu?", "vi", "vn")
    assert ("proper_name", "nps") in unknown.unbound_spans, unknown.unbound_spans
    assert unknown.binding_ledger["coverage"] < 1.0


def test_the_ledger_field_is_additive_so_old_payloads_still_validate():
    from gladiators.planner.semantic_parser import AnalyticalRequest, AnalyticalTimeScope

    request = AnalyticalRequest(
        normalized_question="x", language="vi",
        time_scope=AnalyticalTimeScope(dates=("2026-07-03",), mode="single_snapshot"),
        requested_grain="listing_snapshot", requested_output_shape="scalar",
    )
    assert request.binding_ledger == {}
    assert request.unbound_spans == ()
