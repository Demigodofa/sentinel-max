"""Browser watcher that relays ChatGPT commands into the Sentinel GUI.

Design goals:
- Portable: keep a dedicated Chrome profile on the external drive (e.g., F:\\sentinel-data\\chrome-profile)
- Robust: do NOT require chromedriver on PATH (use Selenium Manager when available)
- Debuggable: log what the relay is seeing (message counts, extracted commands)
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Callable, Iterable, List, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


def _default_profile_dir() -> str:
    """
    Pick a stable, portable profile dir.
    Priority:
      1) SENTINEL_RELAY_PROFILE_DIR env var
      2) F:\\sentinel-data\\chrome-profile (if F: exists)
      3) .\\sentinel-data\\chrome-profile (repo-local fallback)
    """
    env = os.environ.get("SENTINEL_RELAY_PROFILE_DIR", "").strip()
    if env:
        return env

    # Common case for you: external SSD mounted as F:
    if Path("F:/").exists():
        return r"F:\sentinel-data\chrome-profile"

    return str(Path.cwd() / "sentinel-data" / "chrome-profile")


def create_chrome_driver(
    *,
    headless: bool = False,
    profile_dir: Optional[str] = None,
    profile_name: Optional[str] = None,
    chrome_binary: Optional[str] = None,
) -> webdriver.Chrome:
    """Return a configured Chrome driver.

    Notes:
    - With modern Selenium (4.6+), Selenium Manager can auto-fetch the right driver.
      That means you typically do NOT need chromedriver on PATH.
    - We use a dedicated user-data-dir so you can log into ChatGPT once and persist the session.
    """
    options = Options()

    # Optional: specify Chrome binary explicitly (rarely needed on Windows)
    if chrome_binary:
        options.binary_location = chrome_binary

    # Headless mode is possible, but ChatGPT often needs an interactive login.
    if headless:
        options.add_argument("--headless=new")

    # Stability / compatibility flags
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--start-maximized")

    # Use a dedicated profile dir (portable)
    prof = profile_dir or _default_profile_dir()
    Path(prof).mkdir(parents=True, exist_ok=True)
    options.add_argument(f"--user-data-dir={prof}")

    # If you want a named profile inside that user-data-dir, you can set it (optional).
    # Usually unnecessary unless you’re juggling multiple profiles in the same dir.
    if profile_name:
        options.add_argument(f'--profile-directory={profile_name}')

    # Reduce “automation detected” UI noise (doesn't magically bypass anything; just cleaner)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    return webdriver.Chrome(options=options)


@dataclass(slots=True)
class BrowserRelayConfig:
    chatgpt_url: str = "https://chat.openai.com/"
    assistant_selector: str = 'div[data-message-author-role="assistant"]'
    start_marker: str = "<START>"
    stop_marker: str = "<STOP>"
    poll_interval_seconds: float = 1.5
    headless: bool = False

    # Portable profile settings
    profile_dir: Optional[str] = None
    profile_name: Optional[str] = None
    chrome_binary: Optional[str] = None

    # Debug/behavior knobs
    log_element_counts: bool = True
    max_commands_per_poll: int = 25


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
                profile_name=self.config.profile_name,
                chrome_binary=self.config.chrome_binary,
            )
        )

        self.logger = logger or logging.getLogger(__name__)
        self._stop_event = threading.Event()
        self._seen_signatures: set[str] = set()
        self._driver: webdriver.Chrome | None = None

        # Precompile extraction regex
        self._pattern = re.compile(
            re.escape(self.config.start_marker)
            + r"(.*?)"
            + re.escape(self.config.stop_marker),
            re.DOTALL,
        )

    def run(self) -> None:
        try:
            self._driver = self.driver_factory()
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Failed to create Chrome driver for browser relay: %s", exc)
            self.logger.error(
                "Fix checklist:\n"
                "  1) Ensure Google Chrome is installed.\n"
                "  2) Ensure selenium is installed (and preferably >= 4.6).\n"
                "  3) If Selenium Manager cannot download drivers (proxy/corp lock-down), "
                "install chromedriver manually OR allow outbound downloads."
            )
            return

        self.logger.info(
            "Starting ChatGPT browser relay:\n"
            "  url=%s\n"
            "  selector=%s\n"
            "  poll=%.2fs\n"
            "  headless=%s\n"
            "  profile_dir=%s\n"
            "  profile_name=%s",
            self.config.chatgpt_url,
            self.config.assistant_selector,
            self.config.poll_interval_seconds,
            self.config.headless,
            self.config.profile_dir or _default_profile_dir(),
            self.config.profile_name,
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
        if self.config.log_element_counts:
            self.logger.debug("Relay sees %d assistant elements", len(elements))

        commands = self._extract_commands(elements)

        # Clamp to avoid spam if the page suddenly matches weird stuff
        if len(commands) > self.config.max_commands_per_poll:
            commands = commands[: self.config.max_commands_per_poll]

        for command in commands:
            signature = self._signature(command)
            if signature in self._seen_signatures:
                continue
            self._seen_signatures.add(signature)
            cleaned = command.strip()
            if cleaned:
                self.logger.info("Forwarding ChatGPT command (%d chars)", len(cleaned))
                self.command_queue.put(cleaned)

    def _extract_commands(self, elements: Iterable) -> List[str]:
        commands: List[str] = []
        for element in elements:
            text = (getattr(element, "text", "") or "").strip()
            if not text:
                continue
            for match in self._pattern.findall(text):
                cleaned = match.strip()
                if cleaned:
                    commands.append(cleaned)
        return commands

    def _signature(self, command: str) -> str:
        # Stable across runs (unlike Python's built-in hash which is salted per-process)
        return hashlib.sha256(command.encode("utf-8", errors="ignore")).hexdigest()
