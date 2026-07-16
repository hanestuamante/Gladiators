from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class TraceStore:
    def __init__(self, root: str | Path = "artifacts/traces", retention_days: int = 30, redact_fields: tuple[str, ...] = ("api_key", "authorization", "password", "token", "email")):
        self.root, self.retention_days, self.redact_fields = Path(root), retention_days, redact_fields
        self.root.mkdir(parents=True, exist_ok=True)

    def redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: ("[REDACTED]" if any(x in k.lower() for x in self.redact_fields) else self.redact(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [self.redact(v) for v in value]
        if isinstance(value, str):
            value = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]", value)
            value = re.sub(r"\bAIza[A-Za-z0-9_-]{20,}\b", "[REDACTED_API_KEY]", value)
            value = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED_TOKEN]", value)
            return value
        return value

    def write(self, trace_id: str, payload: dict) -> Path:
        path = self.root / f"{trace_id}.json"
        path.write_text(json.dumps(self.redact(payload), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        os.chmod(path, 0o600)
        return path

    def prune(self, now: datetime | None = None) -> int:
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=self.retention_days)
        deleted = 0
        for path in self.root.glob("*.json"):
            if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff:
                path.unlink(); deleted += 1
        return deleted
