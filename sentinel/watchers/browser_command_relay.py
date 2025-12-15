"""Browser watcher that relays ChatGPT commands into the Sentinel GUI."""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Callable, Iterable, List, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


def _norm_path(p: str | Path | None) -> str | None:
    if not p:
        return None
    return str(Path(p).expanduser().resolve())


def create_chrome_driver(
    *,
    headless: bool = False,
    profile_dir: str | Path | None = None,
    chrome_binary: str | None = None,
    attach_debug_port: int | None = None,
) -> webdriver.Chrome:
    """
    Create a Chrome WebDriver.

    - If attach_debug_port is set, Selenium attaches to an already-running Chrome started with:
        chrome.exe --remote-debugging-port=9222 --user-data-dir=...
    - Otherwise Selenium launches Chrome itself.

    NOTE: chromedriver does NOT need to be on PATH if you're on Selenium 4.6+ (Selenium Manager),
    but having it pinned can remove ambiguity.
    """
    options = Options()

    if chrome_binary:
        options.binary_location = chrome_binary

    if headless and not attach_debug_port:
        options.add_argument("--headless=new")

    # Stability flags (harmless; often reduce startup flakiness)
    options.add_argument("--disable-gpu")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-dev-shm-usage")

    prof = _norm_path(profile_dir)
    if attach_debug_port:
        # Attach mode: you launch Chrome manually; webdriver connects to it.
        options.add_experimental_option("debuggerAddress", f"127.0.0.1:{attach_debug_port}")
        return webdriver.Chrome(options=options)

    # Launch mode: webdriver launches Chrome using a dedicated profile dir.
    if prof:
        Path(prof).mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={prof}")

    return webdriver.Chrome(options=options)


@dataclass(slots=True)
class BrowserRelayConfig:
    chatgpt_url: str = "https://chat.openai.com/"
    assistant_selector: str = 'div[data-message-author-role="assistant"]'
    start_marker: str = "<START>"
    stop_marker: str = "<STOP>"
    poll_interval_seconds: float = 1.5
    headless: bool = False
    profile_dir: Optional[str] = None
    chrome_binary: Optional[str] = None
    attach_debug_port: Optional[int] = None


class ChatGPTBrowserRelay:
    """Poll a ChatGPT browser tab and forward wrapped commands to a queue."""

    def __init__(
        self,
        command_queue: Queue[str],
        *,
        config: BrowserRelayConfig | None = None,
        driver_factory: Callable[[], webdriver.Chrome] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.command_queue = command_queue
        self.config = config or BrowserRelayConfig()
        self.driver_factory = driver_factory or (
            lambda: create_chrome_driver(
                headless=self.config.headless,
                profile_dir=self.config.profile_dir,
                chrome_binary=self.config.chrome_binary,
                attach_debug_port=self.config.attach_debug_port,
            )
        )
        self.logger = logger or logging.getLogger(__name__)
        self._stop_event = threading.Event()
        self._seen_signatures: set[str] = set()
        self._driver: webdriver.Chrome | None = None

    def run(self) -> None:
        try:
            self._driver = self.driver_factory()
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Failed to create Chrome driver for browser relay: %s", exc)
            self.logger.error("If you see DevToolsActivePort/session-not-created, use a fresh profile dir or attach mode.")
            return

        self.logger.info(
            "Relay starting: url=%s selector=%s poll=%.2fs headless=%s profile_dir=%s attach_port=%s",
            self.config.chatgpt_url,
            self.config.assistant_selector,
            self.config.poll_interval_seconds,
            self.config.headless,
            self.config.profile_dir,
            self.config.attach_debug_port,
        )

        # Only navigate if we're not attaching to an already-open tab.
        if not self.config.attach_debug_port:
            self._driver.get(self.config.chatgpt_url)

        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception as exc:  # noqa: BLE001
                self.logger.exception("Relay polling failed: %s", exc)
            finally:
                self._stop_event.wait(self.config.poll_interval_seconds)

        self._shutdown_driver()

    def stop(self) -> None:
        self._stop_event.set()

    def _shutdown_driver(self) -> None:
        if self._driver:
            try:
                self._driver.quit()
            except Exception:  # noqa: BLE001
                self.logger.debug("Driver shutdown raised, continuing.")
            finally:
                self._driver = None

    def _poll_once(self) -> None:
        if not self._driver:
            return

        elements = self._driver.find_elements(By.CSS_SELECTOR, self.config.assistant_selector)
        commands = self._extract_commands(elements)

        for command in commands:
            signature = self._signature(command)
            if signature in self._seen_signatures:
                continue
            self._seen_signatures.add(signature)
            self.logger.info("Forwarding ChatGPT command: %s", command.strip())
            self.command_queue.put(command.strip())

    def _extract_commands(self, elements: Iterable) -> List[str]:
        commands: List[str] = []
        pattern = re.compile(
            re.escape(self.config.start_marker) + r"(.*?)" + re.escape(self.config.stop_marker),
            re.DOTALL,
        )
        for element in elements:
            text = (getattr(element, "text", "") or "").strip()
            if not text:
                continue
            for match in pattern.findall(text):
                cleaned = match.strip()
                if cleaned:
                    commands.append(cleaned)
        return commands

    def _signature(self, command: str) -> str:
        return hashlib.sha256(command.encode("utf-8", errors="ignore")).hexdigest()
