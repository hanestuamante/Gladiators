"""P0 regression lock — docs/ultimate solution.md §16 P0.

Locks the runtime's current behaviour on six probes *before* any P1+ package
changes it, so every later commit has to prove it is an improvement rather than
a regression.  Four independent layers are pinned per probe, deliberately kept
separate so each fails with its own message:

``action``
    ``gate.action`` and ``gate.rule_id``.  Never ``gate.reason`` — reasons are
    wording, rule ids are contract.
``plan``
    ``planning.plan_id`` + sorted ``semantic_refs`` for template plans, or
    ``macro`` + ``macro_version`` for certified macros.
``oracle``
    ``(metric, value)`` equality plus ``attrs`` *subset* containment, so adding
    a new attr does not break the lock.  Every number is cross-checked against
    ``eval/independent/p0_probe_expected.json``, which imports no gladiators
    code — it is never recomputed here.
``answer``
    Citation linkage (every evidence id appears in the answer) plus a short
    curated marker list.  ``evidence_id`` embeds a uuid4, so literals are never
    pinned.

Three probes are genuine ALLOW-sai contracts that are red today and carry
``xfail(strict=True, raises=AssertionError)``.  ``strict`` turns the eventual
fix into a hard XPASS failure; ``raises`` stops a probe from xfailing for the
wrong reason if the runtime starts crashing instead of answering wrongly.

**Flipping a case after P1 fixes it** — do all of this, and never edit an
assertion body:

1. set ``expected_state`` to ``"green"`` and fill ``fixed_in``/``fixed_at`` in
   ``eval/p0_probes.json``;
2. paste the new observed block into that case's ``baseline`` from a fresh
   ``artifacts/release/<run_id>/baseline_red_proof.json``, cross-checked against
   the independent oracle;
3. re-run ``scripts/build_release_proof.py`` and diff against the P0 proof —
   that diff is the §17 before/after evidence.

Expect 2–3 tests to fail for a single fix (the contract XPASSes *and* the
baseline locks move).  That is the point of "khoá oracle/action/plan/answer".
"""
from __future__ import annotations

import ast
import json
import runpy
from pathlib import Path

import pytest

from gladiators.agent.workflow import AgentRuntime


PROBES = json.loads(Path("eval/p0_probes.json").read_text(encoding="utf-8"))
PROBES_BY_ID = {case["id"]: case for case in PROBES["cases"]}
DR2607 = {
    case["id"]: case
    for case in json.loads(Path("eval/dr2607.json").read_text(encoding="utf-8"))
}
ORACLE = {
    record["case_id"]: record
    for record in json.loads(
        Path("eval/independent/p0_probe_expected.json").read_text(encoding="utf-8"),
    )
}
CASE_IDS = [case["id"] for case in PROBES["cases"]]
RED_IDS = [case["id"] for case in PROBES["cases"] if case["kind"] == "red"]

# Populated by @contract_test at import time; asserted complete below.
CONTRACT_TESTS: dict[str, str] = {}


def probe_question(case: dict) -> str:
    """Probe questions either stand alone or are borrowed from the DR40 suite."""
    if case["question"] is not None:
        return case["question"]
    return DR2607[case["dr2607_id"]]["question"]


def contract_test(case_id: str):
    """Mark a contract test, xfailing it while the fixture still says ``red``."""
    case = PROBES_BY_ID[case_id]
    CONTRACT_TESTS[case_id] = case["kind"]

    def wrap(fn):
        fn = pytest.mark.p0_contract(case_id)(fn)
        if case["expected_state"] == "red":
            fn = pytest.mark.xfail(
                reason=f"{case_id}: {case['red_reason']}",
                strict=True,
                raises=AssertionError,
            )(fn)
        return fn

    return wrap


@pytest.fixture(scope="module")
def runtime(tmp_path_factory) -> AgentRuntime:
    return AgentRuntime(trace_dir=tmp_path_factory.mktemp("p0-traces"))


@pytest.fixture(scope="module")
def responses(runtime):
    return {case["id"]: runtime.run(probe_question(case)) for case in PROBES["cases"]}


# --------------------------------------------------------------------- meta --


def test_probe_file_schema_and_ids_do_not_collide_with_dr2607():
    assert PROBES["schema_version"] == "p0-probes.v1"
    assert len(CASE_IDS) == len(set(CASE_IDS))
    dr_questions = {case["question"] for case in DR2607.values()}
    for case in PROBES["cases"]:
        cid = case["id"]
        assert cid.startswith("p0-"), cid
        assert case["kind"] in {"red", "guard_rail", "oracle_lock"}, cid
        assert case["expected_state"] in {"red", "green"}, cid
        assert (case["question"] is None) != (case["dr2607_id"] is None), cid
        assert case["spec_ref"], cid
        assert case["oracle_ref"].split("#")[-1] in ORACLE, cid
        assert case["contract"]["statement"], cid
        if case["dr2607_id"] is not None:
            assert case["dr2607_id"] in DR2607, cid
        else:
            # Authored probes must stay outside the 40-case DR suite, otherwise
            # they would be silently smuggled into a lock they do not belong to.
            assert case["question"] not in dr_questions, cid


