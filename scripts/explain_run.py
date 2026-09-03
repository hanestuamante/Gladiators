"""Chay cau hoi qua AgentRuntime va in tung buoc xu ly de debug/hoc kien truc.

Doc truc tiep tu AgentResponse contract (request/gate/tool_calls/evidence/llm/
verification) nen khong hardcode theo tung intent cu the - them intent/tool moi
trong registry thi script nay tu dong hien dung, khong can sua.

Cach dung:
    PYTHONPATH=src python scripts/explain_run.py "cau hoi cua ban"   # 1 lan roi thoat
    PYTHONPATH=src python scripts/explain_run.py                    # REPL, go lien tuc
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gladiators.agent.workflow import AgentRuntime


def line(char: str = "-", width: int = 70) -> str:
    return char * width


def section(title: str) -> None:
    print()
    print(line("="))
    print(f"  {title}")
    print(line("="))


def explain(question: str, runtime: AgentRuntime) -> None:
    section("INPUT")
    print(f"  raw_text = {question!r}")

    response = runtime.run(question)

    section("BUOC 1 - PARSE (deterministic regex, khong goi LLM)")
    r = response.request
    print(f"  intent      = {r.intent}")
    print(f"  entity_text = {r.entity_text!r}")
    print(f"  country     = {r.country!r}")
    print(f"  language    = {r.language}")

    section("BUOC 2 - GATE (cong kiem tra co duoc phep chay khong)")
    g = response.gate
    icon = {"allow": "[ALLOW]", "clarify": "[CLARIFY]", "abstain": "[ABSTAIN]"}[g.action]
    print(f"  {icon} action = {g.action}")
    print(f"  rule_id = {g.rule_id}")
    print(f"  reason  = {g.reason}")
    if g.answerable_alternative:
        print(f"  goi y   = {g.answerable_alternative}")

    if g.action != "allow":
        section("DUNG TAI GATE - khong chay tool, khong goi LLM generation")
        print(f"  answer = {response.answer}")
        return

    section("BUOC 3 - ENTITY RESOLUTION + TOOL CALL")
    if response.resolved_listing_key:
        print(f"  resolved_listing_key = {response.resolved_listing_key}")
    else:
        print("  (khong can resolve entity cho intent nay)")
    for call in response.tool_calls:
        print(f"  tool: {call.name}({call.args}) -> status={call.status}")
        if call.error:
            print(f"    error = {call.error}")

    section(f"BUOC 4 - EVIDENCE THU DUOC ({len(response.evidence)} muc)")
    for ev in response.evidence[:8]:
        print(f"  [{ev.evidence_id}] {ev.metric} = {ev.value} {ev.unit or ''}  (tier={ev.source_tier})")
    if len(response.evidence) > 8:
        print(f"  ... con {len(response.evidence) - 8} evidence nua")

    section("BUOC 5 - GENERATION LOOP (sinh cau tra loi)")
    gen = response.llm.get("generation", {})
    provider = response.llm.get("provider", "deterministic")
    print(f"  provider = {provider}")
    if provider == "deterministic":
        print("  -> dung template co san trong _deterministic_answer(), KHONG goi LLM")
    else:
        print(f"  attempts = {gen.get('attempts')}  fallback = {gen.get('fallback')}")
        if gen.get("errors"):
            print(f"  errors (loop retry vi verifier tu choi) = {gen['errors']}")

    section("BUOC 6 - VERIFIER (kiem tra moi con so co evidence khong)")
    v = response.verification
    print(f"  passed   = {v.get('passed')}")
    print(f"  claimed  = {v.get('claimed')}")
    print(f"  coverage = {v.get('coverage')}")
    if v.get("unsupported"):
        print(f"  UNSUPPORTED (bi tu choi, roi ve deterministic) = {v['unsupported']}")

    section("OUTPUT CUOI CUNG")
    print(f"  degraded = {response.degraded}")
    print(f"  answer   =")
    print(f"  {response.answer}")


def repl(runtime: AgentRuntime) -> None:
    print(line("#"))
    print("  CHE DO LIVE - go cau hoi roi Enter, go 'exit' hoac Ctrl+C de thoat")
    print(line("#"))
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nThoat.")
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit", "q"}:
            print("Thoat.")
            break
        try:
            explain(question, runtime)
        except Exception as exc:
            print(f"  LOI khi chay agent: {type(exc).__name__}: {exc}")
        print(line("#"))


if __name__ == "__main__":
    runtime = AgentRuntime()
    if len(sys.argv) > 1:
        explain(" ".join(sys.argv[1:]), runtime)
        print()
        print(line("#"))
    else:
        repl(runtime)
