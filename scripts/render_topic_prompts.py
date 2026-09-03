"""Render canonical topic projections — ultimate solution §6.6.

Writes ``docs/topics/*.md`` from the registry and, with ``--check``, fails when
a checked-in file no longer matches what the code would produce.

The point is not documentation. A hand-editable copy of a topic card is a second
source of truth that drifts from the first, and the drift is invisible until a
reviewer signs off against the stale copy. So the files carry the source hash
they were generated from, and are generated -- never edited.

    python scripts/render_topic_prompts.py           # write
    python scripts/render_topic_prompts.py --check   # verify, exit 1 on drift
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

# The Windows console defaults to cp1252, which cannot encode Vietnamese. Without
# this the script does its work and then dies on its own success message.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from gladiators.domain import topics  # noqa: E402
from gladiators.domain.invariants import INVARIANTS  # noqa: E402
from gladiators.domain.invariants import REGISTRY_HASH as INVARIANT_HASH  # noqa: E402
from gladiators.domain.relations import RELATIONS  # noqa: E402
from gladiators.planner.context_packer import estimate_tokens, render_catalog_ref  # noqa: E402
from gladiators.planner.prompt_library import RENDERER_VERSION  # noqa: E402

OUT_DIR = REPO / "docs" / "topics"
BANNER = "<!-- SINH TỰ ĐỘNG bởi scripts/render_topic_prompts.py — không sửa tay -->"


def render_card(topic_id: str) -> str:
    card = topics.TOPICS[topic_id]
    lines = [
        BANNER,
        f"<!-- topics={topics.REGISTRY_HASH} invariants={INVARIANT_HASH} renderer={RENDERER_VERSION} -->",
        "",
        f"# {card.id} — {card.name}",
        "",
        f"- kind: `{card.kind}`",
        f"- anchor: {', '.join(f'`{a}`' for a in card.anchor_entities) or '—'}",
        f"- kế thừa: {', '.join(f'`{p}`' for p in card.inherits) or '—'}",
        "",
    ]

    owned = [ref for ref in card.owner_refs if ref not in card.non_sql_refs]
    if owned:
        lines += ["## Semantic refs", "", "```text"]
        lines += [render_catalog_ref(ref) for ref in owned]
        lines += ["```", ""]

    if card.non_sql_refs:
        lines += [
            "## Refs không compile sang SQL",
            "",
            "Do tool tính hoặc chỉ là ngữ cảnh ngoài; plan không được address.",
            "",
        ]
        lines += [f"- `{ref}`" for ref in card.non_sql_refs]
        lines += [""]

    if card.relation_paths:
        lines += ["## Relation paths", "", "| path | relation | grain | fanout | dedupe |",
                  "| --- | --- | --- | --- | --- |"]
        for path in card.relation_paths:
            spec = RELATIONS[path.relation_ids[0]]
            lines.append(
                f"| `{path.path_id}` | `{spec.name}` | "
                f"{path.input_grain} → {path.output_grain} | "
                f"{spec.fanout_effect} | {path.dedupe_policy_id or '—'} |"
            )
        lines += [""]

    if card.invariant_ids:
        lines += ["## Invariants", ""]
        for invariant_id in card.invariant_ids:
            spec = INVARIANTS[invariant_id]
            lines.append(f"- `{invariant_id}` ({spec.severity}) — `{spec.message_key}`")
        lines += [""]

    body = "\n".join(lines)
    tokens = estimate_tokens("\n".join(render_catalog_ref(r) for r in owned))
    return body + f"\n<!-- render_budget_tokens={tokens} -->\n"


def render_index() -> str:
    lines = [
        BANNER,
        "",
        "# Topic registry",
        "",
        f"- topics hash: `{topics.REGISTRY_HASH}`",
        f"- invariants hash: `{INVARIANT_HASH}`",
        f"- refs được sở hữu: {len(topics.OWNER_BY_REF)}",
        "",
        "| id | tên | kind | refs | relations | invariants |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for card in sorted(topics.TOPICS.values(), key=lambda c: (c.kind, c.id)):
        lines.append(
            f"| [{card.id}]({card.id}.md) | {card.name} | {card.kind} | "
            f"{len(card.all_refs())} | {len(card.relation_ids)} | {len(card.invariant_ids)} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="so sánh với file đã commit, exit 1 khi lệch")
    args = parser.parse_args()

    rendered = {f"{topic_id}.md": render_card(topic_id) for topic_id in topics.TOPICS}
    rendered["README.md"] = render_index()

    if args.check:
        drift: list[str] = []
        for name, content in sorted(rendered.items()):
            path = OUT_DIR / name
            if not path.exists():
                drift.append(f"{name}: thiếu file")
            elif path.read_text(encoding="utf-8") != content:
                drift.append(f"{name}: lệch so với registry")
        for path in sorted(OUT_DIR.glob("*.md")) if OUT_DIR.exists() else []:
            if path.name not in rendered:
                drift.append(f"{path.name}: topic không còn tồn tại")
        if drift:
            print("Topic projection đã trôi khỏi registry:")
            for line in drift:
                print(f"  - {line}")
            print("\nChạy: python scripts/render_topic_prompts.py")
            return 1
        print(f"OK — {len(rendered)} projection khớp registry {topics.REGISTRY_HASH}")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUT_DIR.glob("*.md"):
        if path.name not in rendered:
            path.unlink()
    for name, content in sorted(rendered.items()):
        (OUT_DIR / name).write_text(content, encoding="utf-8")
    print(f"Đã ghi {len(rendered)} file vào {OUT_DIR.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
