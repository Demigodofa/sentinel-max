# Browser ChatGPT relay

Use the browser relay when you want a ChatGPT tab to drive Sentinel through the GUI without touching the existing CLI/API entry points. The relay watches the ChatGPT transcript for commands wrapped in `<START>` and `<STOP>`, strips the markers, and feeds the text into the GUI input panel exactly as if you had typed it.

## What the relay does

- Starts a Chrome session (via Selenium) at the provided ChatGPT URL and scans assistant messages using the CSS selector `div[data-message-author-role="assistant"]`.
- Looks for one or more `<START> ... <STOP>` blocks inside each assistant message.
- Deduplicates already-forwarded blocks and pushes each new command into the Sentinel GUI input queue so the normal conversation controller handles it.

## Setup

1. Install dependencies (includes Selenium):

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r sentinel/requirements.txt
   ```

2. Ensure Chrome/Chromium and a matching `chromedriver` are on your `PATH`.
3. Sign in to ChatGPT in the profile that the launched browser will use (headless mode expects an existing session).
4. Export your Sentinel LLM environment variables (for example `OPENAI_API_KEY`, `SENTINEL_LLM_MODEL`) before launching the GUI.

## Running the relay + GUI together

Launch both the relay and the Sentinel GUI in one command:

```bash
python scripts/browser_chatgpt_relay.py --chatgpt-url "https://chat.openai.com/" --poll-seconds 1.5
```

Flags you may want:

- `--headless`: run the ChatGPT browser session headlessly (requires an already-authenticated profile).
- `--start-marker` / `--stop-marker`: customize wrappers if you do not want `<START>` and `<STOP>`.
- `--selector`: override the CSS selector for assistant messages if the ChatGPT DOM changes.

Close the GUI window to stop the relay; the runner shuts down the watcher thread and webdriver cleanly.

## Prompt the browser ChatGPT with these rules

Paste this at the top of the ChatGPT thread so it behaves like a disciplined operator for Sentinel:

```
You are operating Sentinel MAX through a GUI that accepts plain text commands. Every time you want Sentinel to act, wrap the exact command in <START> and <STOP> markers on their own lines. Send one wrapped block per turn. Do not add commentary inside the block.

Available commands and tools:
- /auto on | /auto off | /auto until done
- /mechanic (diagnostics)
- /tools (list tools) and /toolhelp <name>
- /tool <name> <json> (execute a tool). Tools include fs_list, fs_read, fs_write, fs_delete, sandbox_exec, web_search, internet_extract, code_analyzer, microservice_builder, browser_agent, and echo.
- Natural language requests ("list files in F:\\Sandbox", "search the web for ...") also work; Sentinel's controller will route them to tools.

Constraints:
- Stay within the F:\ drive sandbox. Avoid paths outside F:\.
- Ask for confirmation before destructive actions unless the user explicitly says autonomy is on.
- Keep commands short and deterministic; avoid speculative wording inside the <START>/<STOP> block.

File layout hints for grounding:
- sentinel/controller.py (controller wiring), sentinel/gui/app.py (Tk GUI), sentinel/watchers/browser_command_relay.py (ChatGPT relay), sentinel/tools/* (tool implementations), sentinel/tests/* (coverage).
```

## Operator workflow

1. Start the relay runner (above). A Chrome window opens to ChatGPT and the Sentinel GUI opens locally.
2. Tell ChatGPT what you want done and share the relay prompt so it emits `<START>...<STOP>` blocks.
3. Each wrapped block is injected into the GUI input panel; you'll see it appear in the transcript as a user message.
4. Monitor the plan, state, and log panels as Sentinel executes. Use `/auto off` or close the GUI to halt.

## Troubleshooting

- If no commands arrive, confirm you see `<START>` and `<STOP>` in the ChatGPT assistant reply and that the CSS selector still matches assistant messages.
- Selenium requires a compatible `chromedriver`; run `chromedriver --version` to confirm.
- Headless mode relies on existing auth cookies. If ChatGPT responds with a login prompt, run without `--headless` and sign in once.
