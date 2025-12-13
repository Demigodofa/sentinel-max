# Sentinel MAX Repo Map

This report summarizes runtime wiring, duplicate implementations, and risks based on the requested diagnostics.

## Boot flow (actual call chain)
- **CLI**: `sentinel.main:main()` dispatches `--mode cli` to `run_cli()`, which instantiates `SentinelController` and routes every user input through `controller.process_input()` → `conversation_controller.handle_input()` → `DialogManager` / `IntentEngine` / `NLToTaskGraph` → `AdaptivePlanner` → `Worker` / `ExecutionController` → `AutonomyLoop` and reflection stack.【F:sentinel/main.py†L22-L68】【F:sentinel/controller.py†L34-L114】
- **GUI**: `run_gui_app()` builds the Tkinter shell, wires user input through `ControllerBridge`, and streams `SentinelController.process_input()` responses (agent text, plan updates, and logs) back into the widgets on the UI thread.【F:sentinel/gui/app.py†L11-L93】【F:sentinel/gui/controller_bridge.py†L10-L82】
- **Server**: `sentinel.main --mode server` starts Uvicorn against `sentinel.server.main:app`; FastAPI handlers (not detailed here) would need to instantiate `SentinelController` similarly to the CLI path.【F:sentinel/main.py†L38-L63】

## Single source of truth (duplicate detection)
- **DialogManager**: There are three implementations:
  - `sentinel/conversation/dialog_manager.py` (stateful, memory-backed, used by `SentinelController` via `sentinel.conversation`).【F:sentinel/conversation/dialog_manager.py†L15-L111】
  - `sentinel/dialog/dialog_manager.py` (LLM formatter for project status; unused by `SentinelController`).【F:sentinel/dialog/dialog_manager.py†L6-L82】
  - `sentinel/dialog_manager.py` (compatibility wrapper; also unused by `SentinelController`).【F:sentinel/dialog_manager.py†L1-L36】
  - **Used path**: `SentinelController` imports `DialogManager` from `sentinel.conversation`, so the other two are effectively dead code.【F:sentinel/controller.py†L12-L53】
- **ConversationController**: Single implementation at `sentinel/conversation/conversation_controller.py` orchestrates intent classification, planning, execution, and autonomy gating; this is the instance wired into `SentinelController`.【F:sentinel/controller.py†L65-L94】【F:sentinel/conversation/conversation_controller.py†L20-L71】
- **AutonomyLoop**: Sole implementation at `sentinel/agent_core/autonomy.py`, injected into `SentinelController` and reused by `ConversationController` for `/auto` execution and multi-cycle runs.【F:sentinel/agent_core/autonomy.py†L16-L86】【F:sentinel/controller.py†L45-L80】

## Tool lifecycle
- **Registration**: `SentinelController._register_default_tools()` loads filesystem, sandbox exec, web search, internet extractor, code analyzer, microservice builder, and echo tool into `DEFAULT_TOOL_REGISTRY`.【F:sentinel/controller.py†L96-L116】
- **Global singleton**: `DEFAULT_TOOL_REGISTRY` is constructed and immediately registers `BrowserAgent()` at import time, so importing `sentinel.tools.registry` mutates global state before controllers are instantiated.【F:sentinel/tools/registry.py†L56-L74】
- **Import side effects / missing deps**: Importing the tool package fails without `requests` because `sentinel.tools.web_search` is imported eagerly by `sentinel.tools.__init__`; this prevents `sentinel.main` and `SentinelController` from loading until the dependency is installed.【F:sentinel/tools/__init__.py†L1-L9】【ce5401†L1-L16】
- **Listing tools**: CLI `/tools` routes through `SentinelController._handle_cli_command`, while conversation `/tools` walks the planner’s registry; both rely on the shared registry populated above.【F:sentinel/controller.py†L118-L153】【F:sentinel/conversation/conversation_controller.py†L272-L316】
- **/tools behavior**: The conversation handler formats registry contents but does not execute anything; `/tools` is distinct from `/auto`, which consumes pending plans or goals.

## Autonomy gating model
- **Intent classification**: `classify_intent` maps `/auto` or autonomy keywords to `AUTONOMY_TRIGGER`; task-like prefixes become `TASK`; everything else is `CONVERSATION`, which yields generic acknowledgements like “Got it — I’ve noted that.”【F:sentinel/conversation/intent.py†L4-L33】【F:sentinel/conversation/dialog_manager.py†L70-L107】
- **Slash commands**: `/auto` has multiple modes—execute pending plan, toggle auto mode, or one-shot plan+execute; `/run` executes pending plans; `/cancel` clears queued work; `/tools` lists registry contents.【F:sentinel/conversation/conversation_controller.py†L270-L355】
- **Autonomy loop usage**: When `Intent.AUTONOMY_TRIGGER` arrives and a pending goal/plan exists, `ConversationController` calls `_execute_with_goal`/`_execute_pending_plan`, which translate goals to `TaskGraph` via `NLToTaskGraph`, then run through planner→worker→execution controller→reflector inside the injected `AutonomyLoop`.【F:sentinel/conversation/conversation_controller.py†L143-L242】
- **GUI behavior**: GUI input flows through `ConversationController` and the same autonomy/tool pipeline as CLI/server via `ControllerBridge`, so plan execution, tool calls, and reflections are available in GUI mode.