def test_dataset_version_matches_pinned_oracle(runtime):
    assert runtime.repo.dataset_version == PROBES["dataset_version"], (
        "data/processed changed since the P0 baselines were captured; every pinned "
        "number below is stale. Regenerate eval/independent/p0_probe_expected.json "
        "and re-capture the baselines before trusting any failure in this module."
    )


def test_every_probe_case_has_a_contract_test():
    assert set(CONTRACT_TESTS) == set(CASE_IDS)


def test_no_red_case_is_silently_marked_green():
    for case in PROBES["cases"]:
        if case["kind"] == "red" and case["expected_state"] == "green":
            assert case["fixed_in"] and case["fixed_at"], (
                f"{case['id']} was flipped to green without recording fixed_in/fixed_at"
            )


def test_independent_p0_oracle_has_no_source_import_and_matches_checked_in_denotation():
    path = Path("eval/independent/p0_probe_oracle.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    imported.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not any(name.startswith("gladiators") for name in imported)
    module = runpy.run_path(str(path))
    expected = json.loads(
        Path("eval/independent/p0_probe_expected.json").read_text(encoding="utf-8"),
    )
    assert module["build"]() == expected


# ----------------------------------------------------------- baseline locks --


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_baseline_action_and_rule_are_pinned(case_id, responses):
    baseline = PROBES_BY_ID[case_id]["baseline"]
    response = responses[case_id]
    assert response.gate.action == baseline["action"], case_id
    assert response.gate.rule_id == baseline["rule_id"], case_id


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_baseline_plan_identity_is_pinned(case_id, responses):
    baseline = PROBES_BY_ID[case_id]["baseline"]["planning"]
    planning = responses[case_id].planning
    for key in ("mode", "macro", "macro_version", "plan_id", "a19_rule"):
        if key in baseline:
            assert planning.get(key) == baseline[key], f"{case_id}.{key}"
    if "semantic_refs" in baseline:
        assert sorted(planning.get("semantic_refs", [])) == sorted(
            baseline["semantic_refs"],
        ), case_id


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_baseline_evidence_denotation_is_pinned(case_id, responses):
    baseline = PROBES_BY_ID[case_id]["baseline"]["evidence"]
    evidence = responses[case_id].evidence
    assert [(item.metric, item.value, item.unit) for item in evidence] == [
        (item["metric"], item["value"], item["unit"]) for item in baseline
    ], case_id
    for observed, pinned in zip(evidence, baseline):
        # Subset containment: a new attr must not break the lock, a changed one must.
        missing = {
            key: value for key, value in pinned["attrs"].items()
            if observed.attrs.get(key) != value
        }
        assert not missing, f"{case_id}/{observed.metric} attrs drifted: {missing}"


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_baseline_answer_is_evidence_linked_and_marker_stable(case_id, responses):
    baseline = PROBES_BY_ID[case_id]["baseline"]
    response = responses[case_id]
    for item in response.evidence:
        assert f"[{item.evidence_id}]" in response.answer, (
            f"{case_id}: evidence {item.metric} is not cited in the answer"
        )
    for marker in baseline["answer_markers"]:
        assert marker in response.answer, f"{case_id}: missing marker {marker!r}"
    for marker in baseline["answer_absent"]:
        assert marker not in response.answer, f"{case_id}: unexpected marker {marker!r}"
    assert len(response.claims) == baseline["n_claims"], case_id
    evidence_ids = {item.evidence_id for item in response.evidence}
    assert all(claim.evidence_id in evidence_ids for claim in response.claims), case_id


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_baseline_request_scope_is_pinned(case_id, responses):
    baseline = PROBES_BY_ID[case_id]["baseline"]["request_countries"]
    assert list(responses[case_id].request.countries) == baseline, case_id


# ------------------------------------------------------- guard rails / oracle --


@contract_test("p0-tc19-sentinel-premise")
def test_tc19_never_allows_while_dr1_is_pending(responses):
    case = PROBES_BY_ID["p0-tc19-sentinel-premise"]
    # §1.5: the runtime may only act on approved data decisions. Whether this
    # listing's price may anchor a ±20% comparison is still pending, so allow is
    # forbidden regardless of which reason the gate happens to give today.
    assert case["dr1_status"] == "pending"
    assert DR2607["tc19"]["status"] == "needs_human_policy_oracle"
    assert ORACLE["p0_tc19_sentinel_ref"]["value"]["dr1_status"] == "pending"
    assert responses["p0-tc19-sentinel-premise"].gate.action != "allow"


@contract_test("p0-tc23-voucher-oracle")
def test_tc23_matches_independent_latest_snapshot_voucher_oracle(responses):
    response = responses["p0-tc23-voucher-oracle"]
    oracle = ORACLE["p0_tc23_voucher_latest"]["value"]
    observed = {
        str(item.attrs["country"]): int(item.value) for item in response.evidence
    }
    assert observed == oracle["counts"]
    assert {str(item.attrs["snapshot_date"]) for item in response.evidence} == {
        oracle["snapshot_date"],
    }
    assert all(item.attrs.get("sub_id") == "sr1" for item in response.evidence)
    assert "Chưa trả lời được" in response.answer


@contract_test("p0-gap-item-42955556831")
def test_snapshot_gap_item_never_allows_a_transition_delta(responses):
    response = responses["p0-gap-item-42955556831"]
    transition = ORACLE["p0_gap_item_42955556831"]["value"]["transitions"][0]
    assert transition["transition_metric_eligible"] is False
    assert transition["days_since_previous"] == 2
    assert response.gate.action != "allow"
    # monthly_sold is flat 4000 -> 4000 across the gap, so "compute it anyway"
    # yields a confident 0 that reads as "no decline". Forbid the metric itself,
    # not merely a non-zero value.
    assert not any(item.metric == "monthly_sold_delta" for item in response.evidence)


@contract_test("p0-grouping-dropped-official-shop")
def test_dimension_named_in_question_must_not_be_dropped_by_the_plan(responses):
    response = responses["p0-grouping-dropped-official-shop"]
    oracle = ORACLE["p0_grouping_official_shop"]["value"]
    # The wrong answer and the right one differ by 203 listings, so a regression
    # that re-allows the template is not a rounding difference.
    assert oracle["vn_all_listings"] != oracle["vn_official_shop_listings"]
    assert response.gate.action != "allow"
    assert str(oracle["vn_all_listings"]) not in response.answer


@contract_test("p0-date-point-substituted")
def test_named_date_must_not_be_substituted_by_the_latest_snapshot(responses):
    response = responses["p0-date-point-substituted"]
    by_date = ORACLE["p0_date_point_vn"]["value"]["by_date"]
    # Every snapshot has a different count, so substituting one for another is a
    # wrong answer rather than a defensible default.
    counts = {entry["listing_count"] for entry in by_date.values()}
    assert len(counts) == len(by_date)
    assert response.gate.action != "allow"
    assert str(by_date["2026-07-03"]["listing_count"]) not in response.answer


@contract_test("p0-rank-direction-inverted")
def test_ascending_ranking_must_not_be_answered_by_a_descending_template(responses):
    response = responses["p0-rank-direction-inverted"]
    oracle = ORACLE["p0_rank_direction_vn"]["value"]
    # ~3000x apart, so an inverted answer can never be mistaken for a near miss.
    assert oracle["max_price"] > oracle["min_price"] * 1000
    assert str(int(oracle["max_price"])) not in response.answer
    if response.gate.action == "allow":
        # Answering is allowed only with the actual minimum, and the sentence
        # must not call it the maximum.
        assert any(
            item.metric == "price" and item.value == oracle["min_price"]
            for item in response.evidence
        )
        assert oracle["min_price_product"] in response.answer


# ------------------------------------------------------------ red contracts --


@contract_test("p0-tc34-date-window-narrowing")
def test_tc34_date_window_must_not_be_narrowed(responses):
    response = responses["p0-tc34-date-window-narrowing"]
    asked = ORACLE["p0_tc34_window"]["value"]["asked_window"]
    window = {
        (str(item.attrs.get("previous_date")), str(item.attrs.get("date")))
        for item in response.evidence
        if item.metric == "monthly_sold_delta"
    }
    covered = bool(window) and min(start for start, _ in window) == asked[0] \
        and max(end for _, end in window) == asked[1]
    assert response.gate.action != "allow" or covered, (
        f"§4.4: hỏi {asked[0]}→{asked[1]} nhưng evidence chỉ phủ {sorted(window)}"
    )


@contract_test("p0-scope-dropped-vn-id")
def test_multi_country_scope_must_not_be_dropped(responses):
    response = responses["p0-scope-dropped-vn-id"]
    asked = set(response.request.countries)
    covered = {
        str(item.attrs["country"])
        for item in response.evidence
        if item.attrs.get("country")
    }
    assert response.gate.action != "allow" or covered >= asked, (
        f"§4.4: hỏi {sorted(asked)} nhưng evidence chỉ phủ {sorted(covered)}"
    )


@contract_test("p0-plurality-top-k")
def test_plural_ranking_must_not_collapse_to_top_1(responses):
    response = responses["p0-plurality-top-k"]
    # Count distinct listings, never len(evidence): this template emits two
    # Evidence objects (product_name + price) for a single listing.
    listings = {
        str(item.attrs["product_name"])
        for item in response.evidence
        if item.attrs.get("product_name")
    }
    assert len(ORACLE["p0_plurality_top_prices"]["value"]["candidates"]) > 1
    assert response.gate.action != "allow" or len(listings) > 1, (
        f"§4.4 shape: hỏi số nhiều nhưng chỉ trả {len(listings)} listing"
    )
