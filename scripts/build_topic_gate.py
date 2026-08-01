"""Topic gate report — ultimate solution §6.4 / §7.3.

Routing may only be enabled when it demonstrably loses nothing.  §7.3 sets the
conditions: required-ref recall 100%, required-relation recall 100%, plan-valid
rate not down, ``false_allow_rate`` 0, and every adversarial topic case passing.

Two things this deliberately does not do:

**It does not pass on token reduction.**  Token cost is a secondary goal per
§7.3 and is reported but never gates. A slice that is cheap and wrong is worse
than the broad slice it replaced.

**It does not decide the recall thresholds it cannot verify.**  Required-ref
recall needs an oracle listing what each question genuinely needs, and that
oracle is a reviewer artifact (§1.5). Where it is absent the report says
``pending_oracle`` and the gate stays shut -- it does not score itself against
its own routing and call that recall.

    python scripts/build_topic_gate.py [--output eval/topic_gate.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from gladiators.domain import topics  # noqa: E402
from gladiators.domain.alias_index import default_alias_index  # noqa: E402
from gladiators.domain.catalog import CATALOG  # noqa: E402
from gladiators.domain.invariants import REGISTRY_HASH as INVARIANT_HASH  # noqa: E402
from gladiators.planner.context_packer import estimate_tokens, render_catalog_ref  # noqa: E402
from gladiators.planner.semantic_parser import DeterministicSemanticParser  # noqa: E402
from gladiators.planner.topic_router import TopicRouter  # noqa: E402

SCHEMA_VERSION = "topic-gate-report.v1"

# Bounds below the measured values, so ordinary catalogue growth does not trip
# them but a routing regression does.
MIN_TOPIC_SCOPED_RATE = 0.65
MAX_UNKNOWN_RATE = 0.12
MAX_OVERFLOW_RATE = 0.02


def corpus() -> list[str]:
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

    for path in glob.glob(str(REPO / "eval" / "**" / "*.json"), recursive=True):
        try:
            walk(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(set(found))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(REPO / "eval" / "topic_gate.json"))
    args = parser.parse_args()

    router = TopicRouter()
    semantic = DeterministicSemanticParser()
    questions = corpus()

    modes: dict[str, int] = {}
    domain_hits: dict[str, int] = {}
    routed_tokens: list[int] = []
    unresolved_examples: list[str] = []

    for question in questions:
        result = router.route(question, semantic.parse(question, "vi", "vn"))
        modes[result.mode] = modes.get(result.mode, 0) + 1
        for topic_id in result.domain_topic_ids:
            domain_hits[topic_id] = domain_hits.get(topic_id, 0) + 1
        refs = [r for r in result.effective_refs() if r not in topics.non_sql_refs()]
        routed_tokens.append(estimate_tokens("\n".join(render_catalog_ref(r) for r in refs)))
        if result.mode == "unknown" and len(unresolved_examples) < 25:
            unresolved_examples.append(question)

    total = max(1, len(questions))
    routed_tokens.sort()
    broad_tokens = estimate_tokens("\n".join(render_catalog_ref(r) for r in CATALOG))

    rates = {mode: count / total for mode, count in modes.items()}
    unreachable = sorted({card.id for card in topics.domains()} - set(domain_hits))

    checks = {
        "topic_scoped_rate": {
            "value": rates.get("topic_scoped", 0.0),
            "threshold": MIN_TOPIC_SCOPED_RATE,
            "pass": rates.get("topic_scoped", 0.0) >= MIN_TOPIC_SCOPED_RATE,
        },
        "unknown_rate": {
            "value": rates.get("unknown", 0.0),
            "threshold": MAX_UNKNOWN_RATE,
            "pass": rates.get("unknown", 0.0) <= MAX_UNKNOWN_RATE,
        },
        "topic_overflow_rate": {
            "value": rates.get("overflow", 0.0),
            "threshold": MAX_OVERFLOW_RATE,
            "pass": rates.get("overflow", 0.0) <= MAX_OVERFLOW_RATE,
        },
        "every_domain_reachable": {
            "value": unreachable, "threshold": [], "pass": not unreachable,
        },
        "ownership_is_a_partition": {
            "value": len(topics.OWNER_BY_REF), "threshold": len(CATALOG),
            "pass": set(topics.OWNER_BY_REF) == set(CATALOG),
        },
    }

    # §1.5: these need a reviewer-owned oracle. Reporting a self-scored number
    # here would let routing gate itself on its own opinion.
    pending = {
        "required_ref_recall": "pending_oracle",
        "required_relation_recall": "pending_oracle",
        "plan_valid_rate_delta": "pending_oracle",
        "false_allow_rate": "pending_oracle",
        "false_abstain_rate": "pending_oracle",
        "adversarial_topic_cases": "pending_oracle",
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "topics_hash": topics.REGISTRY_HASH,
        "invariants_hash": INVARIANT_HASH,
        "alias_index_hash": default_alias_index().index_hash,
        "corpus_size": len(questions),
        "routing": {
            "modes": modes,
            "rates": rates,
            "domain_usage": dict(sorted(domain_hits.items())),
        },
        "context_tokens": {
            "broad_slice": broad_tokens,
            "routed_p50": routed_tokens[len(routed_tokens) // 2] if routed_tokens else 0,
            "routed_p95": routed_tokens[int(len(routed_tokens) * 0.95)] if routed_tokens else 0,
            "routed_max": routed_tokens[-1] if routed_tokens else 0,
            "routed_mean": round(statistics.fmean(routed_tokens), 1) if routed_tokens else 0,
            "note": "Token là mục tiêu phụ (§7.3) — báo cáo, không dùng để gate.",
        },
        "checks": checks,
        "pending_reviewer_signoff": pending,
        "unknown_examples": unresolved_examples,
        # The gate stays shut while any reviewer-owned metric is unverified,
        # regardless of how good the automatic checks look.
        "automatic_checks_pass": all(c["pass"] for c in checks.values()),
        "gate_open": False,
        "gate_blocked_by": sorted(pending),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"Topic gate → {output.relative_to(REPO)}")
    for name, check in checks.items():
        mark = "PASS" if check["pass"] else "FAIL"
        print(f"  [{mark}] {name}: {check['value']}")
    print(f"  token: broad {broad_tokens} → routed p50 {report['context_tokens']['routed_p50']}")
    print(f"  gate_open=False, chờ reviewer: {', '.join(report['gate_blocked_by'])}")
    return 0 if report["automatic_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
