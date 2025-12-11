# sentinel/tools/browser_agent.py
# Hybrid Browser Automation Tool for Sentinel MAX
# Supports:
#  - Headless Playwright browser (fast, safe)
#  - Visible Chrome control via CDP (ONLY DOM-level interactions)
#  - Unified navigation/click/fill/scroll/JS runner API

from __future__ import annotations

import asyncio
import importlib.util
import threading
from typing import Optional, Any, Dict

from sentinel.agent_core.base import Tool
from sentinel.logging.logger import get_logger
from sentinel.tools.tool_schema import ToolSchema

# Playwright (headless mode)
playwright_root = importlib.util.find_spec("playwright")
playwright_spec = importlib.util.find_spec("playwright.sync_api") if playwright_root else None
if playwright_spec:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
else:
    PLAYWRIGHT_AVAILABLE = False

# CDP visible-mode support (Chrome DevTools Protocol)
import json
websockets_spec = importlib.util.find_spec("websockets")
if websockets_spec:
    import websockets  # type: ignore
else:
    websockets = None
requests_spec = importlib.util.find_spec("requests")
if requests_spec:
    import requests  # type: ignore
else:
    requests = None


log = get_logger(__name__)


class BrowserAgent(Tool):
    """
    Hybrid browser automation tool providing:
      - Headless browser automation via Playwright.
      - Visible browser automation via Chrome DevTools Protocol (CDP).

    Visible mode is ONLY used when user explicitly requests
    text injection or pressing enter into a live browser tab.

    All actions are DOM-level and cannot interact with the OS.
    """

    name = "browser_agent"
    description = "Unified headless/visible browser automation tool."

    def __init__(self):
        super().__init__(self.name, self.description, deterministic=False)
        self.headless_browser = None
        self.headless_page = None

        # CDP
        self.cdp_ws = None
        self.cdp_id_counter = 1
        self.schema = ToolSchema(
            name="browser_agent",
            version="1.0.0",
            description=self.description,
            input_schema={
                "mode": {"type": "string", "required": False},
                "action": {"type": "string", "required": True},
                "selector": {"type": "string", "required": False},
                "url": {"type": "string", "required": False},
                "script": {"type": "string", "required": False},
                "value": {"type": "string", "required": False},
            },
            output_schema={"type": "object"},
            permissions=["net:read", "browser"],
            deterministic=False,
        )

    # ================================
    # Internal helpers
    # ================================

    def _next_cdp_id(self) -> int:
        self.cdp_id_counter += 1
        return self.cdp_id_counter

    async def _cdp_send(self, method: str, params: dict = None) -> dict:
        """Send a CDP command to the connected Chrome instance."""
        if not self.cdp_ws:
            raise RuntimeError("CDP connection not established.")

        payload = {
            "id": self._next_cdp_id(),
            "method": method,
            "params": params or {},
        }
        await self.cdp_ws.send(json.dumps(payload))
        response = await self.cdp_ws.recv()
        return json.loads(response)

    # ================================
    # HEADLESS MODE
    # ================================

    def ensure_headless(self):
        """Start Playwright headless browser if not already active."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright not installed.")

        if self.headless_browser is None:
            log.info("Launching headless browser...")
            self.play = sync_playwright().start()
            self.headless_browser = self.play.chromium.launch(headless=True)
            self.headless_page = self.headless_browser.new_page()

    def headless_goto(self, url: str):
        self.ensure_headless()
        self.headless_page.goto(url)

    def headless_click(self, selector: str):
        self.ensure_headless()
        self.headless_page.click(selector)

    def headless_fill(self, selector: str, text: str):
        self.ensure_headless()
        self.headless_page.fill(selector, text)

    def headless_press_enter(self, selector: str):
        self.ensure_headless()
        self.headless_page.press(selector, "Enter")

    def headless_scroll(self, amount: int = 500):
        self.ensure_headless()
        self.headless_page.evaluate(f"window.scrollBy(0, {amount});")

    def headless_extract(self, selector: str) -> str:
        self.ensure_headless()
        element = self.headless_page.query_selector(selector)
        if not element:
            return ""
        return element.inner_text()

    def headless_run_js(self, script: str) -> Any:
        self.ensure_headless()
        return self.headless_page.evaluate(script)

    # ================================
    # VISIBLE MODE (Chrome DevTools)
    # ================================

    def connect_visible(self, chrome_debug_port: int = 9222):
        """
        Connect to an existing Chrome session launched with:
            chrome.exe --remote-debugging-port=9222

        Only DOM-level control. No OS interactions.
        """
        url = f"http://127.0.0.1:{chrome_debug_port}/json"
        tabs = requests.get(url).json()
        if not tabs:
            raise RuntimeError("No Chrome tabs available for CDP.")

        ws_url = tabs[0]["webSocketDebuggerUrl"]
        self.cdp_ws = asyncio.get_event_loop().run_until_complete(
            websockets.connect(ws_url)
        )
        log.info("Connected to visible Chrome via CDP.")

    def visible_goto(self, url: str):
        asyncio.get_event_loop().run_until_complete(
            self._cdp_send("Page.navigate", {"url": url})
        )

    def visible_scroll(self, amount: int = 500):
        script = f"window.scrollBy(0, {amount});"
        self.visible_run_js(script)

    def visible_run_js(self, script: str) -> Any:
        response = asyncio.get_event_loop().run_until_complete(
            self._cdp_send("Runtime.evaluate", {"expression": script})
        )
        return response.get("result", {}).get("value")

    def visible_click(self, selector: str):
        js = (
            f"""
            var el = document.querySelector("{selector}");
            if (el) el.click();
            """
        )
        self.visible_run_js(js)

    def visible_fill(self, selector: str, text: str):
        js = (
            f"""
            var el = document.querySelector("{selector}");
            if (el) el.value = "{text}";
            """
        )
        self.visible_run_js(js)

    def visible_press_enter(self, selector: str):
        js = (
            f"""
            var el = document.querySelector("{selector}");
            if (el) {{
                var evt = new KeyboardEvent('keydown', {{key:'Enter'}});
                el.dispatchEvent(evt);
            }}
            """
        )
        self.visible_run_js(js)

    def visible_extract(self, selector: str) -> str:
        js = (
            f"""
            var el = document.querySelector("{selector}");
            el ? el.innerText : "";
            """
        )
        return self.visible_run_js(js) or ""

    # ================================
    # Unified entry point
    # ================================

    def execute(self, **kwargs: Any) -> Any:
        return self.run(**kwargs)

    def run(self, **kwargs) -> Any:
        """
        Commands:
          mode: "headless" or "visible"
          action: goto | click | fill | scroll | press_enter | extract | run_js
        """
        mode = kwargs.get("mode", "headless")
        action = kwargs.get("action")
        value = kwargs.get("value")
        selector = kwargs.get("selector")
        script = kwargs.get("script")
        url = kwargs.get("url")

        if mode not in ("headless", "visible"):
            return {"error": "Invalid mode."}

        try:
            if mode == "headless":
                if action == "goto": self.headless_goto(url)
                elif action == "click": self.headless_click(selector)
                elif action == "fill": self.headless_fill(selector, value)
                elif action == "press_enter": self.headless_press_enter(selector)
                elif action == "scroll": self.headless_scroll(int(value or 500))
                elif action == "extract": return self.headless_extract(selector)
                elif action == "run_js": return self.headless_run_js(script)
                else: return {"error": f"Unknown headless action {action}"}

            if mode == "visible":
                if not self.cdp_ws:
                    self.connect_visible()

                if action == "goto": self.visible_goto(url)
                elif action == "click": self.visible_click(selector)
                elif action == "fill": self.visible_fill(selector, value)
                elif action == "press_enter": self.visible_press_enter(selector)
                elif action == "scroll": self.visible_scroll(int(value or 500))
                elif action == "extract": return self.visible_extract(selector)
                elif action == "run_js": return self.visible_run_js(script)
                else: return {"error": f"Unknown visible action {action}"}

        except Exception as e:
            log.error(f"BrowserAgent error: {e}")
            return {"error": str(e)}

        return {"status": "ok"}


__all__ = ["BrowserAgent"]
