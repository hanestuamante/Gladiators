from __future__ import annotations

import os

from dotenv import load_dotenv

from gladiators.agent.cassette import CassetteLLMClient, LLMCassette
from gladiators.agent.llm import (
    DeepSeekLLMClient,
    FallbackLLMClient,
    GeminiLLMClient,
    GroqLLMClient,
    HuggingFaceLLMClient,
)
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


SEARCH_CASSETTE_DIR = "artifacts/search_cassettes"


def _search_provider(live):
    """Pick the search provider the configured mode actually implies (§16 P12).

    ``record`` wraps the live provider so every call is saved as a cassette;
    ``replay`` serves cassettes only and raises on a miss. Before this, the
    record/replay layer existed and nothing selected it -- the same
    dark-component problem the shadow wiring fixed for routing, and just as
    invisible: ``mode=record`` looked configured and recorded nothing.
    """
    from gladiators.external.record_replay import (
        CassetteStore,
        RecordingSearchProvider,
        ReplaySearchProvider,
    )

    mode = getattr(live, "mode", "cache_only")
    store = CassetteStore(getattr(live, "cassette_dir", SEARCH_CASSETTE_DIR))
    if mode == "replay":
        # No live provider is constructed at all, so a miss cannot reach out.
        return ReplaySearchProvider(store)
    if mode == "record":
        return RecordingSearchProvider(TavilyProvider(), store)
    if mode == "live":
        return TavilyProvider()
    return None


def create_runtime(provider: str | None = None) -> AgentRuntime:
    load_dotenv()
    selected = provider or os.getenv("GLADIATORS_LLM_PROVIDER", "offline")
    if selected not in {"offline", "gemini", "huggingface", "groq", "deepseek"}:
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
            "deepseek": os.getenv("DEEPSEEK_MODEL", ""),
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
                else DeepSeekLLMClient()
                if selected == "deepseek"
                else GroqLLMClient()
            )
            # DeepSeek primary, Groq as spare: a transport failure on the fast
            # provider degrades to the slower one instead of failing the request.
            if selected == "deepseek" and os.getenv("GROQ_API_KEY"):
                try:
                    delegate = FallbackLLMClient(delegate, GroqLLMClient())
                except RuntimeError:
                    pass
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
        provider_adapter = _search_provider(live)
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
