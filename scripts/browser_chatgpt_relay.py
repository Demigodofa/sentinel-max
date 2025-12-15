"""Launch the Sentinel GUI with a ChatGPT browser relay."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on sys.path so `import sentinel` works when launched from /scripts
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import logging
import os
import threading
from queue import Queue

from sentinel.gui.app import run_gui_app_with_queue
from sentinel.watchers.browser_command_relay import (
    BrowserRelayConfig,
    ChatGPTBrowserRelay,
    create_chrome_driver,
)


def default_profile_dir() -> str:
    # Prefer env var if set, otherwise default under F:\sentinel-data\chrome-profile\<COMPUTERNAME>
    env = os.environ.get("SENTINEL_RELAY_PROFILE_DIR")
    if env:
        return env
    computer = os.environ.get("COMPUTERNAME", "DEFAULT")
    return fr"F:\sentinel-data\chrome-profile\{computer}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Relay ChatGPT commands into Sentinel.")
    parser.add_argument("--chatgpt-url", default="https://chat.openai.com/")
    parser.add_argument("--poll-seconds", type=float, default=1.5)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--start-marker", default="<START>")
    parser.add_argument("--stop-marker", default="<STOP>")
    parser.add_argument("--selector", default='div[data-message-author-role="assistant"]')

    parser.add_argument(
        "--profile-dir",
        default=default_profile_dir(),
        help="Chrome user-data-dir folder to persist login (close Chrome before running).",
    )
    parser.add_argument(
        "--chrome-binary",
        default=None,
        help="Optional full path to chrome.exe if auto-detect is weird.",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    command_queue: Queue[str] = Queue()

    config = BrowserRelayConfig(
        chatgpt_url=args.chatgpt_url,
        assistant_selector=args.selector,
        start_marker=args.start_marker,
        stop_marker=args.stop_marker,
        poll_interval_seconds=args.poll_seconds,
        headless=args.headless,
    )

    relay = ChatGPTBrowserRelay(
        command_queue,
        config=config,
        driver_factory=lambda: create_chrome_driver(
            headless=args.headless,
            profile_dir=args.profile_dir,
            chrome_binary=args.chrome_binary,
        ),
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
