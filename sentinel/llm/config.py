from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    backend: str  # "ollama" | "openai" | "none"
    base_url: str
    api_key: str | None
    model: str
    temperature: float = 0.2
    timeout_s: float = 45.0


def load_llm_config() -> LLMConfig:
    """
    Env vars:
      SENTINEL_LLM_BACKEND=ollama|openai|none
      SENTINEL_LLM_BASE_URL (default: ollama -> http://localhost:11434/v1)
      SENTINEL_LLM_API_KEY  (optional for ollama, required for openai)
      SENTINEL_LLM_MODEL    (default: qwen2.5:7b)
    """
    backend = (os.getenv("SENTINEL_LLM_BACKEND") or "none").strip().lower()
    model = (os.getenv("SENTINEL_LLM_MODEL") or "qwen2.5:7b").strip()

    if backend == "ollama":
        base_url = (os.getenv("SENTINEL_LLM_BASE_URL") or "http://localhost:11434/v1").rstrip("/")
        api_key = os.getenv("SENTINEL_LLM_API_KEY") or "ollama"
        return LLMConfig(backend=backend, base_url=base_url, api_key=api_key, model=model)

    if backend == "openai":
        base_url = (os.getenv("SENTINEL_LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        api_key = os.getenv("SENTINEL_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            # Keep it non-fatal; the app will fall back to deterministic dialog.
            api_key = None
        return LLMConfig(backend=backend, base_url=base_url, api_key=api_key, model=model)

    return LLMConfig(backend="none", base_url="", api_key=None, model=model)
