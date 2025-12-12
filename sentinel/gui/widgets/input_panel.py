"""
Clean, Windows-safe input panel with readable text, copy/paste,
and consistent ttk/tk behavior across OSes.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import TclError, ttk

# Windows ttk Entry does NOT support background/insert colors normally,
# so we implement a safe fallback and enforce dark-mode readability.
from typing import Callable

from sentinel.gui.theme import load_theme


class InputPanel(ttk.Frame):
    """Panel for user commands to the agent."""

    def __init__(self, master: tk.Misc, on_send: Callable[[str], None], theme: dict | None = None) -> None:
        self.theme = theme or load_theme()
        super().__init__(master, padding=self.theme["spacing"]["pad"], style="InputPanel.TFrame")
        self._configure_styles()
        self._build_widgets(on_send)

    # ------------------------------------------------------------
    # STYLE CONFIGURATION (Windows-safe)
    # ------------------------------------------------------------
    def _configure_styles(self) -> None:
        style = ttk.Style()
        colors = self.theme["colors"]
        style.configure(
            "InputPanel.TFrame",
            background=colors["panel_bg"]
        )
        style.configure(
            "InputPanel.TButton",
            background=colors["accent"],
            foreground=colors["panel_bg"],
            padding=self.theme["spacing"]["pad_small"],
        )
        # Windows ttk ignores Entry background, so we use fieldbackground
        style.configure(
            "InputPanel.TEntry",
            foreground=colors["text"],
            fieldbackground=colors["panel_bg"],
            insertcolor=colors["accent"],
            borderwidth=1
        )

    # ------------------------------------------------------------
    # ENTRY CREATION (ttk first, fallback to tk.Entry)
    # ------------------------------------------------------------
    def _build_widgets(self, on_send: Callable[[str], None]) -> None:
        colors = self.theme["colors"]
        fonts = self.theme["fonts"]

        self.entry_var = tk.StringVar()

        # First try ttk.Entry
        try:
            self.entry = ttk.Entry(
                self,
                textvariable=self.entry_var,
                font=fonts["body"],
                style="InputPanel.TEntry"
            )
        except TclError:
            # Fallback to tk.Entry (Windows-safe)
            self.entry = tk.Entry(
                self,
                textvariable=self.entry_var,
                font=fonts["body"],
                bg=colors["panel_bg"],
                fg=colors["text"],
                insertbackground=colors["accent"],
                relief="solid",
                borderwidth=1,
                highlightthickness=0
            )

        self.entry.grid(row=0, column=0, sticky="nsew", padx=(0, self.theme["spacing"]["pad_small"]))

        # FORCE COLORS even if ttk theme overrides it (Windows)
        try:
            self.entry.configure(
                foreground=colors["text"],
                background=colors["panel_bg"]
            )
        except TclError:
            pass

        self._bind_clipboard_shortcuts()

        self.send_button = ttk.Button(
            self,
            text="Send",
            command=lambda: self._handle_send(on_send),
            style="InputPanel.TButton",
        )
        self.send_button.grid(row=0, column=1, sticky="e")

        self.entry.bind("<Return>", lambda _: self._handle_send(on_send))
        self.entry.focus_set()

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.configure(style="InputPanel.TFrame")

    # ------------------------------------------------------------
    # SEND HANDLER
    # ------------------------------------------------------------
    def _handle_send(self, on_send: Callable[[str], None]) -> None:
        text = self.entry_var.get().strip()
        if not text:
            return
        on_send(text)
        self.entry_var.set("")
        self.entry.focus_set()

    # ------------------------------------------------------------
    # CLIPBOARD SUPPORT (Windows/macOS/Linux)
    # ------------------------------------------------------------
    def _bind_clipboard_shortcuts(self) -> None:
        mappings = {
            "<Control-c>": "<<Copy>>",
            "<Control-v>": "<<Paste>>",
            "<Control-x>": "<<Cut>>",
            "<Command-c>": "<<Copy>>",
            "<Command-v>": "<<Paste>>",
            "<Command-x>": "<<Cut>>"
        }

        for key, event in mappings.items():
            self.entry.bind(key, lambda e, ev=event: self._run_clipboard(ev))

    def _run_clipboard(self, event_name: str):
        try:
            self.entry.event_generate(event_name)
        except TclError:
            pass
        return "break"

    def current_text(self) -> str:
        return self.entry_var.get().strip()
