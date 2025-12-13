# Sentinel MAX GUI quick start and smoke checks

## Launching the GUI
Run the GUI entrypoint from the repo root:

```bash
python -m sentinel.main --mode gui
```

The window opens with a high-contrast input field, a "Send" button, and the log/output panes. The input text box uses the updated background and border colors for legibility.

## Clipboard support
The input field supports both keyboard shortcuts and a right-click context menu:

- **Keyboard:** `Ctrl+C`/`Cmd+C`, `Ctrl+V`/`Cmd+V`, and `Ctrl+X`/`Cmd+X` map to copy, paste, and cut.
- **Mouse:** right-click the input box and choose **Cut**, **Copy**, or **Paste**.

## Basic manual test flow
1. Start the GUI (command above).
2. Click the input field, type some text, and verify the caret and text are readable against the background.
3. Use copy/paste via both keyboard and the context menu to confirm clipboard behavior.
4. Press **Enter** or click **Send** to submit; the field should clear and retain focus for the next entry.

> **Note:** The container environment used for automated tasks is headless, so GUI screenshots are not available here. The steps above reproduce the experience on a local machine with a display.
