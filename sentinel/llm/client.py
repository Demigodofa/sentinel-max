from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Tuple

from sentinel.logging.logger import get_logger
from sentinel.llm.config import LLMConfig, load_llm_config
from sentinel.tools.registry import DEFAULT_TOOL_REGISTRY, ToolRegistry

logger = get_logger(__name__)


@dataclass(frozen=True)
class ChatMessage:
    role: str  # system|user|assistant
    content: str


class LLMClientError(Exception):
    pass


class LLMClient:
    """OpenAI Chat Completions client with retries and health checks."""

    def __init__(self, cfg: LLMConfig | None = None) -> None:
        self.cfg = cfg or load_llm_config()
        self.backend = self.cfg.backend

    @property
    def enabled(self) -> bool:
        if self.backend == "openai":
            return bool(self.cfg.api_key)
        return True

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        return headers

    def _post_json(self, path: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str | None, float]:
        url = f"{self.cfg.base_url}{path}"
        headers = self._build_headers()
        data = json.dumps(payload).encode("utf-8")

        backoff = 1.0
        last_error: Exception | None = None

        for attempt in range(3):
            start = time.perf_counter()
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.cfg.timeout_s) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    latency_ms = (time.perf_counter() - start) * 1000
                    request_id = resp.headers.get("x-request-id") or resp.headers.get("x-openai-request-id")
                return json.loads(raw), request_id, latency_ms
            except urllib.error.HTTPError as exc:
                latency_ms = (time.perf_counter() - start) * 1000
                status = getattr(exc, "code", "unknown")
                body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
                snippet = body[:300]
                logger.error(
                    "LLM request failed backend=%s model=%s base_url=%s status=%s latency_ms=%.2f response=%s",
                    self.backend,
                    self.cfg.model,
                    self.cfg.base_url,
                    status,
                    latency_ms,
                    snippet,
                )
                last_error = exc
                if status in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                break
            except Exception as exc:  # pragma: no cover - defensive catch
                latency_ms = (time.perf_counter() - start) * 1000
                logger.error(
                    "LLM request failed backend=%s model=%s base_url=%s latency_ms=%.2f error=%s",
                    self.backend,
                    self.cfg.model,
                    self.cfg.base_url,
                    latency_ms,
                    exc,
                )
                last_error = exc
                break

        raise LLMClientError(str(last_error) if last_error else "Unknown LLM error")

    def chat(self, messages: Iterable[ChatMessage], max_tokens: int = 512) -> str | None:
        if not self.enabled:
            message = (
                "LLM backend is disabled or missing credentials. "
                f"backend={self.backend}, model={self.cfg.model}"
            )
            logger.error(message)
            return message

        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.cfg.temperature,
            "max_tokens": max_tokens,
        }

        try:
            data, request_id, latency_ms = self._post_json("/chat/completions", payload)
            logger.info(
                "LLM request succeeded backend=%s model=%s base_url=%s latency_ms=%.2f request_id=%s",
                self.backend,
                self.cfg.model,
                self.cfg.base_url,
                latency_ms,
                request_id,
            )
            return (data.get("choices") or [{}])[0].get("message", {}).get("content")
        except Exception as exc:
            message = (
                "LLM request failed. "
                f"backend={self.backend}, base_url={self.cfg.base_url}, model={self.cfg.model}, "
                f"error={exc}"
            )
            logger.error(message)
            return message

    def chat_with_tools(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
        *,
        max_tokens: int = 600,
        model_override: str | None = None,
    ) -> dict[str, object] | None:
        """Call the chat API with tool/function metadata."""

        if not self.enabled:
            logger.error("LLM backend disabled; cannot run tool calls")
            return None

        payload: dict[str, object] = {
            "model": model_override or self.cfg.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "max_tokens": max_tokens,
            "temperature": self.cfg.temperature,
        }

        try:
            data, request_id, latency_ms = self._post_json("/chat/completions", payload)
            logger.info(
                "LLM tool-call request backend=%s model=%s base_url=%s latency_ms=%.2f request_id=%s",
                self.backend,
                payload["model"],
                self.cfg.base_url,
                latency_ms,
                request_id,
            )
            return (data.get("choices") or [{}])[0].get("message") or {}
        except Exception as exc:
            logger.error(
                "Tool-call request failed backend=%s model=%s base_url=%s error=%s",
                self.backend,
                payload.get("model"),
                self.cfg.base_url,
                exc,
            )
            return None

    def health_check(self) -> Tuple[bool, str]:
        if not self.enabled:
            message = (
                "OpenAI API key missing. Set SENTINEL_OPENAI_API_KEY before starting Sentinel."
            )
            logger.error(
                "LLM health check failed backend=%s model=%s base_url=%s reason=missing_api_key",
                self.backend,
                self.cfg.model,
                self.cfg.base_url,
            )
            return False, message

        if self.backend != "openai":
            message = f"LLM backend '{self.backend}' configured; health check skipped"
            logger.info(
                "LLM health check skipped backend=%s model=%s base_url=%s",
                self.backend,
                self.cfg.model,
                self.cfg.base_url,
            )
            return True, message

        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": [{"role": "user", "content": "Respond with 'ok'"}],
            "max_tokens": 2,
            "temperature": 0,
        }

        try:
            data, request_id, latency_ms = self._post_json("/chat/completions", payload)
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
            ok = content.lower().startswith("ok")
            logger.info(
                "LLM health check backend=%s model=%s base_url=%s latency_ms=%.2f request_id=%s result=%s",
                self.backend,
                self.cfg.model,
                self.cfg.base_url,
                latency_ms,
                request_id,
                "ok" if ok else content,
            )
            if ok:
                return True, "LLM health check passed"
            return False, f"Unexpected health check response: {content or 'empty response'}"
        except Exception as exc:
            logger.error(
                "LLM health check failed backend=%s model=%s base_url=%s error=%s",
                self.backend,
                self.cfg.model,
                self.cfg.base_url,
                exc,
            )
            return False, f"LLM health check failed: {exc}"

    def supports_tool_calls(self) -> bool:
        """Return True when backend supports OpenAI-style tool calling."""

        return self.backend == "openai"


