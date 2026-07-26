"""Content-addressed record/replay cassette for LLM calls."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict

from gladiators.contracts import StructuredRequest
from gladiators.external.injection_guard import sanitize_internal_text

CassetteMode = Literal["off", "record", "replay"]


class CassetteMissError(LookupError):
    pass


def cassette_key(
    *,
    provider: str,
    model: str,
    model_revision: str,
    temperature: float,
    top_p: float,
    seed: int | None,
    prompt_version: str,
    purpose: str,
    system_prompt_hash: str,
    tool_schema_hash: str,
    context_hash: str,
    dataset_version: str,
) -> str:
    payload = {
        "provider": provider,
        "model": model,
        "model_revision": model_revision,
        "temperature": temperature,
        "top_p": top_p,
        "seed": seed,
        "prompt_version": prompt_version,
        "purpose": purpose,
        "system_prompt_hash": system_prompt_hash,
        "tool_schema_hash": tool_schema_hash,
        "context_hash": context_hash,
        "dataset_version": dataset_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class CassetteRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = "1.0"
    key: str
    request: dict[str, Any]
    response: Any


_SECRET_KEYS = frozenset({"authorization", "api_key", "x-api-key"})


def _redact(value: Any, key: str | None = None) -> Any:
    if key and key.casefold() in _SECRET_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return sanitize_internal_text(value, max_chars=20_000).text
    return value


class LLMCassette:
    def __init__(
        self,
        root: str | Path = "tests/fixtures/cassettes",
        mode: CassetteMode | None = None,
    ):
        configured = mode or os.getenv("GLADIATORS_CASSETTE_MODE", "off")
        if configured not in {"off", "record", "replay"}:
            raise ValueError("GLADIATORS_CASSETTE_MODE phải là off, record hoặc replay.")
        self.root = Path(root)
        self.mode: CassetteMode = configured

    def _path(self, key: str) -> Path:
        if len(key) != 64 or any(ch not in "0123456789abcdef" for ch in key):
            raise ValueError("cassette key không hợp lệ")
        return self.root / f"{key}.json"

    def read(self, key: str) -> Any:
        path = self._path(key)
        if not path.exists():
            raise CassetteMissError(f"Không có cassette cho key={key}")
        record = CassetteRecord.model_validate_json(path.read_text(encoding="utf-8"))
        if record.key != key:
            raise RuntimeError("Cassette key không khớp nội dung.")
        return record.response

    def write(self, key: str, request: dict[str, Any], response: Any) -> Any:
        path = self._path(key)
        record = CassetteRecord(
            key=key, request=_redact(request), response=_redact(response),
        )
        encoded = json.dumps(
            record.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_text(encoding="utf-8") != encoded:
                raise RuntimeError("Immutable cassette collision.")
            return response
        temp = path.with_name(path.name + f".{os.getpid()}.tmp")
        temp.write_text(encoded, encoding="utf-8")
        os.replace(temp, path)
        return response

    def call(
        self,
        key: str,
        request: dict[str, Any],
        provider_call: Callable[[], Any],
    ) -> Any:
        if self.mode == "replay":
            return self.read(key)
        response = provider_call()
        if self.mode == "record":
            self.write(key, request, response)
        return response


_PURPOSES = {
    "parse_intent": "P1",
    "generate": "P2",
    "judge": "P3",
    "plan_live_search": "P5",
    "extract_web": "P6",
    "plan_analytical": "P8",
    "critique_plan": "P9",
    "plan_analytical_alternate": "P10",
    "adjudicate_plans": "P11",
}


def _stable_hash(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CassetteLLMClient:
    """Record/replay proxy for every provider-facing LLM protocol method.

    In replay mode ``delegate`` may be ``None``.  A miss raises before any
    provider code can run, which makes offline provider-path regression
    deterministic and socket-free.
    """

    def __init__(
        self,
        delegate: Any | None,
        *,
        provider: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        dataset_version: str,
        cassette: LLMCassette | None = None,
        model_revision: str | None = None,
    ):
        if delegate is None and not provider:
            raise ValueError("Replay client cần provider định danh.")
        self._delegate = delegate
        self.provider = provider or str(delegate.provider)
        self.model = model or str(delegate.model)
        self.prompt_version = prompt_version or str(delegate.prompt_version)
        self.model_revision = (
            model_revision
            or str(getattr(delegate, "model_revision", self.model))
        )
        self.dataset_version = dataset_version
        self.cassette = cassette or LLMCassette()

    def _invoke(self, method: str, *args: Any, **kwargs: Any) -> Any:
        request = {"method": method, "args": list(args), "kwargs": kwargs}
        context_source = kwargs.get("context_bundle") or (
            args[0] if len(args) == 1 and isinstance(args[0], dict) else request
        )
        if isinstance(context_source, dict):
            context_hash = str(context_source.get("context_hash") or _stable_hash(context_source))
        else:
            context_hash = _stable_hash(context_source)
        key = cassette_key(
            provider=self.provider,
            model=self.model,
            model_revision=self.model_revision,
            temperature=0.0,
            top_p=1.0,
            seed=0,
            prompt_version=self.prompt_version,
            purpose=_PURPOSES[method],
            system_prompt_hash=_stable_hash(
                "untrusted-input; evidence-only; no-secret-disclosure",
            ),
            tool_schema_hash=_stable_hash({"method": method, "protocol": "LLMClient-v1"}),
            context_hash=context_hash,
            dataset_version=self.dataset_version,
        )

        def provider_call() -> Any:
            if self._delegate is None:
                raise CassetteMissError(
                    f"Replay không được gọi provider cho {method}; cassette bị thiếu.",
                )
            result = getattr(self._delegate, method)(*args, **kwargs)
            if isinstance(result, BaseModel):
                return {
                    "__pydantic_type__": (
                        f"{result.__class__.__module__}:{result.__class__.__qualname__}"
                    ),
                    "value": result.model_dump(mode="json"),
                }
            return result

        result = self.cassette.call(key, request, provider_call)
        if method == "parse_intent":
            if isinstance(result, StructuredRequest):
                return result
            if isinstance(result, dict) and result.get("__pydantic_type__"):
                result = result["value"]
            return StructuredRequest.model_validate(result)
        return result

    def parse_intent(self, text: str, intent_names: tuple[str, ...]) -> StructuredRequest:
        return self._invoke("parse_intent", text, intent_names)

    def generate(self, context: dict) -> str:
        return self._invoke("generate", context)

    def judge(self, answer: str, rubric: str) -> dict:
        return self._invoke("judge", answer, rubric)

    def critique_plan(self, question: str, plan: dict) -> dict:
        return self._invoke("critique_plan", question, plan)

    def plan_analytical(self, payload: dict) -> dict:
        return self._invoke("plan_analytical", payload)

    def plan_analytical_alternate(self, payload: dict) -> dict:
        return self._invoke("plan_analytical_alternate", payload)

    def adjudicate_plans(self, payload: dict) -> dict:
        return self._invoke("adjudicate_plans", payload)

    def plan_live_search(self, payload: dict) -> dict:
        return self._invoke("plan_live_search", payload)

    def extract_web(self, payload: dict) -> dict:
        return self._invoke("extract_web", payload)

    def telemetry(self) -> dict:
        base = (
            self._delegate.telemetry()
            if self._delegate is not None and hasattr(self._delegate, "telemetry")
            else {}
        )
        return {**base, "cassette_mode": self.cassette.mode}
