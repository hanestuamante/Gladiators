"""Typed Phase 6 settings loaded from YAML with explicit environment overrides."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Mapping

import yaml
from pydantic import BaseModel, ConfigDict, Field


class LiveSearchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    provider: Literal["tavily"] = "tavily"
    # "replay" serves recorded cassettes only and never reaches the network,
    # which is what makes live search usable inside a regression suite (§16 P12).
    mode: Literal["cache_only", "record", "live", "replay"] = "cache_only"
    max_admission: Literal["context_only"] = "context_only"
    max_queries_per_request: int = Field(default=3, ge=1, le=3)
    max_results_per_query: int = Field(default=5, ge=1, le=5)
    daily_query_limit: int = Field(default=150, ge=1)
    cache_dir: str = "data/external_cache"
    cassette_dir: str = "artifacts/search_cassettes"
    quota_path: str = "artifacts/external_quota.json"
    timeout_s: float = Field(default=10.0, gt=0, le=25)
    total_budget_s: float = Field(default=25.0, gt=0, le=25)
    demo_provenance_label: str = Field(
        default="project-demo-approved-context", min_length=1,
        description="Project approval/provenance label; not a legal license identifier.",
    )


class ExternalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    live_search: LiveSearchSettings = Field(default_factory=LiveSearchSettings)


_ENV_MAP = {
    "GLADIATORS_ENABLE_LIVE_SEARCH": ("enabled", lambda value: _bool(value)),
    "GLADIATORS_LIVE_SEARCH_PROVIDER": ("provider", str),
    "GLADIATORS_LIVE_SEARCH_MODE": ("mode", str),
    "GLADIATORS_LIVE_SEARCH_DAILY_LIMIT": ("daily_query_limit", int),
    "GLADIATORS_LIVE_SEARCH_MAX_RESULTS": ("max_results_per_query", int),
    "GLADIATORS_LIVE_SEARCH_MAX_QUERIES": ("max_queries_per_request", int),
    "GLADIATORS_EXTERNAL_CACHE_DIR": ("cache_dir", str),
    "GLADIATORS_EXTERNAL_QUOTA_PATH": ("quota_path", str),
    "GLADIATORS_LIVE_SEARCH_TIMEOUT_SECONDS": ("timeout_s", float),
    "GLADIATORS_LIVE_SEARCH_TOTAL_BUDGET_SECONDS": ("total_budget_s", float),
    "GLADIATORS_DEMO_EXTERNAL_LABEL": ("demo_provenance_label", str),
}


def _bool(value: str) -> bool:
    if value == "1":
        return True
    if value == "0":
        return False
    raise ValueError("Boolean environment override chỉ nhận 0 hoặc 1.")


def load_external_settings(
    config_path: str | Path = "configs/default.yaml", *, environ: Mapping[str, str] | None = None,
) -> ExternalSettings:
    env = os.environ if environ is None else environ
    payload = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    live = dict(payload.get("sources", {}).get("live_search", {}))
    for env_name, (field, converter) in _ENV_MAP.items():
        if env_name in env:
            live[field] = converter(env[env_name])
    return ExternalSettings(live_search=LiveSearchSettings.model_validate(live))
