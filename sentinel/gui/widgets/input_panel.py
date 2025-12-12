"""Input panel with entry box and send button."""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import TclError, ttk
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
        # NOTE: ttk.Entry styling is often ignored on Windows native themes.
        # We use tk.Entry for reliable colors + clipboard.

    def _build_widgets(self, on_send: Callable[[str], None]) -> None:
        colors = self.theme["colors"]
        fonts = self.theme["fonts"]
        self.entry_var = tk.StringVar()

        # Windows + ttk.Entry is notorious for ignoring fg/bg under the default theme,
        # and ttk.Entry does NOT support "insertbackground" (tk.Entry does).
        # So: on Windows, always use tk.Entry for legible colors + reliable clipboard.
        if sys.platform.startswith("win"):
            self.entry = tk.Entry(
                self,
                textvariable=self.entry_var,
                font=fonts["body"],
                bg=colors.get("entry_bg", colors.get("panel_bg", "#ffffff")),
                fg=colors.get("entry_fg", colors.get("text", "#111111")),
                insertbackground=colors.get("entry_insert", colors.get("accent", "#0b5fff")),
                relief="flat",
                highlightthickness=1,
                highlightbackground=colors.get("panel_border", colors.get("border", "#cccccc")),
                highlightcolor=colors.get("panel_border", colors.get("accent", "#0b5fff")),
                exportselection=False,
            )
            self.entry.configure(
                selectbackground=colors.get("selection_bg", colors.get("accent", "#0b5fff")),
                selectforeground=colors.get("selection_fg", colors.get("panel_bg", "#ffffff")),
            )
        else:
            self.entry = ttk.Entry(
                self, textvariable=self.entry_var, font=fonts["body"], style="InputPanel.TEntry"
            )
        self.entry.grid(row=0, column=0, sticky="nsew", padx=(0, self.theme["spacing"]["pad_small"]))

        # Clipboard shortcuts + right click menu
        self._bind_clipboard_shortcuts()
        self._install_context_menu()

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

    def _handle_send(self, on_send: Callable[[str], None]) -> None:
        text = self.entry_var.get().strip()
        if not text:
            return
        on_send(text)
        self.entry_var.set("")
        self.entry.focus_set()

    def _bind_clipboard_shortcuts(self) -> None:
        # Explicit bindings because some ttk setups can swallow defaults on Windows.
        for sequence in ("<Control-c>", "<Command-c>"):
            self.entry.bind(sequence, self._copy)
        for sequence in ("<Control-v>", "<Command-v>"):
            self.entry.bind(sequence, self._paste)
        for sequence in ("<Control-a>", "<Command-a>"):
            self.entry.bind(sequence, self._select_all)

    def _copy(self, event=None):  # type: ignore[override]
        try:
            self.entry.event_generate("<<Copy>>")
        except TclError:
            return "break"
        return "break"

    def _paste(self, event=None):  # type: ignore[override]
        try:
            self.entry.event_generate("<<Paste>>")
        except TclError:
            return "break"
        return "break"

    def _select_all(self, event=None):  # type: ignore[override]
        try:
            self.entry.selection_range(0, tk.END)
            self.entry.icursor(tk.END)
        except TclError:
            return "break"
        return "break"

    def _install_context_menu(self) -> None:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Cut", command=lambda: self.entry.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: self.entry.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: self.entry.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: self.entry.event_generate("<<SelectAll>>"))

        def popup(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        # Windows: Button-3. macOS trackpad can be Button-2 sometimes.
        self.entry.bind("<Button-3>", popup)
        self.entry.bind("<Button-2>", popup)

    def current_text(self) -> str:
        return self.entry_var.get().strip()
