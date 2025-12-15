"""Browser watcher that relays ChatGPT commands into the Sentinel GUI."""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from queue import Queue
from typing import Callable, Iterable, List

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


def create_chrome_driver(*, headless: bool = False) -> webdriver.Chrome:
    """Return a configured Chrome driver.

    The caller is responsible for ensuring chromedriver is on PATH. Headless mode
    is available for local testing, but the relay assumes an interactive user is
    already signed in to ChatGPT in the launched browser profile.
    """

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    return webdriver.Chrome(options=options)


@dataclass(slots=True)
class BrowserRelayConfig:
    chatgpt_url: str = "https://chat.openai.com/"
    assistant_selector: str = 'div[data-message-author-role="assistant"]'
    start_marker: str = "<START>"
    stop_marker: str = "<STOP>"
    poll_interval_seconds: float = 1.5
    headless: bool = False


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
            lambda: create_chrome_driver(headless=self.config.headless)
        )
        self.logger = logger or logging.getLogger(__name__)
        self._stop_event = threading.Event()
        self._seen_signatures: set[str] = set()
        self._driver: webdriver.Chrome | None = None

    def run(self) -> None:
        try:
            self._driver = self.driver_factory()
        except Exception as exc:  # noqa: BLE001
            self.logger.error(
                "Failed to create Chrome driver for browser relay: %s", exc
            )
            self.logger.error(
                "Ensure chromedriver is installed and discoverable on PATH before enabling the ChatGPT relay."
            )
            return

        self.logger.info(
            "Starting ChatGPT browser relay: url=%s selector=%s poll=%.2fs headless=%s",
            self.config.chatgpt_url,
            self.config.assistant_selector,
            self.config.poll_interval_seconds,
            self.config.headless,
        )

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
            text = (element.text or "").strip()
            if not text:
                continue
            for match in pattern.findall(text):
                cleaned = match.strip()
                if cleaned:
                    commands.append(cleaned)
        return commands

    def _signature(self, command: str) -> str:
        return str(hash(command))
