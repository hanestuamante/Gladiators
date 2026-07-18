from __future__ import annotations

import os

from dotenv import load_dotenv

from gladiators.agent.llm import GeminiLLMClient, GroqLLMClient, HuggingFaceLLMClient
from gladiators.agent.workflow import AgentRuntime


def create_runtime(provider: str | None = None) -> AgentRuntime:
    load_dotenv()
    selected = provider or os.getenv("GLADIATORS_LLM_PROVIDER", "offline")
    if selected not in {"offline", "gemini", "huggingface", "groq"}:
        raise ValueError(f"Provider không hỗ trợ: {selected}")
    llm = GeminiLLMClient() if selected == "gemini" else HuggingFaceLLMClient() if selected == "huggingface" else GroqLLMClient() if selected == "groq" else None
    return AgentRuntime(llm_client=llm, use_llm_parser=llm is not None, use_llm_generation=llm is not None)
