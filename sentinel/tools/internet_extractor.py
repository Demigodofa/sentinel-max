"""Internet extractor that searches, scrapes, cleans, and summarizes content."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from sentinel.agent_core.base import Tool
from sentinel.logging.logger import get_logger
from sentinel.memory.vector_memory import VectorMemory
from sentinel.tools.web_scraper import WebScraperTool
from sentinel.tools.tool_schema import ToolSchema

logger = get_logger(__name__)


def _summarize_text(text: str, max_sentences: int = 3) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    trimmed = [s.strip() for s in sentences if s.strip()]
    return " ".join(trimmed[:max_sentences])


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class InternetExtractorTool(Tool):
    def __init__(self, vector_memory: Optional[VectorMemory] = None) -> None:
        super().__init__("internet_extract", "Search, scrape, clean, and summarize web content", deterministic=True)
        self.scraper = WebScraperTool()
        self.vector_memory = vector_memory or VectorMemory()
        self.schema = ToolSchema(
            name="internet_extract",
            version="1.0.0",
            description="Search, scrape, clean, and summarize web content",
            input_schema={"url": {"type": "string", "required": True}, "store": {"type": "boolean", "required": False}, "namespace": {"type": "string", "required": False}},
            output_schema={"type": "object", "properties": {"url": "string", "clean_text": "string", "summary": "string"}},
            permissions=["net:read", "fs:read-limited"],
            deterministic=True,
        )

    def execute(self, url: str, store: bool = True, namespace: str = "internet") -> Dict[str, Any]:
        logger.info("Extracting content from %s", url)
        scrape_result = self.scraper.execute(url)
        clean_text = _clean_text(scrape_result["text"])
        summary = _summarize_text(clean_text)
        if store:
            try:
                self.vector_memory.add(
                    clean_text,
                    metadata={"url": url, "summary": summary},
                    namespace=namespace,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Vector memory store failed: %s", exc)
        return {
            "url": url,
            "raw_html": scrape_result.get("html", ""),
            "clean_text": clean_text,
            "summary": summary,
        }


INTERNET_EXTRACTOR_TOOL = InternetExtractorTool()
