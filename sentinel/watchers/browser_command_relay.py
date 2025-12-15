"""Browser watcher that relays ChatGPT commands into the Sentinel GUI."""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from dataclasses import dataclass
from queue import Queue
from typing import Callable, Iterable, List, Optional

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


@dataclass(slots=True)
class BrowserRelayConfig:
    chatgpt_url: str = "https://chat.openai.com/"
    assistant_selector: str = 'div[data-message-author-role="assistant"]'
    start_marker: str = "<START>"
    stop_marker: str = "<STOP>"
    poll_interval_seconds: float = 1.5
    headless: bool = False

    # NEW:
    profile_dir: Optional[str] = None          # Chrome --user-data-dir
    chrome_binary: Optional[str] = None        # Explicit chrome.exe
    attach_debug_port: Optional[int] = None    # Attach to existing Chrome debugging port


def create_chrome_driver(config: BrowserRelayConfig) -> webdriver.Chrome:
    """
    Create a Chrome WebDriver.

    If attach_debug_port is set, we ATTACH to an existing Chrome instance started with:
      --remote-debugging-port=PORT

    Otherwise, we launch a new Chrome using profile_dir if provided.

    Note: Selenium 4+ can use Selenium Manager to obtain a compatible driver automatically,
    so chromedriver does not have to be preinstalled on PATH in many setups.
    """
    options = Options()

    if config.chrome_binary:
        options.binary_location = config.chrome_binary

    if config.attach_debug_port:
        # Attach mode: do NOT pass user-data-dir here. Chrome is already running.
        options.add_experimental_option(
            "debuggerAddress", f"127.0.0.1:{config.attach_debug_port}"
        )
    else:
        # Launch mode:
        if config.profile_dir:
            options.add_argument(f'--user-data-dir={config.profile_dir}')

        if config.headless:
            options.add_argument("--headless=new")

        # Hardening flags that reduce startup weirdness on Windows
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--remote-allow-origins=*")

    return webdriver.Chrome(options=options)


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
        self.driver_factory = driver_factory or (lambda: create_chrome_driver(self.config))
        self.logger = logger or logging.getLogger(__name__)
        self._stop_event = threading.Event()
        self._seen_signatures: set[str] = set()
        self._driver: webdriver.Chrome | None = None

    def run(self) -> None:
        try:
            self._driver = self.driver_factory()
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Failed to create Chrome driver for browser relay: %s", exc)
            self.logger.error(
                "If you're using attach mode, confirm Chrome is running with --remote-debugging-port "
                "and the port matches. If launching, confirm Chrome can start with the given profile_dir."
            )
            return

        mode = "attach" if self.config.attach_debug_port else "launch"
        self.logger.info(
            "Starting ChatGPT browser relay (%s): url=%s selector=%s poll=%.2fs headless=%s profile_dir=%s port=%s",
            mode,
            self.config.chatgpt_url,
            self.config.assistant_selector,
            self.config.poll_interval_seconds,
            self.config.headless,
            self.config.profile_dir,
            self.config.attach_debug_port,
        )

        if not self._ensure_chatgpt_tab():
            self._shutdown_driver()
            return

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

        try:
            elements = self._driver.find_elements(By.CSS_SELECTOR, self.config.assistant_selector)
        except WebDriverException:
            return

        commands = self._extract_commands(elements)
        for command in commands:
            signature = self._signature(command)
            if signature in self._seen_signatures:
                continue
            self._seen_signatures.add(signature)
            self._forward_command(command)

    def _extract_commands(self, elements: Iterable) -> List[str]:
        commands: List[str] = []
        pattern = re.compile(
            re.escape(self.config.start_marker) + r"(.*?)" + re.escape(self.config.stop_marker),
            re.DOTALL,
        )

        for element in elements:
            try:
                text = (element.text or "").strip()
            except StaleElementReferenceException:
                continue

            if not text:
                continue

            for match in pattern.findall(text):
                cleaned = match.strip()
                if cleaned:
                    commands.append(cleaned)

        return commands

    def _signature(self, command: str) -> str:
        return hashlib.sha256(command.encode("utf-8")).hexdigest()

    def _ensure_chatgpt_tab(self) -> bool:
        if not self._driver:
            return False

        try:
            self._driver.get(self.config.chatgpt_url)
        except WebDriverException as exc:
            self.logger.error("Navigation to chatgpt_url failed: %s", exc)
            return False

        try:
            self._driver.find_element(By.TAG_NAME, "body")
            self.logger.info("ChatGPT tab ready; watching for wrapped commands.")
            return True
        except WebDriverException as exc:
            self.logger.error("ChatGPT page did not finish loading: %s", exc)
            return False

    def _forward_command(self, command: str) -> None:
        cleaned = command.strip()
        if not cleaned:
            return
        self.logger.info("Forwarding ChatGPT command into GUI: %s", cleaned)
        self.command_queue.put(cleaned)
