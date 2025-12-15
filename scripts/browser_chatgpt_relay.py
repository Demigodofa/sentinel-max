"""
Launch the Sentinel GUI with a ChatGPT browser relay.

What this script does:
- Starts a Chrome session (using a persistent profile dir so you log in once).
- Opens ChatGPT and polls assistant messages for <START> ... <STOP> blocks.
- Pushes extracted commands into the Sentinel GUI input queue.

Portability goals:
- Works when launched from /scripts (fixes `import sentinel`).
- Stores the Chrome profile in a repo-independent folder (default: F:\sentinel-data\chrome-profile).
- Does NOT require `chromedriver` to be installed manually (Selenium Manager handles it).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from pathlib import Path
from queue import Queue

# --------------------------------------------------------------------------------------
# Make sure repo root is on sys.path so `import sentinel` works even when launched from scripts/
# --------------------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentinel.gui.app import run_gui_app_with_queue  # noqa: E402
from sentinel.watchers.browser_command_relay import (  # noqa: E402
    BrowserRelayConfig,
    ChatGPTBrowserRelay,
)

# We'll build our own driver factory so we can:
# - set user-data-dir (profile) for one-time login
# - optionally set chrome binary
# - rely on Selenium Manager (no chromedriver PATH required)
from selenium import webdriver  # noqa: E402
from selenium.webdriver.chrome.options import Options  # noqa: E402


def _default_profile_dir() -> str:
    # Prefer env var so your launcher can control it per-machine.
    env = os.environ.get("SENTINEL_RELAY_PROFILE_DIR", "").strip()
    if env:
        return env

    # Portable-ish default: if you keep sentinel-data on F: across machines, this is stable.
    return r"F:\sentinel-data\chrome-profile"


def create_chrome_driver(
    *,
    headless: bool = False,
    profile_dir: str | None = None,
    chrome_binary: str | None = None,
) -> webdriver.Chrome:
    """
    Create a Chrome driver configured for ChatGPT relay.

    Notes:
    - Uses --user-data-dir so your login persists (log in once).
    - Uses Selenium Manager to locate/download a compatible driver automatically.
    """
    profile_dir = profile_dir or _default_profile_dir()

    # Ensure directory exists
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    opts = Options()

    # If you want to force a specific Chrome binary path (optional)
    if chrome_binary:
        opts.binary_location = chrome_binary

    # Headless is optional; for ChatGPT login the first time, keep it visible.
    if headless:
        # "new" headless is the modern mode
        opts.add_argument("--headless=new")

    # Keep it stable on Windows
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")

    # IMPORTANT: persistent profile (this is the key to "login once")
    opts.add_argument(f"--user-data-dir={profile_dir}")

    # Quality of life
    opts.add_argument("--start-maximized")

    # Create the driver. With Selenium 4.6+ this should use Selenium Manager automatically.
    return webdriver.Chrome(options=opts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Relay ChatGPT commands into Sentinel (GUI).")

    parser.add_argument(
        "--chatgpt-url",
        default="https://chat.openai.com/",
        help="ChatGPT conversation URL to open and monitor.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=1.5,
        help="How often to scan the ChatGPT transcript for wrapped commands.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome headless (ONLY if you already have a logged-in profile).",
    )
    parser.add_argument(
        "--start-marker",
        default="<START>",
        help="Marker used to denote the start of a command block.",
    )
    parser.add_argument(
        "--stop-marker",
        default="<STOP>",
        help="Marker used to denote the end of a command block.",
    )
    parser.add_argument(
        "--selector",
        default='div[data-message-author-role="assistant"]',
        help="CSS selector for assistant messages in ChatGPT.",
    )
    parser.add_argument(
        "--profile-dir",
        default=_default_profile_dir(),
        help=r"Chrome user profile dir for persistent login (e.g. F:\sentinel-data\chrome-profile).",
    )
    parser.add_argument(
        "--chrome-binary",
        default=os.environ.get("SENTINEL_CHROME_BINARY", "").strip() or None,
        help=r"Optional: explicit path to chrome.exe (or set SENTINEL_CHROME_BINARY).",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    logger = logging.getLogger("browser_relay_launcher")

    command_queue: Queue[str] = Queue()

    config = BrowserRelayConfig(
        chatgpt_url=args.chatgpt_url,
        assistant_selector=args.selector,
        start_marker=args.start_marker,
        stop_marker=args.stop_marker,
        poll_interval_seconds=args.poll_seconds,
        headless=args.headless,
    )

    def driver_factory() -> webdriver.Chrome:
        logger.info("Launching Chrome with profile dir: %s", args.profile_dir)
        if args.chrome_binary:
            logger.info("Using explicit Chrome binary: %s", args.chrome_binary)
        return create_chrome_driver(
            headless=args.headless,
            profile_dir=args.profile_dir,
            chrome_binary=args.chrome_binary,
        )

    relay = ChatGPTBrowserRelay(
        command_queue,
        config=config,
        driver_factory=driver_factory,
        logger=logging.getLogger("browser_relay"),
    )

    relay_thread = threading.Thread(target=relay.run, daemon=True)

    try:
        relay_thread.start()
        run_gui_app_with_queue(command_queue)
    finally:
        relay.stop()
        relay_thread.join(timeout=5)


if __name__ == "__main__":
    main()
