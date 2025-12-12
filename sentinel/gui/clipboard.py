from __future__ import annotations

import tkinter as tk

def _install_context_menu(widget: tk.Widget) -> None:
    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Cut", command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))
    menu.add_separator()
    menu.add_command(label="Select All", command=lambda: widget.event_generate("<<SelectAll>>"))

    def popup(event: tk.Event) -> None:
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    widget.bind("<Button-3>", popup)  # Windows right click
    widget.bind("<Control-Button-1>", popup)  # trackpads / alt-click


def install(root: tk.Misc) -> None:
    """
    Make clipboard shortcuts + right click work everywhere.
    This fixes the "can't copy/paste to or from GUI" deal-breaker.
    """
    # Make sure <<SelectAll>> exists
    root.event_add("<<SelectAll>>", "<Control-a>")

    for cls in ("Entry", "Text"):
        root.bind_class(cls, "<Control-c>", lambda e: e.widget.event_generate("<<Copy>>") or "break")
        root.bind_class(cls, "<Control-x>", lambda e: e.widget.event_generate("<<Cut>>") or "break")
        root.bind_class(cls, "<Control-v>", lambda e: e.widget.event_generate("<<Paste>>") or "break")
        root.bind_class(cls, "<Control-a>", lambda e: e.widget.event_generate("<<SelectAll>>") or "break")

    # Add right-click context menu on focus
    def on_focus_in(event: tk.Event) -> None:
        widget = event.widget
        if isinstance(widget, (tk.Entry, tk.Text)):
            if not getattr(widget, "_sentinel_ctx_menu", False):
                _install_context_menu(widget)
                setattr(widget, "_sentinel_ctx_menu", True)

    root.bind_all("<FocusIn>", on_focus_in, add=True)
