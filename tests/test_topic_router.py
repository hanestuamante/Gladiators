"""TopicRouter contract — ultimate solution §6.5.

The router narrows what the planner is allowed to see, so its failure mode is
silent: a wrongly-dropped topic cannot be recovered downstream because nothing
downstream knows it existed.  These tests pin the four distinct route states and
the no-truncation rule, and hold the measured corpus distribution as a bound so
routing quality cannot regress unnoticed.
"""
from __future__ import annotations

import glob
import json

import pytest

from gladiators.domain import topics
from gladiators.planner.semantic_parser import DeterministicSemanticParser
from gladiators.planner.topic_router import (
    TOPIC_GATE_VERSION,
    RoutingResult,
    TopicRouter,
)


@pytest.fixture(scope="module")
def router() -> TopicRouter:
    return TopicRouter()


@pytest.fixture(scope="module")
def parser() -> DeterministicSemanticParser:
    return DeterministicSemanticParser()


@pytest.fixture(scope="module")
def corpus() -> tuple[str, ...]:
    """Every question in the eval tree, deduplicated."""
    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            question = node.get("question")
            if isinstance(question, str) and len(question) > 10:
                found.append(question)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    # `eval/independent/` giữ ORACLE và đáp án, không phải corpus câu hỏi để đo
    # routing — ngưỡng topic_scoped được hiệu chỉnh trên các suite viết tay. Đo riêng
    # cho thấy khác biệt là thật chứ không phải nhiễu: corpus cũ route được 69,3%,
    # bộ đề sinh từ dữ liệu chỉ 34,1% (61,4% rơi về core_only). Con số đó được ghi ở
    # eval/reports/2026-08-27-independent-bank.md thay vì bị trộn vào một ngưỡng
    # không dành cho nó.
    # `eval/reports/` là ĐẦU RA, không phải đầu vào. Một report chứa `rows[]` kèm
    # `question` sẽ lặng lẽ bơm chính bộ đề vừa bị loại ở trên trở lại corpus:
    # eval/reports/<ngày>-sql-baseline.json đã kéo topic_scoped từ 65,9% xuống
    # 63,4% đúng bằng cách đó. Một phép đo được phép đọc corpus; nó không được
    # phép trở thành corpus.
    # `eval/accuracy/` là benchmark accuracy độc lập (TC_formulation) — cùng
    # lớp với independent/: bộ đề sinh từ dữ liệu, KHÔNG phải corpus mà ngưỡng
    # topic_scoped 0.65 được hiệu chỉnh trên đó. Trộn vào kéo topic_scoped từ
    # 69% xuống 57.6% đúng bằng cơ chế đã ghi ở comment trên.
    excluded = {"independent", "reports", "accuracy"}
    for path in glob.glob("eval/**/*.json", recursive=True):
        if excluded & set(path.replace("\\", "/").split("/")):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                walk(json.load(handle))
        except (OSError, json.JSONDecodeError):
            continue
    return tuple(sorted(set(found)))


def _route(router, parser, question: str) -> RoutingResult:
    return router.route(question, parser.parse(question, "vi", "vn"))


# --- route modes ----------------------------------------------------------

def test_measure_question_routes_to_its_owning_topic(router, parser):
    result = _route(router, parser, "Giá trung bình tại Việt Nam là bao nhiêu?")
    assert result.mode == "topic_scoped"
    assert result.domain_topic_ids == ("T1",)
    assert "measure.price" in result.resolved_refs


def test_scope_only_question_is_unknown_not_core_only(router, parser):
    """The parser injects a country filter on every request.

    If injected scope refs counted as bindings, ``unknown`` would be
    unreachable and a question about data we do not hold -- stock, margin --
    would route as a perfectly valid CORE slice.
    """
    result = _route(router, parser, "Tỷ lệ chuyển đổi là bao nhiêu?")
    assert result.mode == "unknown"
    assert "scope_refs_only" in result.routing_reasons or "no_ref_bound" in result.routing_reasons


def test_counting_question_is_core_only_not_a_domain(router, parser):
    result = _route(router, parser, "Có bao nhiêu listing tại Việt Nam?")
    assert result.mode == "core_only"
    assert result.domain_topic_ids == ()


def test_cross_domain_question_keeps_every_topic(router, parser):
    result = _route(router, parser, "Giá và lượt bán tháng của sản phẩm tại VN")
    assert result.mode == "multi_topic"
    assert {"T1", "T2"} <= set(result.domain_topic_ids)


def test_gate_disabled_is_its_own_state(parser):
    """§6.5: gate off must not be reported as ``unknown`` routing."""
    result = TopicRouter(gate_enabled=False).route(
        "Giá trung bình tại Việt Nam", parser.parse("Giá trung bình tại VN", "vi", "vn")
    )
    assert result.routing_reasons == ("topic_gate_disabled",)
    assert result.domain_topic_ids == ()


def test_overflow_never_truncates_topic_metadata(router, parser):
    """§6.5: overflow preserves everything; the decomposer decides, not the router."""
    base = _route(router, parser, "Giá và lượt bán tháng và voucher tại VN")
    overflowed = router.mark_overflow(base, "context_budget")
    assert overflowed.mode == "overflow"
    assert overflowed.overflow_reason == "context_budget"
    assert overflowed.domain_topic_ids == base.domain_topic_ids
    assert overflowed.resolved_refs == base.resolved_refs
    assert overflowed.required_relation_ids == base.required_relation_ids


# --- ref and relation handling -------------------------------------------

