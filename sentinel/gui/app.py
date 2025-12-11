"""Tkinter GUI bootstrap for Sentinel MAX."""
from __future__ import annotations

try:
    import tkinter as tk
except Exception:  # pragma: no cover - optional dependency
    tk = None  # type: ignore

from sentinel.controller import SentinelController


def run_gui_app() -> None:
    """Launch a minimal Tkinter chat window if Tk is available."""

    if tk is None:
        print("Tkinter is not available in this environment.")
        return

    controller = SentinelController()

    root = tk.Tk()
    root.title("Sentinel MAX")

    text_area = tk.Text(root, height=20, width=60)
    text_area.pack()

    entry = tk.Entry(root, width=50)
    entry.pack()

    def send_message(event=None):
        message = entry.get()
        entry.delete(0, tk.END)
        response = controller.process_input(message)
        text_area.insert(tk.END, f"You: {message}\nAgent: {response}\n\n")

    send_button = tk.Button(root, text="Send", command=send_message)
    send_button.pack()
    entry.bind("<Return>", send_message)

    root.mainloop()
