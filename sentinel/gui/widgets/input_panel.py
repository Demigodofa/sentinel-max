"""Input panel with entry box and send button."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, TclError

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

    def _configure_styles(self) -> None:
        style = ttk.Style()
        colors = self.theme["colors"]
        style.configure(
            "InputPanel.TFrame",
            background=colors["panel_bg"],
            borderwidth=self.theme["border"]["width"],
            relief=self.theme["border"]["relief"],
        )
        style.configure(
            "InputPanel.TButton",
            background=colors["accent"],
            foreground=colors["panel_bg"],
            padding=self.theme["spacing"]["pad_small"],
        )
        # ttk.Entry style — only applies on macOS/Linux reliably.
        # Windows will ignore unsupported options, but fallback handles it.
        style.configure(
            "InputPanel.TEntry",
            foreground=colors["text"],
            fieldbackground=colors["panel_bg"],
            borderwidth=0,
        )

        # Ensure focus highlight does not go white on Windows
        style.map(
            "InputPanel.TEntry",
            foreground=[["active", colors["text"]]],
            fieldbackground=[["active", colors["panel_bg"]]],
        )

    def _build_widgets(self, on_send: Callable[[str], None]) -> None:
        colors = self.theme["colors"]
        fonts = self.theme["fonts"]
        self.entry_var = tk.StringVar()

        # Create a robust entry widget:
        # 1. Try ttk.Entry with dark theme
        # 2. If styling fails (Windows), fallback to tk.Entry with explicit colors
        self.entry = self._create_entry(colors, fonts)
        self.entry.grid(row=0, column=0, sticky="nsew", padx=(0, self.theme["spacing"]["pad_small"]))

        # Clipboard bindings (Windows/Linux/Mac)
        self._bind_clipboard_shortcuts()

        self.send_button = ttk.Button(
            self,
            text="Send",
            command=lambda: self._handle_send(on_send),
            style="InputPanel.TButton",
        )
        self.send_button.grid(row=0, column=1, sticky="e")

        self.entry.bind("<Return>", lambda _: self._handle_send(on_send))

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.configure(style="InputPanel.TFrame")


    def _create_entry(self, colors: dict, fonts: dict):
        """Creates a ttk.Entry with fallback to tk.Entry on Windows."""
        try:
            # Try themed ttk.Entry
            widget = ttk.Entry(
                self,
                textvariable=self.entry_var,
                font=fonts["body"],
                style="InputPanel.TEntry",
            )

            # If ttk supports insertbackground, set it
            try:
                widget.configure(insertbackground=colors["accent"])
            except TclError:
                pass

            return widget

        except Exception:
            # Fallback: standard tk.Entry with explicit styling
            return tk.Entry(
                self,
                textvariable=self.entry_var,
                font=fonts["body"],
                bg=colors["panel_bg"],
                fg=colors["text"],
                insertbackground=colors["accent"],
                relief="flat",
                highlightthickness=0,
            )

    def _handle_send(self, on_send: Callable[[str], None]) -> None:
        text = self.entry_var.get().strip()
        if not text:
            return
        on_send(text)
        self.entry_var.set("")
        self.entry.focus_set()

    def _bind_clipboard_shortcuts(self):
        """Universal copy/paste bindings for Windows, macOS, Linux."""
        # Copy
        self.entry.bind("<Control-c>", self._copy)
        self.entry.bind("<Control-C>", self._copy)
        self.entry.bind("<Command-c>", self._copy)

        # Paste
        self.entry.bind("<Control-v>", self._paste)
        self.entry.bind("<Control-V>", self._paste)
        self.entry.bind("<Command-v>", self._paste)

    def _copy(self, event=None):
        try:
            self.entry.event_generate("<<Copy>>")
        except TclError:
            return "break"
        return "break"

    def _paste(self, event=None):
        try:
            self.entry.event_generate("<<Paste>>")
        except TclError:
            return "break"
        return "break"

    def current_text(self) -> str:
        return self.entry_var.get().strip()
