from __future__ import annotations

import tkinter as tk
from typing import Any


def _select_all(widget: tk.Widget) -> None:
    """Select all text in Entry/Text widgets (Windows-friendly)."""
    if isinstance(widget, tk.Entry):
        widget.selection_range(0, tk.END)
        widget.icursor(tk.END)
    elif isinstance(widget, tk.Text):
        widget.tag_add("sel", "1.0", "end-1c")
        widget.mark_set("insert", "end-1c")
        widget.see("insert")



def _select_all(widget: tk.Widget) -> None:
    if isinstance(widget, tk.Entry):
        widget.selection_range(0, "end")
        widget.icursor("end")
    elif isinstance(widget, tk.Text):
        widget.tag_add("sel", "1.0", "end-1c")
        widget.mark_set("insert", "end-1c")
        widget.see("insert")


def _install_context_menu(widget: tk.Widget) -> None:
    """Install a right-click context menu on a widget (idempotent)."""
    if getattr(widget, "_sentinel_ctx_menu_installed", False):
        return

    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Cut", command=lambda w=widget: w.event_generate("<<Cut>>"))
    menu.add_command(label="Copy", command=lambda w=widget: w.event_generate("<<Copy>>"))
    menu.add_command(label="Paste", command=lambda w=widget: w.event_generate("<<Paste>>"))
    menu.add_separator()
    menu.add_command(label="Select All", command=lambda w=widget: _select_all(w))

    def popup(event: Any) -> None:
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    widget.bind("<Button-3>", popup, add=True)  # Windows right-click
    setattr(widget, "_sentinel_ctx_menu_installed", True)


def install(root: tk.Misc) -> None:
    """
    Enable right-click cut/copy/paste/select-all menus for Entry/Text widgets.
    Does not alter keyboard shortcuts.
    """

    def on_focus_in(event: Any) -> None:
        widget = getattr(event, "widget", None)
        if isinstance(widget, (tk.Entry, tk.Text)):
            _install_context_menu(widget)

    # Install lazily when a widget receives focus.
    root.bind_all("<FocusIn>", on_focus_in, add=True)
