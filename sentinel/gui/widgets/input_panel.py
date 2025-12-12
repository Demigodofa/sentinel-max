"""Input panel with entry box and send button."""
from __future__ import annotations

import sys
IS_DARWIN = sys.platform == "darwin"

def _platform_seqs(ctrl_seq: str, cmd_seq: str):
    # On Windows/Linux, do NOT bind <Command-*> because it can behave like a stuck modifier.
    return (ctrl_seq, cmd_seq) if IS_DARWIN else (ctrl_seq,)

import tkinter as tk
import os
from tkinter import ttk
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

    def _build_widgets(self, on_send: Callable[[str], None]) -> None:
        colors = self.theme["colors"]
        fonts = self.theme["fonts"]
        self.entry_var = tk.StringVar()

        # Windows-safe: tk.Entry always respects bg/fg/insert colors reliably.
        self.entry = tk.Entry(
            self,
            textvariable=self.entry_var,
            font=fonts["body"],
            bg=colors["panel_bg"],
            fg=colors["text"],
            insertbackground=colors["accent"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=colors["accent"],
            highlightcolor=colors["accent"],
        )
        self.entry.grid(row=0, column=0, sticky="nsew", padx=(0, self.theme["spacing"]["pad_small"]))

        self.send_button = ttk.Button(
            self,
            text="Send",
            command=lambda: self._handle_send(on_send),
            style="InputPanel.TButton",
        )
        self.send_button.grid(row=0, column=1, sticky="e")

        self.entry.bind("<Return>", lambda _: self._handle_send(on_send))
        for seq in _platform_seqs("<Control-a>", "<Command-a>"):
            self.entry.bind(seq, self._select_all)
        for seq in _platform_seqs("<Control-v>", "<Command-v>"):
            self.entry.bind(seq, self._paste)
        for seq in _platform_seqs("<Control-x>", "<Command-x>"):
            self.entry.bind(seq, self._cut)
        for seq in _platform_seqs("<Control-c>", "<Command-c>"):
            self.entry.bind(seq, self._copy)
        self.entry.bind("<Button-3>", self._open_menu)

        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(label="Cut", command=self._cut_menu)
        self._menu.add_command(label="Copy", command=self._copy_menu)
        self._menu.add_command(label="Paste", command=self._paste_menu)

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.configure(style="InputPanel.TFrame")
        self.after_idle(self.entry.focus_set)

    def _handle_send(self, on_send: Callable[[str], None]) -> None:
        text = self.entry_var.get().strip()
        if not text:
            return
        on_send(text)
        self.entry_var.set("")
        self.after_idle(self.entry.focus_set)

    def current_text(self) -> str:
        return self.entry_var.get().strip()

    # Clipboard helpers -------------------------------------------------
    def _select_all(self, event=None):  # type: ignore[override]
        self.entry.selection_range(0, "end")
        return "break"

    def _copy(self, event=None):  # type: ignore[override]
        self.entry.event_generate("<<Copy>>")
        return "break"

    def _cut(self, event=None):  # type: ignore[override]
        self.entry.event_generate("<<Cut>>")
        return "break"

    def _paste(self, event=None):  # type: ignore[override]
        self.entry.event_generate("<<Paste>>")
        return "break"

    def _open_menu(self, event):  # type: ignore[override]
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _copy_menu(self) -> None:
        self.entry.event_generate("<<Copy>>")

    def _cut_menu(self) -> None:
        self.entry.event_generate("<<Cut>>")

    def _paste_menu(self) -> None:
        self.entry.event_generate("<<Paste>>")