## Risk list / weirdness
- **Import-time side effects**: `DEFAULT_TOOL_REGISTRY` registers a `BrowserAgent` during module import; loading `sentinel.tools` also imports `requests` and attempts web-tool setup before configuration or dependency checks.【F:sentinel/tools/registry.py†L56-L74】【ce5401†L1-L16】
- **Global singletons**: Shared `DEFAULT_TOOL_REGISTRY` and singleton `MemoryManager` usage in `SentinelController` mean state leaks across GUI/CLI/server instances if multiple controllers are created in one process.
- **Missing dependencies**: `requests` is not installed, causing import failures for `sentinel.main`/`controller` and the tool registry script; this explains “works in CLI but not GUI” style issues in environments lacking optional deps.【a527aa†L1-L17】【a82d42†L8-L14】
*** (entry removed: GUI now routes through `ControllerBridge` and the shared controller pipeline)***

## Actionable recommendations
1. Consolidate dialog managers into the `sentinel/conversation` version and delete/alias the two unused variants to avoid confusion.
2. Move `DEFAULT_TOOL_REGISTRY` population into `SentinelController._register_default_tools()` (or a dedicated bootstrap) and avoid registration during module import to reduce side effects and GUI/CLI divergence.
3. Keep GUI aligned with CLI/server by ensuring any new conversation commands or autonomy modes are surfaced through `ControllerBridge` callbacks and covered by GUI tests.
4. Add dependency checks or optional imports for `requests` (and other web tools) to prevent import-time crashes when the package is missing.

## Repo map table
| File | Purpose | Called by | Calls into | Used? |
| --- | --- | --- | --- | --- |
| `sentinel/main.py` | Unified entrypoint dispatching CLI/GUI/Server modes | CLI users / `python -m sentinel.main` | `SentinelController`, `run_gui_app`, `uvicorn` | Yes |
| `sentinel/controller.py` | System orchestrator wiring memory, tools, planner, worker, autonomy, conversation | CLI, ControllerBridge (intended GUI/server) | `ConversationController`, `AdaptivePlanner`, `Worker`, `AutonomyLoop`, tool registration | Yes |
| `sentinel/conversation/conversation_controller.py` | Text→intent→plan→execute pipeline with `/auto`/`/tools` support | `SentinelController` | `DialogManager`, `IntentEngine`, `NLToTaskGraph`, `AutonomyLoop`, `MultiAgentEngine` | Yes |
| `sentinel/conversation/dialog_manager.py` | Stateful dialog manager using LLM and memory | `SentinelController` → `ConversationController` | `LLMClient`, `MemoryManager`, `WorldModel` | Yes |
| `sentinel/dialog/dialog_manager.py` | Project-status formatter with LLM fallbacks | (Not referenced by `SentinelController`) | `LLMClient` | No |
| `sentinel/dialog_manager.py` | Compatibility wrapper storing dialog turns | (Not referenced by `SentinelController`) | `MemoryManager`, `WorldModel` | No |
| `sentinel/agent_core/autonomy.py` | Reflection-driven autonomy executor | `SentinelController`, `ConversationController` | `AdaptivePlanner`, `Worker`, `ExecutionController`, `Reflector` | Yes |
| `sentinel/tools/registry.py` | Tool registry + global `DEFAULT_TOOL_REGISTRY` | Imported by many modules at import time | Registers `BrowserAgent`; validates tools | Yes (global) |
| `sentinel/gui/app.py` | Tkinter UI shell | End-users (GUI mode) | Wires widgets to `ControllerBridge` for streamed controller responses | Yes |
| `sentinel/gui/controller_bridge.py` | Threaded adapter around `SentinelController` for GUI widgets | GUI | `SentinelController.process_input`, memory readers | Yes |
| `sentinel/llm/client.py` | Minimal OpenAI/Ollama-compatible client | Dialog managers, planners | Env-driven HTTP chat | Yes |

## One-liner Codex prompt
“Generate a repo map + runtime map for SentinelMAX. Run the PowerShell commands to inventory modules, grep for duplicates, trace entrypoints, list registered tools, and confirm LLM backend wiring. Produce docs/repo_map.md with boot flows (CLI/GUI/server), single-source-of-truth modules, tool lifecycle, autonomy gating triggers, and a risk list (import-time side effects, globals). Include concrete recommendations and identify duplicate dialog managers/controllers/autonomy loops and which are actually wired.”
