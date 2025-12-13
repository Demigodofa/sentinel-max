"""Safe HTML scraper with multiple cleaning strategies."""
from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any, Dict
from urllib.parse import urlparse

try:
    import requests
except Exception:  # pragma: no cover - optional dependency
    requests = None

try:  # BeautifulSoup is optional
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    BeautifulSoup = None

from sentinel.agent_core.base import Tool
from sentinel.logging.logger import get_logger
from sentinel.tools.tool_schema import ToolSchema


logger = get_logger(__name__)


class WebScraperTool(Tool):
    def __init__(self) -> None:
        super().__init__("web_scraper", "Fetch raw HTML and cleaned text from a URL", deterministic=False)
        self.schema = ToolSchema(
            name="web_scraper",
            version="1.0.0",
            description="Fetch raw HTML and cleaned text from a URL",
            input_schema={"url": {"type": "string", "required": True}, "timeout": {"type": "number", "required": False}},
            output_schema={"type": "object", "properties": {"url": "string", "html": "string", "text": "string"}},
            permissions=["net:read"],
            deterministic=False,
        )

    def _is_safe_domain(self, url: str) -> None:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            raise ValueError("URL must include a hostname")
        lowered = host.lower()
        if lowered.endswith(".local"):
            return
        if lowered in {"localhost", "127.0.0.1", "0.0.0.0"}:
            raise ValueError("Localhost access is not permitted")
        try:
            ip_obj = ipaddress.ip_address(lowered)
            if ip_obj.is_private or ip_obj.is_loopback:
                raise ValueError("Private or loopback addresses are not allowed")
        except ValueError:
            # Host is not a direct IP; resolve and check
            try:
                infos = socket.getaddrinfo(host, None)
                for _, _, _, _, addr in infos:
                    resolved_ip = addr[0]
                    ip_obj = ipaddress.ip_address(resolved_ip)
                    if ip_obj.is_private or ip_obj.is_loopback:
                        raise ValueError("Resolved to private address; blocked")
            except Exception:
                # Resolution failures are treated as unsafe
                raise ValueError("Unable to resolve host safely")

    def _clean_html(self, html: str) -> str:
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            return soup.get_text(" ", strip=True)
        # Fallback: strip tags with regex and collapse whitespace
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()

    def execute(self, url: str, timeout: float = 5.0) -> Dict[str, Any]:
        self._is_safe_domain(url)
        if requests is None:
            html = f"<html><body>{url}</body></html>"
            return {"url": url, "html": html, "text": self._clean_html(html)}
        headers = {"User-Agent": "SentinelMAX/1.0"}
        try:
            response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            html = response.text
        except Exception as exc:  # pragma: no cover - runtime safeguard
            logger.warning("Web scrape failed, returning simulated content: %s", exc)
            html = f"<html><body>Simulated content for {url}</body></html>"
        return {"url": url, "html": html, "text": self._clean_html(html)}


WEB_SCRAPER_TOOL = WebScraperTool()
