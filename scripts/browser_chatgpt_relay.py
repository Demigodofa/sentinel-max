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
import threading
from queue import Queue

from sentinel.gui.app import run_gui_app_with_queue
from sentinel.watchers.browser_command_relay import (
    BrowserRelayConfig,
    ChatGPTBrowserRelay,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Relay ChatGPT <START>/<STOP> commands into Sentinel GUI.")
    parser.add_argument("--chatgpt-url", default="https://chat.openai.com/")
    parser.add_argument("--poll-seconds", type=float, default=1.5)
    parser.add_argument("--headless", action="store_true")

    parser.add_argument("--start-marker", default="<START>")
    parser.add_argument("--stop-marker", default="<STOP>")
    parser.add_argument("--selector", default='div[data-message-author-role="assistant"]')

    # NEW: profile + attach options
    parser.add_argument("--profile-dir", default=None, help="Chrome user-data-dir to use (recommended).")
    parser.add_argument("--chrome-binary", default=None, help="Explicit chrome.exe path (optional).")
    parser.add_argument("--attach-debug-port", type=int, default=None,
                        help="Attach to an existing Chrome started with --remote-debugging-port=PORT.")

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
        profile_dir=args.profile_dir,
        chrome_binary=args.chrome_binary,
        attach_debug_port=args.attach_debug_port,
    )

    relay = ChatGPTBrowserRelay(command_queue, config=config, logger=logging.getLogger("browser_relay"))
    relay_thread = threading.Thread(target=relay.run, daemon=True)

    try:
        relay_thread.start()
        run_gui_app_with_queue(command_queue)
    finally:
        relay.stop()
        relay_thread.join(timeout=5)


if __name__ == "__main__":
    main()
