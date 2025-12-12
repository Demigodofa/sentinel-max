"""Input panel with entry box and send button."""
from __future__ import annotations

import tkinter as tk
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
        # NOTE: ttk.Entry styling is often ignored on Windows native themes.
        # We use tk.Entry for reliable colors + clipboard.

    def _build_widgets(self, on_send: Callable[[str], None]) -> None:
        colors = self.theme["colors"]
        fonts = self.theme["fonts"]
        self.entry_var = tk.StringVar()

        # Use tk.Entry for Windows-reliable colors + caret + selection + clipboard.
        self.entry = tk.Entry(
            self,
            textvariable=self.entry_var,
            font=fonts["body"],
            bg=colors["entry_bg"],
            fg=colors["entry_fg"],
            insertbackground=colors["entry_insert"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=colors["panel_border"],
            highlightcolor=colors["panel_border"],
        )
        self.entry.configure(selectbackground=colors["selection_bg"], selectforeground=colors["selection_fg"])
        self.entry.grid(row=0, column=0, sticky="nsew", padx=(0, self.theme["spacing"]["pad_small"]))

        # Clipboard shortcuts + right click menu
        self._bind_clipboard()

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

    def _bind_clipboard(self) -> None:
        for seq in ("<Control-c>", "<Command-c>"):
            self.entry.bind(seq, lambda e: (self.entry.event_generate("<<Copy>>"), "break"))
        for seq in ("<Control-v>", "<Command-v>"):
            self.entry.bind(seq, lambda e: (self.entry.event_generate("<<Paste>>"), "break"))
        for seq in ("<Control-x>", "<Command-x>"):
            self.entry.bind(seq, lambda e: (self.entry.event_generate("<<Cut>>"), "break"))
        self.entry.bind("<Control-a>", lambda e: (self.entry.selection_range(0, "end"), "break"))
        self.entry.bind("<Button-3>", self._open_menu)

        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(label="Cut", command=lambda: self.entry.event_generate("<<Cut>>"))
        self._menu.add_command(label="Copy", command=lambda: self.entry.event_generate("<<Copy>>"))
        self._menu.add_command(label="Paste", command=lambda: self.entry.event_generate("<<Paste>>"))
        self._menu.add_separator()
        self._menu.add_command(label="Select All", command=lambda: self.entry.selection_range(0, "end"))

    def _open_menu(self, event):  # type: ignore[override]
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def current_text(self) -> str:
        return self.entry_var.get().strip()
