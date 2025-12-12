"""Selectable/copyable chat transcript for Windows-friendly Tkinter."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ChatLog(ttk.Frame):
    """
    A scrollable text transcript that supports:
      - selection + Ctrl+C copy
      - right-click context menu (Copy / Select All)
      - readable, high contrast colors
    """

    def __init__(self, master: tk.Misc, theme: dict) -> None:
        super().__init__(master, padding=theme["spacing"]["pad_small"])
        self.theme = theme
        self.colors = theme["colors"]
        self.fonts = theme["fonts"]

        self._build()

    def _build(self) -> None:
        c = self.colors

        self.text = tk.Text(
            self,
            wrap="word",
            padx=10,
            pady=10,
            bg=c["panel_bg"],
            fg=c["text"],
            insertbackground=c["entry_insert"],
            selectbackground=c["selection_bg"],
            selectforeground=c["selection_fg"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=c["panel_border"],
            highlightcolor=c["panel_border"],
        )
        self.text.configure(font=self.fonts["body"])

        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=self.scroll.set)

        self.text.grid(row=0, column=0, sticky="nsew")
        self.scroll.grid(row=0, column=1, sticky="ns")

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # Tags for simple readability
        self.text.tag_configure("user", spacing1=6, spacing3=10)
        self.text.tag_configure("agent", spacing1=6, spacing3=10)
        self.text.tag_configure("meta", foreground=c["muted"], font=self.fonts["mono"])

        # Make it read-only but still selectable
        self.text.configure(state="disabled")

        self.text.bind("<Button-3>", self._open_menu)  # right click

        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(label="Copy", command=self._copy_menu)
        self._menu.add_command(label="Paste", command=self._paste_menu)
        self._menu.add_command(label="Cut", command=self._cut_menu)
        self._menu.add_separator()
        self._menu.add_command(label="Select All", command=self._select_all_menu)

    def append(self, who: str, message: str) -> None:
        """
        who: 'user' or 'agent' (anything else becomes 'meta')
        """
        tag = "user" if who == "user" else "agent" if who == "agent" else "meta"
        prefix = "You: " if tag == "user" else "Agent: " if tag == "agent" else ""

        self.text.configure(state="normal")
        self.text.insert("end", prefix + message.strip() + "\n", tag)
        self.text.configure(state="disabled")
        self.text.see("end")

    def _copy_menu(self) -> None:
        self.text.event_generate("<<Copy>>")

    def _cut_menu(self) -> None:
        self.text.event_generate("<<Copy>>")

    def _paste_menu(self) -> None:
        # Output is read-only; paste falls back to copying clipboard text into selection without mutation.
        try:
            clip = self.clipboard_get()
            if clip:
                self.text.clipboard_clear()
                self.text.clipboard_append(clip)
        except Exception:
            pass

    def _select_all_menu(self) -> None:
        self.text.tag_add("sel", "1.0", "end-1c")

    def _open_menu(self, event):  # type: ignore[override]
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()
