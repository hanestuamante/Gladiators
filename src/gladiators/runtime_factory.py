from __future__ import annotations

import os

from dotenv import load_dotenv

from gladiators.agent.cassette import CassetteLLMClient, LLMCassette
from gladiators.agent.llm import GeminiLLMClient, GroqLLMClient, HuggingFaceLLMClient
from gladiators.agent.workflow import AgentRuntime
from gladiators.data.repository import ArtifactRepository
from gladiators.external.cache import ExternalCache, QuotaGuard
from gladiators.external.pipeline import ExternalContextPipeline
from gladiators.external.search_executor import SearchExecutor
from gladiators.external.search_planner import LiveSearchPlanner
from gladiators.external.search_provider import TavilyProvider
from gladiators.external.settings import load_external_settings
from gladiators.external.registry import build_source_registry
from gladiators.external.web_extract import WebExtractor


def create_runtime(provider: str | None = None) -> AgentRuntime:
    load_dotenv()
    selected = provider or os.getenv("GLADIATORS_LLM_PROVIDER", "offline")
    if selected not in {"offline", "gemini", "huggingface", "groq"}:
        raise ValueError(f"Provider không hỗ trợ: {selected}")
    external_settings = load_external_settings()
    live = external_settings.live_search
    live_enabled = live.enabled
    source_registry = build_source_registry(live)
    cassette = LLMCassette(
        root=os.getenv("GLADIATORS_CASSETTE_DIR", "tests/fixtures/cassettes"),
    )
    llm = None
    if selected != "offline":
        defaults = {
            "gemini": os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
            "huggingface": os.getenv("HF_MODEL", "Qwen/Qwen3-32B"),
            "groq": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        }
        if cassette.mode == "replay":
            llm = CassetteLLMClient(
                None,
                provider=selected,
                model=defaults[selected],
                prompt_version=os.getenv("GLADIATORS_PROMPT_VERSION", "v1.1.0"),
                dataset_version=ArtifactRepository().dataset_version,
                cassette=cassette,
            )
        else:
            delegate = (
                GeminiLLMClient()
                if selected == "gemini"
                else HuggingFaceLLMClient()
                if selected == "huggingface"
                else GroqLLMClient()
            )
            llm = (
                CassetteLLMClient(
                    delegate,
                    dataset_version=ArtifactRepository().dataset_version,
                    cassette=cassette,
                )
                if cassette.mode == "record"
                else delegate
            )
    external_pipeline = None
    if live_enabled:
        if llm is None:
            raise RuntimeError("Live search cần LLM cho bounded P5/P6; chọn provider trước khi bật.")
        source = source_registry.require_enabled("live_web_search")
        provider_adapter = TavilyProvider() if live.mode in {"record", "live"} else None
        cache = ExternalCache(live.cache_dir)
        quota = QuotaGuard(
            live.quota_path, live.daily_query_limit,
        )
        external_pipeline = ExternalContextPipeline(
            LiveSearchPlanner(llm, max_queries=live.max_queries_per_request), SearchExecutor(
                provider_adapter, cache, quota, max_results=live.max_results_per_query,
                timeout_s=live.timeout_s, total_budget_s=live.total_budget_s,
                cache_provider_id=live.provider,
            ),
            WebExtractor(llm), mode=live.mode, license=source.license,
        )
    return AgentRuntime(
        llm_client=llm, use_llm_parser=llm is not None,
        use_llm_generation=llm is not None,
        external_pipeline=external_pipeline, enable_live_search=live_enabled,
    )
