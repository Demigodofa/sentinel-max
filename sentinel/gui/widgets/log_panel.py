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
        self.text.configure(state="normal")

        self.text.bind("<Button-3>", self._open_menu)

        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(label="Copy", command=self._copy_menu)
        self._menu.add_command(label="Paste", command=self._paste_menu)
        self._menu.add_command(label="Cut", command=self._cut_menu)
        self._menu.add_separator()
        self._menu.add_command(label="Select All", command=self._select_all_menu)

        self.text.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def append_logs(self, lines: Iterable[str]) -> None:
        """Append new log lines and scroll to bottom."""

        if not lines:
            return

        for line in lines:
            self.text.insert(tk.END, line.rstrip() + "\n")
        self.text.see(tk.END)

    def _copy(self, event=None):  # type: ignore[override]
        self.text.event_generate("<<Copy>>")
        return "break"

    def _copy_menu(self) -> None:
        self.text.event_generate("<<Copy>>")

    def _cut_menu(self) -> None:
        self.text.event_generate("<<Copy>>")

    def _paste_menu(self) -> None:
        try:
            clip = self.text.clipboard_get()
            if clip:
                self.text.clipboard_clear()
                self.text.clipboard_append(clip)
        except Exception:
            pass

    def _select_all(self, event=None):  # type: ignore[override]
        self.text.tag_add("sel", "1.0", "end-1c")
        return "break"

    def _select_all_menu(self) -> None:
        self.text.tag_add("sel", "1.0", "end-1c")

    def _open_menu(self, event):  # type: ignore[override]
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()
