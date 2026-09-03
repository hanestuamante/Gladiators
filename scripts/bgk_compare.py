"""Score the agent run against ground truth.

Scoring is by *outcome class*, not string equality, because the two artifacts
speak different languages: the oracle emits a number, the agent emits a Vietnamese
sentence carrying that number. What matters is whether the number the reader ends
up with is the right one, and whether a refusal was the right move.

Four outcomes:
  correct        answerable question, answered, value matches the oracle
  wrong_value    answered, value does not match  -- the dangerous class
  missed         answerable question, refused or asked back -- the usefulness cost
  correct_refuse question the oracle says has no determinate answer, and refused
"""
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)

from collections import Counter

runs = json.load(open("artifacts/bgk_agent_run.json", encoding="utf-8"))

NUMBER = re.compile(r"-?\d[\d.,]*")


def numbers_in(text: str) -> set[float]:
    found = set()
    for token in NUMBER.findall(text or ""):
        cleaned = token.replace(".", "").replace(",", "")
        if cleaned.isdigit():
            found.add(float(cleaned))
        else:
            try:
                found.add(float(token.replace(",", ".")))
            except ValueError:
                pass
    return found


def truth_numbers(value) -> set[float]:
    if isinstance(value, (int, float)):
        return {float(value)}
    if isinstance(value, dict):
        return {float(v) for v in value.values() if isinstance(v, (int, float))}
    return set()


rows = []
for record in runs:
    expected = record["verdict_expected"]
    answered = record["action"] == "allow"
    wanted = truth_numbers(record["ground_truth"])
    shown = numbers_in(record["answer"]) | {
        float(v) for _, v in record["evidence"] if isinstance(v, (int, float))
    }

    if expected in {"must_refuse", "undetermined", "false_premise"}:
        outcome = "correct_refuse" if not answered else "wrong_value"
    elif not answered:
        outcome = "missed"
    elif wanted and wanted & shown:
        outcome = "correct"
    elif not wanted:
        outcome = "correct" if record["verified"] else "wrong_value"
    else:
        outcome = "wrong_value"

    rows.append({**record, "outcome": outcome,
                 "truth_numbers": sorted(wanted), "shown_numbers": sorted(shown)[:8]})

json.dump(rows, open("artifacts/bgk_scored.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

counts = Counter(r["outcome"] for r in rows)
print("=== kết quả ===")
for key in ("correct", "correct_refuse", "missed", "wrong_value"):
    print(f"  {key:16s} {counts.get(key, 0):2d}")
answerable = [r for r in rows if r["verdict_expected"] == "answerable"]
hit = sum(1 for r in answerable if r["outcome"] == "correct")
print(f"\n  câu ĐÁNG LẼ trả lời được : {len(answerable)}")
print(f"  trong đó trả lời đúng     : {hit}  ({hit / max(1, len(answerable)):.0%})")
print(f"  trong đó bị từ chối       : {sum(1 for r in answerable if r['outcome'] == 'missed')}")
print(f"\n  số hiển thị sai (nguy hiểm): {counts.get('wrong_value', 0)}")

print("\n=== chi tiết ===")
for r in rows:
    print(f"{r['id']} [{r['group']}] {r['outcome']:14s} {r['action']:8s} {r['rule']:22s} "
          f"{r['seconds']:6.1f}s")