def test_resolved_refs_beat_alias_guesses(router, parser):
    """Alias fallback runs only over phrases the request failed to bind."""
    question = "Giá trung bình tại Việt Nam"
    request = parser.parse(question, "vi", "vn")
    result = router.route(question, request)
    bound = {b.ref for b in request.requested_measures if b.ref}
    assert bound <= set(result.resolved_refs)


def test_ambiguous_alias_contributes_nothing(router):
    """"shop" names both entity.shop and dim.shop_name.

    Resolving that by index order answers a different question than the one
    asked, and nothing downstream could detect it happened.
    """
    result = router.route("shop", None)
    assert "entity.shop" not in result.resolved_refs
    assert "dim.shop_name" not in result.resolved_refs
    assert any(r.startswith("alias_ambiguous") for r in result.routing_reasons)


def test_effective_refs_carry_required_refs_through_the_route(router, parser):
    result = _route(router, parser, "Giá trung bình tại Việt Nam")
    effective = set(result.effective_refs())
    assert set(result.resolved_refs) <= effective
    assert set(topics.TOPICS["CORE"].all_refs()) <= effective


def test_router_only_emits_declared_relations(router, parser, corpus):
    """The router must not be able to invent an edge the registry never declared."""
    declared = {r for card in topics.TOPICS.values() for r in card.relation_ids}
    for question in corpus[:60]:
        result = _route(router, parser, question)
        assert set(result.required_relation_ids) <= declared


def test_similarity_route_requests_no_sql_relation_for_tool_refs(router, parser):
    result = _route(router, parser, 'Sản phẩm nào tương tự "Chupa Chups"?')
    assert "T8" in result.domain_topic_ids
    assert topics.non_sql_refs() & set(result.resolved_refs)


# --- aspects --------------------------------------------------------------

def test_aspects_come_from_request_structure_not_words(router, parser):
    ranked = _route(router, parser, "Sản phẩm nào có giá cao nhất tại VN?")
    assert "A2" in ranked.aspect_topic_ids


def test_routing_hash_changes_with_the_route(router, parser):
    a = _route(router, parser, "Giá trung bình tại Việt Nam")
    b = _route(router, parser, "Lượt bán tháng tại Việt Nam")
    assert a.routing_hash != b.routing_hash
    assert len(a.routing_hash) == 16
    assert a.topic_gate_version == TOPIC_GATE_VERSION


# --- corpus-level quality bound -------------------------------------------

def test_corpus_routing_distribution_does_not_regress(router, parser, corpus):
    """Measured bound, not an aspiration.

    At the time of writing: 71.3% topic_scoped, 13.3% multi_topic, 9.0%
    core_only, 6.4% unknown over 188 questions, with the unknown set being
    almost entirely genuine capability misses (stock, margin, order-level,
    conversion rate). The thresholds sit below the measurement so ordinary
    catalogue growth does not trip them, but a routing regression will.
    """
    assert len(corpus) >= 150
    counts: dict[str, int] = {}
    for question in corpus:
        result = _route(router, parser, question)
        counts[result.mode] = counts.get(result.mode, 0) + 1
    total = sum(counts.values())
    scoped = counts.get("topic_scoped", 0) / total
    unknown = counts.get("unknown", 0) / total
    assert scoped >= 0.65, f"topic_scoped tụt xuống {scoped:.1%}"
    assert unknown <= 0.12, f"unknown tăng lên {unknown:.1%}"
    assert counts.get("overflow", 0) == 0, "router không bao giờ tự đặt overflow"


def _topics_needing_uncollected_data() -> set[str]:
    """Topic mà MỌI ref của nó đọc một artifact bản dữ liệu này chưa thu.

    Không câu hỏi nào trong corpus chạm tới được, và đó không phải lỗi định
    nghĩa: bộ đề viết cho dữ liệu đang có. Tính bằng metadata thay vì liệt kê
    tay, để danh sách miễn trừ TỰ RỖNG đi ngay khi dữ liệu được thu — một
    allowlist viết tay sẽ ở lại mãi và giấu đúng thứ test này đi tìm.
    """
    from gladiators.domain.bindings import default_binding_snapshot
    from gladiators.domain.catalog import CATALOG
    from gladiators.domain.tables import OPTIONAL_ARTIFACTS

    snapshot = default_binding_snapshot()
    uncollected = {
        name.value for name in OPTIONAL_ARTIFACTS if not snapshot.tables[name].columns
    }
    if not uncollected:
        return set()
    blocked = set()
    for card in topics.domains():
        physical = [
            column
            for ref in card.all_refs()
            if ref in CATALOG
            for column in CATALOG[ref].physical
        ]
        if physical and all(col.split(".csv")[0] + ".csv" in uncollected for col in physical):
            blocked.add(card.id)
    return blocked


def test_every_domain_topic_is_reachable_from_the_corpus(router, parser, corpus):
    """A topic no real question routes to is either dead or misdefined."""
    used: set[str] = set()
    for question in corpus:
        used.update(_route(router, parser, question).domain_topic_ids)
    blocked = _topics_needing_uncollected_data()
    missing = sorted({c.id for c in topics.domains()} - used - blocked)
    assert not missing, f"topic không câu hỏi nào chạm tới: {missing}"


def test_the_uncollected_exemption_covers_exactly_the_shop_panel():
    """Miễn trừ ở trên phải HẸP. Nó nới ra tới một topic đọc dữ liệu ĐÃ có là
    lúc nó bắt đầu che một topic chết thật."""
    assert _topics_needing_uncollected_data() == {"T9"}
