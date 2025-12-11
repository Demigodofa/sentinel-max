"""Log panel widget for Sentinel MAX GUI."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Iterable

from sentinel.gui.theme import load_theme


class LogPanel(ttk.Frame):
    """Scrollable log view that efficiently appends new lines."""

    def __init__(self, master: tk.Misc, theme: dict | None = None) -> None:
        self.theme = theme or load_theme()
        super().__init__(master, padding=self.theme["spacing"]["pad"], style="LogPanel.TFrame")
        self._configure_styles()
        self._build_widgets()

    def _configure_styles(self) -> None:
        style = ttk.Style()
        colors = self.theme["colors"]
        style.configure(
            "LogPanel.TFrame",
            background=colors["panel_bg"],
            borderwidth=self.theme["border"]["width"],
            relief=self.theme["border"]["relief"],
        )

    def _build_widgets(self) -> None:
        colors = self.theme["colors"]
        fonts = self.theme["fonts"]
        self.text = tk.Text(
            self,
            wrap="word",
            background=colors["panel_bg"],
            foreground=colors["text"],
            insertbackground=colors["accent"],
            font=fonts["mono"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=self.scrollbar.set)
        self.text.configure(state="disabled")

        self.text.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def append_logs(self, lines: Iterable[str]) -> None:
        """Append new log lines and scroll to bottom."""

        if not lines:
            return

        self.text.configure(state="normal")
        for line in lines:
            self.text.insert(tk.END, line.rstrip() + "\n")
        self.text.see(tk.END)
        self.text.configure(state="disabled")
