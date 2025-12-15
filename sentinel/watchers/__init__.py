"""Watchers that bridge external interfaces into Sentinel."""

from sentinel.watchers.browser_command_relay import (  # noqa: F401
    BrowserRelayConfig,
    ChatGPTBrowserRelay,
    create_chrome_driver,
)

