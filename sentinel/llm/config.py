from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for the OpenAI LLM backend."""

    base_url: str
    api_key: str | None
    model: str
    temperature: float = 0.2
    timeout_s: float = 60.0
    store: bool = False


def load_llm_config() -> LLMConfig:
    """Load OpenAI configuration from environment variables.

    Env vars:
      SENTINEL_OPENAI_API_KEY (required)
      SENTINEL_OPENAI_BASE_URL (default: https://api.openai.com/v1)
      SENTINEL_OPENAI_MODEL (default: gpt-4o)
      SENTINEL_OPENAI_TIMEOUT_SECS (default: 60)
      SENTINEL_OPENAI_STORE (default: false)  # if responses storage is supported
    """

    base_url = (os.getenv("SENTINEL_OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    api_key = os.getenv("SENTINEL_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = (os.getenv("SENTINEL_OPENAI_MODEL") or "gpt-4o").strip()
    timeout_s = float(os.getenv("SENTINEL_OPENAI_TIMEOUT_SECS") or 60)
    store = (os.getenv("SENTINEL_OPENAI_STORE") or "false").strip().lower() == "true"

    return LLMConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_s=timeout_s,
        store=store,
    )
