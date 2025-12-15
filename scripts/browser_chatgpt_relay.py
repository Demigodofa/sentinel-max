"""Launch the Sentinel GUI with a ChatGPT browser relay."""
from __future__ import annotations

import argparse
import logging
import threading
from queue import Queue

from sentinel.gui.app import run_gui_app_with_queue
from sentinel.watchers.browser_command_relay import (
    BrowserRelayConfig,
    ChatGPTBrowserRelay,
    create_chrome_driver,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Relay ChatGPT commands into Sentinel.")
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
        help="Run the ChatGPT browser session in headless mode (requires an existing login session).",
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
        driver_factory=lambda: create_chrome_driver(headless=args.headless),
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
