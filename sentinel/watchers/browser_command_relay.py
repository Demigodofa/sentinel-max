"""Browser watcher that relays ChatGPT commands into the Sentinel GUI."""
from __future__ import annotations

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
    # What to open / watch
    chatgpt_url: str = "https://chat.openai.com/"
    assistant_selector: str = 'div[data-message-author-role="assistant"]'

    # Command markers
    start_marker: str = "<START>"
    stop_marker: str = "<STOP>"

    # Polling
    poll_interval_seconds: float = 1.5

    # Chrome behavior
    headless: bool = False

    # NEW: profile + attach support
    profile_dir: Optional[str] = None          # passed as --user-data-dir when we launch Chrome
    chrome_binary: Optional[str] = None        # explicit chrome.exe path
    attach_debug_port: Optional[int] = None    # attach to an existing Chrome with --remote-debugging-port=PORT


def create_chrome_driver(*, config: BrowserRelayConfig) -> webdriver.Chrome:
    """
    Create a Chrome WebDriver session.

    Two modes:

    1) ATTACH MODE (recommended for "Sign in with Google" / automation-block issues)
       - You start Chrome yourself with:
           --remote-debugging-port=9222 --user-data-dir=...
       - Then set attach_debug_port=9222
       - Selenium attaches via debuggerAddress and does NOT launch a fresh automated instance.

    2) LAUNCH MODE
       - Selenium launches Chrome directly.
       - You can specify profile_dir to persist ChatGPT login.
    """
    options = Options()

    if config.chrome_binary:
        options.binary_location = config.chrome_binary

    if config.attach_debug_port:
        # Attach to an already-running Chrome instance (best for avoiding automation login blocks)
        if config.headless:
            raise ValueError("headless + attach_debug_port is not supported (attach requires visible Chrome).")
        options.add_experimental_option("debuggerAddress", f"127.0.0.1:{config.attach_debug_port}")
        # Selenium Manager (Selenium 4.6+) will auto-provide the correct driver.
        return webdriver.Chrome(options=options)

    # Normal launch mode
    if config.headless:
        options.add_argument("--headless=new")

    # If you provide a profile dir, Chrome will persist login/cookies there
    if config.profile_dir:
        options.add_argument(f'--user-data-dir={config.profile_dir}')

    # Stability flags (mostly harmless on Windows; helps avoid weird startup crashes)
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-popup-blocking")

    # If you ever see CORS / origin mismatch driver issues with new Chrome/driver combos:
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
        self.logger = logger or logging.getLogger(__name__)
        self.driver_factory = driver_factory or (lambda: create_chrome_driver(config=self.config))

        self._stop_event = threading.Event()
        self._seen_signatures: set[str] = set()
        self._driver: webdriver.Chrome | None = None

        self._pattern = re.compile(
            re.escape(self.config.start_marker) + r"(.*?)" + re.escape(self.config.stop_marker),
            re.DOTALL,
        )

    def run(self) -> None:
        try:
            self._driver = self.driver_factory()
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Failed to create Chrome driver for browser relay: %s", exc)
            self.logger.error(
                "If using attach mode, start Chrome with --remote-debugging-port and pass --attach-debug-port."
            )
            return

        self.logger.info(
            "ChatGPT relay starting: url=%s selector=%s poll=%.2fs headless=%s attach=%s profile=%s",
            self.config.chatgpt_url,
            self.config.assistant_selector,
            self.config.poll_interval_seconds,
            self.config.headless,
            self.config.attach_debug_port,
            self.config.profile_dir,
        )

        # In attach mode, the user may already be on the right tab. Still safe to navigate.
        try:
            self._driver.get(self.config.chatgpt_url)
        except WebDriverException as exc:
            self.logger.warning("Navigation to ChatGPT URL failed (continuing): %s", exc)

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
        if not self._driver:
            return
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
        except WebDriverException as exc:
            self.logger.debug("find_elements failed: %s", exc)
            return

        commands = self._extract_commands(elements)
        for command in commands:
            sig = self._signature(command)
            if sig in self._seen_signatures:
                continue
            self._seen_signatures.add(sig)
            self.logger.info("Forwarding ChatGPT command: %s", command.strip())
            self.command_queue.put(command.strip())

    def _extract_commands(self, elements: Iterable) -> List[str]:
        commands: List[str] = []
        for element in elements:
            try:
                text = (element.text or "").strip()
            except StaleElementReferenceException:
                continue
            if not text:
                continue
            for match in self._pattern.findall(text):
                cleaned = match.strip()
                if cleaned:
                    commands.append(cleaned)
        return commands

    def _signature(self, command: str) -> str:
        # Python's hash() is salted per-process; that's fine because we only dedupe within a single run.
        return str(hash(command))
