"""Tkinter GUI bootstrap for Sentinel MAX."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from sentinel.gui.theme import load_theme
from sentinel.gui.widgets.chat_log import ChatLog
from sentinel.gui.widgets.input_panel import InputPanel


def run_gui_app() -> None:
    theme = load_theme()
    root = tk.Tk()
    root.title("Sentinel MAX")

    # Windows ttk native themes often ignore background colors.
    # Force a theme that respects style settings.
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    root.configure(bg=theme["colors"]["app_bg"])
    root.minsize(760, 520)

    app = SentinelApp(root, theme=theme)
    root.mainloop()


class SentinelApp:
    def __init__(self, root: tk.Tk, theme: dict | None = None):
        self.root = root
        self.theme = theme or load_theme()
        self._build_layout()

    def _build_layout(self) -> None:
        c = self.theme["colors"]

        container = ttk.Frame(self.root, padding=self.theme["spacing"]["pad_small"])
        container.pack(fill="both", expand=True)

        self.chat = ChatLog(container, theme=self.theme)
        self.chat.pack(fill="both", expand=True)

        self.input_panel = InputPanel(container, on_send=self._handle_send, theme=self.theme)
        self.input_panel.pack(fill="x", pady=(self.theme["spacing"]["pad_small"], 0))

        self.chat.append("meta", "Sentinel MAX GUI ready. Type a message below.")

    def _handle_send(self, text: str) -> None:
        # Show user message immediately (copyable transcript)
        self.chat.append("user", text)

        # TODO: call your GUIBridge/controller here.
        # Keep it simple & safe: append agent response text.
        try:
            response = self._process(text)  # replace with your pipeline call
        except Exception as e:
            response = f"[error] {e}"
        self.chat.append("agent", str(response))

    def _process(self, text: str) -> str:
        # Placeholder until wired to controller/bridge:
        return "OK. (wire GUIBridge/controller response here)"
