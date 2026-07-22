from __future__ import annotations

import os

from dotenv import load_dotenv

from gladiators.agent.llm import GeminiLLMClient, GroqLLMClient, HuggingFaceLLMClient
from gladiators.agent.workflow import AgentRuntime
from gladiators.external.cache import ExternalCache, QuotaGuard
from gladiators.external.pipeline import ExternalContextPipeline
from gladiators.external.search_executor import SearchExecutor
from gladiators.external.search_planner import LiveSearchPlanner
from gladiators.external.search_provider import TavilyProvider
from gladiators.external.web_extract import WebExtractor


def create_runtime(provider: str | None = None) -> AgentRuntime:
    load_dotenv()
    selected = provider or os.getenv("GLADIATORS_LLM_PROVIDER", "offline")
    if selected not in {"offline", "gemini", "huggingface", "groq"}:
        raise ValueError(f"Provider không hỗ trợ: {selected}")
    live_enabled = os.getenv("GLADIATORS_ENABLE_LIVE_SEARCH") == "1"
    live_license = os.getenv("GLADIATORS_LIVE_SEARCH_LICENSE", "").strip()
    if live_enabled and os.getenv("GLADIATORS_LIVE_SOURCE_REVIEWED") != "1":
        raise RuntimeError("Live search bị chặn: source/license review chưa được xác nhận.")
    if live_enabled and not live_license:
        raise RuntimeError("Live search bị chặn: thiếu GLADIATORS_LIVE_SEARCH_LICENSE đã được duyệt.")
    llm = GeminiLLMClient() if selected == "gemini" else HuggingFaceLLMClient() if selected == "huggingface" else GroqLLMClient() if selected == "groq" else None
    external_pipeline = None
    if live_enabled:
        if llm is None:
            raise RuntimeError("Live search cần LLM cho bounded P5/P6; chọn provider trước khi bật.")
        mode = os.getenv("GLADIATORS_LIVE_SEARCH_MODE", "cache_only")
        provider_adapter = TavilyProvider() if mode in {"record", "live"} else None
        cache = ExternalCache(os.getenv("GLADIATORS_EXTERNAL_CACHE_DIR", "data/external_cache"))
        quota = QuotaGuard(
            os.getenv("GLADIATORS_EXTERNAL_QUOTA_PATH", "artifacts/external_quota.json"),
            int(os.getenv("GLADIATORS_LIVE_SEARCH_DAILY_LIMIT", "150")),
        )
        external_pipeline = ExternalContextPipeline(
            LiveSearchPlanner(llm), SearchExecutor(provider_adapter, cache, quota),
            WebExtractor(llm), mode=mode, license=live_license,
        )
    return AgentRuntime(
        llm_client=llm, use_llm_parser=llm is not None,
        use_llm_generation=llm is not None,
        external_pipeline=external_pipeline, enable_live_search=live_enabled,
    )