DEFAULT_SYSTEM_PROMPT = (
    "You are Sentinel MAX, a practical engineering assistant.\n"
    "Be direct, competent, and helpful. Ask a single clarifying question only if absolutely required.\n"
    "If the user asks you to perform actions requiring tools, propose a short plan and ask for execution approval.\n"
    "You can leverage tools such as web_search, internet_extract, fs_read, fs_write, fs_list, fs_delete, sandbox_exec, "
    "browser_agent, code_analyzer, and microservice_builder. When planning, suggest concrete steps that use these "
    "capabilities to gather information or save outputs.\n"
)

DEFAULT_SYSTEM_PROMPT_BASE = (
    "You are Sentinel MAX. You have tool access via a sandboxed ToolRegistry:\n"
    "- web_search: search the internet\n"
    "- internet_extract: fetch + extract content\n"
    "- fs_read/fs_write/fs_list: read/write project files in allowed roots\n"
    "- sandbox_exec: run safe commands in the sandbox\n"
    "GUI, CLI, and API inputs share the same controller pipeline.\n"
    "When the user asks you to do something, propose a short plan first. Execute only after explicit approval (\"run\", \"y\", \"/run\") unless /auto is enabled (also accepts the word \"auto\").\n"
    "Never claim you lack internet/tools if web_search or internet_extract exist. Use tools to stay factual and cite sources when possible.\n"
)


def _render_tool_list(tool_registry: ToolRegistry) -> str:
    descriptions = tool_registry.describe_tools()
    if not descriptions:
        return ""

    lines = ["\nRegistered tools available right now:"]
    for name, metadata in sorted(descriptions.items()):
        detail = metadata.get("description") or "no description provided"
        lines.append(f"- {name}: {detail}")
    return "\n".join(lines)


def build_system_prompt(tool_registry: ToolRegistry | None = None) -> str:
    registry = tool_registry or DEFAULT_TOOL_REGISTRY
    return DEFAULT_SYSTEM_PROMPT_BASE + _render_tool_list(registry)


DEFAULT_SYSTEM_PROMPT = build_system_prompt()
