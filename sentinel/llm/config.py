from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for the OpenAI LLM backend."""

    backend: str
    base_url: str
    api_key: str | None
    model: str
    worker_model: str | None = None
    temperature: float = 0.2
    timeout_s: float = 60.0
    store: bool = False


def load_llm_config() -> LLMConfig:
    """Load LLM configuration from environment variables.

    Env vars (new canonical names):
      SENTINEL_LLM_BACKEND (default: openai)
      SENTINEL_LLM_BASE_URL (default: https://api.openai.com/v1)
      SENTINEL_LLM_MODEL (default: gpt-4o)
      SENTINEL_LLM_WORKER_MODEL (optional cheaper model)
      SENTINEL_LLM_TIMEOUT_SECS (default: 60)
      SENTINEL_LLM_STORE (default: false)
      OPENAI_API_KEY (preferred key for OpenAI-compatible endpoints)

    Backwards-compatible fallbacks:
      SENTINEL_OPENAI_API_KEY, SENTINEL_OPENAI_BASE_URL, SENTINEL_OPENAI_MODEL,
      SENTINEL_OPENAI_TIMEOUT_SECS, SENTINEL_OPENAI_STORE
    """

    backend = (os.getenv("SENTINEL_LLM_BACKEND") or "openai").strip().lower()
    base_url = (
        os.getenv("SENTINEL_LLM_BASE_URL")
        or os.getenv("SENTINEL_OPENAI_BASE_URL")
        or ("http://localhost:11434/v1" if backend == "ollama" else "https://api.openai.com/v1")
    ).rstrip("/")
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("SENTINEL_OPENAI_API_KEY")
    model = (
        os.getenv("SENTINEL_LLM_MODEL")
        or os.getenv("SENTINEL_OPENAI_MODEL")
        or "gpt-4o"
    ).strip()
    worker_model = (os.getenv("SENTINEL_LLM_WORKER_MODEL") or "").strip() or None
    timeout_s = float(os.getenv("SENTINEL_LLM_TIMEOUT_SECS") or os.getenv("SENTINEL_OPENAI_TIMEOUT_SECS") or 60)
    store = (
        os.getenv("SENTINEL_LLM_STORE")
        or os.getenv("SENTINEL_OPENAI_STORE")
        or "false"
    ).strip().lower() == "true"

    return LLMConfig(
        backend=backend,
        base_url=base_url,
        api_key=api_key,
        model=model,
        worker_model=worker_model,
        timeout_s=timeout_s,
        store=store,
    )
