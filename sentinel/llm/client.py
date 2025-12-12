from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

from sentinel.logging.logger import get_logger
from sentinel.llm.config import LLMConfig, load_llm_config
from sentinel.tools.registry import DEFAULT_TOOL_REGISTRY, ToolRegistry

logger = get_logger(__name__)


@dataclass(frozen=True)
class ChatMessage:
    role: str  # system|user|assistant
    content: str


class LLMClient:
    """
    Minimal OpenAI-chat-compatible client. Works with:
      - Ollama OpenAI-compatible endpoint (default http://localhost:11434/v1)
      - OpenAI API (https://api.openai.com/v1)
    """

    def __init__(self, cfg: LLMConfig | None = None) -> None:
        self.cfg = cfg or load_llm_config()

    @property
    def enabled(self) -> bool:
        if self.cfg.backend == "none":
            return False
        if self.cfg.backend == "openai" and not self.cfg.api_key:
            return False
        return True

    def chat(self, messages: Iterable[ChatMessage], max_tokens: int = 512) -> str | None:
        if not self.enabled:
            message = (
                "LLM backend is disabled or missing credentials. "
                f"backend={self.cfg.backend}, model={self.cfg.model}"
            )
            logger.warning(message)
            return message

        url = f"{self.cfg.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.cfg.temperature,
            "max_tokens": max_tokens,
        }

        headers = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.cfg.timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            return (data.get("choices") or [{}])[0].get("message", {}).get("content")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
            snippet = body[:300]
            message = (
                "LLM request failed. "
                f"backend={self.cfg.backend}, base_url={self.cfg.base_url}, model={self.cfg.model}, "
                f"status={exc.code}, response={snippet}"
            )
            logger.error(message)
            return message
        except Exception as exc:
            message = (
                "LLM request failed. "
                f"backend={self.cfg.backend}, base_url={self.cfg.base_url}, model={self.cfg.model}, "
                f"error={exc}"
            )
            logger.error(message)
            return message


 codex/fix-task-routing-for-llm-tools
DEFAULT_SYSTEM_PROMPT = (
    "You are Sentinel MAX, a practical engineering assistant.\n"
    "Be direct, competent, and helpful. Ask a single clarifying question only if absolutely required.\n"
    "If the user asks you to perform actions requiring tools, propose a short plan and ask for execution approval.\n"
    "You can leverage tools such as web_search, internet_extract, fs_read, fs_write, fs_list, fs_delete, sandbox_exec, "
    "browser_agent, code_analyzer, and microservice_builder. When planning, suggest concrete steps that use these "
    "capabilities to gather information or save outputs.\n"

DEFAULT_SYSTEM_PROMPT_BASE = (
    "You are Sentinel MAX. You have tool access via a sandboxed ToolRegistry:\n"
    "- web_search: search the internet\n"
    "- internet_extract: fetch + extract content\n"
    "- fs_read/fs_write/fs_list: read/write project files in allowed roots\n"
    "- sandbox_exec: run safe commands in the sandbox\n"
    "GUI, CLI, and API inputs share the same controller pipeline.\n"
    "When the user asks to do something, propose a short plan first. Execute only after explicit approval (\"run\", \"y\", \"/run\") unless /auto is enabled (also accepts the word \"auto\").\n"
    "Never claim you lack internet/tools if web_search or internet_extract exist. Use tools to stay factual and cite sources when possible.\n"
 main
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

