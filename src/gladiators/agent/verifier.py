from __future__ import annotations

import math
import re

from gladiators.contracts import Evidence


NUMBER = re.compile(r"(?<![\w-])-?\d+(?:[.,]\d+)?%?")


def scan_numbers(text: str) -> list[float]:
    values = []
    for token in NUMBER.findall(text):
        token = token.rstrip("%").replace(",", ".")
        values.append(float(token))
    return values


def verify_numeric_claims(text: str, evidence: list[Evidence], tolerance: float = 0.011) -> dict:
    metric_text = text
    ignored_strings = []
    for item in evidence:
        metric_text = metric_text.replace(item.evidence_id, "")
        for value in item.attrs.values():
            if isinstance(value, str) and value:
                ignored_strings.append(value)
    for value in sorted(set(ignored_strings), key=len, reverse=True):
        metric_text = metric_text.replace(value, "")
    claimed = scan_numbers(metric_text)
    allowed = [float(e.value) for e in evidence if isinstance(e.value, (int, float)) and not isinstance(e.value, bool)]
    unsupported = [n for n in claimed if not any(math.isclose(n, a, rel_tol=tolerance, abs_tol=tolerance) for a in allowed)]
    return {"passed": not unsupported, "claimed": claimed, "allowed": allowed, "unsupported": unsupported, "coverage": 1.0 if not claimed else (len(claimed) - len(unsupported)) / len(claimed)}
