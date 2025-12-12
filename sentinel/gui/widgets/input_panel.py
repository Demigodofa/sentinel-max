"""Input panel with entry box and send button."""
from __future__ import annotations

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
        style.configure(
            "InputPanel.TEntry",
            foreground=colors["text"],
            fieldbackground=colors["input_bg"],
            background=colors["input_bg"],
            insertcolor=colors["accent"],
            bordercolor=colors["input_border"],
            relief="flat",
            padding=self.theme["spacing"]["pad_small"],
        )

    def _build_widgets(self, on_send: Callable[[str], None]) -> None:
        colors = self.theme["colors"]
        fonts = self.theme["fonts"]
        self.entry_var = tk.StringVar()

        # Prefer ttk.Entry so native themes still work; fallback to tk.Entry if unsupported
        self.entry = self._create_entry(fonts, colors)
        self.entry.grid(row=0, column=0, sticky="nsew", padx=(0, self.theme["spacing"]["pad_small"]))

        # Clipboard shortcuts for common platforms
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


    def _create_entry(self, fonts: dict, colors: dict) -> tk.Entry:
        try:
            return ttk.Entry(
                self,
                textvariable=self.entry_var,
                font=fonts["body"],
                style="InputPanel.TEntry",
            )
        except TclError:
            return tk.Entry(
                self,
                textvariable=self.entry_var,
                font=fonts["body"],
                bg=colors["input_bg"],
                fg=colors["text"],
                insertbackground=colors["accent"],
                relief="flat",
                highlightthickness=1,
                highlightcolor=colors["input_border"],
                highlightbackground=colors["input_border"],
                borderwidth=self.theme["border"]["width"],
            )

    def _handle_send(self, on_send: Callable[[str], None]) -> None:
        text = self.entry_var.get().strip()
        if not text:
            return
        on_send(text)
        self.entry_var.set("")
        self.entry.focus_set()

    def _bind_clipboard_shortcuts(self) -> None:
        for sequence in ("<Control-c>", "<Command-c>"):
            self.entry.bind(sequence, self._copy)
        for sequence in ("<Control-v>", "<Command-v>"):
            self.entry.bind(sequence, self._paste)
        for sequence in ("<Control-x>", "<Command-x>"):
            self.entry.bind(sequence, self._cut)

        # Right-click context menu for mouse-driven clipboard interactions
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Cut", command=lambda: self._cut())
        menu.add_command(label="Copy", command=lambda: self._copy())
        menu.add_command(label="Paste", command=lambda: self._paste())

        def show_menu(event: tk.Event) -> str:
            menu.tk_popup(event.x_root, event.y_root)
            return "break"

        self.entry.bind("<Button-3>", show_menu)

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

    def _cut(self, event=None):  # type: ignore[override]
        try:
            self.entry.event_generate("<<Cut>>")
        except TclError:
            return "break"
        return "break"

    def current_text(self) -> str:
        return self.entry_var.get().strip()
