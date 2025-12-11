# Sentinel MAX — System Specification

## Architecture Overview
- **Entry points**: `main.py` exposes CLI (`run_cli`), GUI (`run_gui`), and FastAPI server (`run_server`). Each mode constructs a `SentinelController` to orchestrate core subsystems.
- **Controller**: `SentinelController` wires `MemoryManager`, `ToolRegistry`, `Sandbox`, `Planner`, `Worker`, `Reflector`, `AutonomyLoop`, `PatchAuditor`, `SelfModificationEngine`, and `HotReloader`. Default tools are registered during initialization.
- **Agent Core**: Planner builds deterministic plans, Worker executes steps via the sandboxed tool registry, AutonomyLoop adds health monitoring and recovery, Reflector summarizes traces to memory, and data classes in `agent_core.base` define plans and execution traces.
- **Memory**: `MemoryManager` persists symbolic records (JSON) and semantic vectors, providing unified recall, search, and fact storage APIs used across planning, execution, and reflection.
- **Tools**: `ToolRegistry` tracks deterministic tools with thread-safe registration and dispatch. Built-in tools include web search, internet extraction, code analysis, microservice generation, browser automation, and deterministic echo generation.
- **Safety**: `Sandbox` limits built-ins during tool execution; `PatchAuditor` and `SelfModificationEngine` safeguard dynamic code paths; `HealthMonitor` evaluates execution quality and recovery strategies inside `AutonomyLoop`.

```mermaid
graph TD
    UserInput[User Input] --> Controller[SentinelController]
    Controller --> Autonomy[AutonomyLoop]
    Autonomy --> Planner
    Planner --> Plan[Plan (PlanStep*)]
    Autonomy --> Worker
    Worker --> Sandbox
    Sandbox --> ToolRegistry
    ToolRegistry -->|execute| Tools[Built-in / Dynamic Tools]
    Worker --> Trace[ExecutionTrace]
    Trace --> Reflector
    Reflector --> Memory[MemoryManager]
    Planner --> Memory
    Worker --> Memory
    Autonomy --> Memory
    Memory --> Export[export_state]
```

## Detailed Subsystems
### Controller (`controller.py`)
- Instantiates `MemoryManager`, shared `ToolRegistry`, and `Sandbox`.
- Registers default tools: web search, internet extractor, code analyzer, microservice builder, echo generator (prefixed), and the pre-registered `BrowserAgent` singleton.
- Builds Planner/Worker/Reflector/AutonomyLoop on shared state and exposes `process_input` which runs the autonomy loop, then returns the latest reflection or execution summary.
- `export_state` surfaces current memory snapshots and registered tool descriptions.

### Agent Core
- **Data Model (`agent_core/base.py`)**: `PlanStep` captures deterministic step metadata; `Plan` groups steps; `ExecutionResult`/`ExecutionTrace` store runtime outcomes with text summaries.
- **Planner (`agent_core/planner.py`)**: Deterministically maps goal keywords to tool-backed steps (code analysis, microservice generation, internet extraction, search, or echo fallback). Records generated plans in memory (`plans` namespace) when available.
- **Worker (`agent_core/worker.py`)**: Iterates plan steps, executing registered tools via `Sandbox.execute` or echoing messages directly. Stores execution outputs/errors to memory (`execution` namespace) and halts on first failure.
- **AutonomyLoop (`agent_core/autonomy.py`)**: Records goals (`goals` namespace), drives the planner→worker cycle with health evaluation per step, optional recovery (continue, retry with backoff, replan, inject reflection), and stops on failures, timeouts, or plan completion. Reflections are injected when scores are low.
- **Health Monitor (`agent_core/health.py`)**: Scores each step for latency, repetition, hallucination signals, and integrates a performance tracker for reflection improvements.
- **Reflector (`agent_core/reflection.py`)**: Summarizes execution traces with timestamps and persists summaries to `reflection` namespace; returns reflection content for controller responses.
- **Sandbox (`agent_core/sandbox.py`)**: Executes callables with restricted `SAFE_BUILTINS` and wraps errors as `SandboxError`.
- **Self-Modification guardrails**: `PatchAuditor`, `SelfModificationEngine`, and `HotReloader` exist to vet and apply code patches with banned-token checks and safe reload hooks.

### Memory Subsystem
- **MemoryManager (`memory/memory_manager.py`)**: Facade combining `SymbolicMemory` (JSON persistence) and `VectorMemory` (semantic search with deterministic hashing fallback). Provides `store_text`, `store_fact`, `query`, `recall_recent`, `semantic_search`, `add` (compatibility), `latest`, and `export_state`.
- **SymbolicMemory**: Namespaced fact store with locking, atomic writes, and timestamp metadata.
- **VectorMemory**: Adds embeddings keyed by namespace; gracefully falls back when models are unavailable.
- All agent core components persist their outputs through `MemoryManager`, ensuring consistent recall for planning, execution, reflection, and health signals.

### Tooling
- **Registry (`tools/registry.py`)**: Thread-safe registry enforcing unique `Tool` instances, dynamic loading (`load_dynamic`), lookup (`get`, `call`, `list_tools`, `has_tool`), and pre-registering `BrowserAgent`.
- **Built-in tools**:
  - `web_search`: deterministic search placeholder for structured results.
  - `internet_extract`: scrapes, cleans, summarizes HTML with optional vector storage.
  - `code_analyzer`: AST-based safety scoring and recommendations.
  - `microservice_builder`: audits generated FastAPI apps with sandboxed execution.
  - `echo` (generated via `generate_echo_tool`): configurable prefix responder.
  - `BrowserAgent`: DOM-only automation with Playwright/CDP hybrid controls.
- All tool execution is funneled through the sandbox via the worker to maintain deterministic, safe behavior.

### Interfaces
- **CLI**: Runs an interactive loop, piping user inputs to `SentinelController.process_input` and printing reflections/summaries.
- **GUI**: Tkinter application launched by `run_gui_app` (not modified here) built on the same controller pipeline.
- **Server**: FastAPI app (`server/main.py`) started via `uvicorn` in `run_server`, exposing API routes backed by the same core components.

## Data Flow and Invariants
1. User input -> Controller -> AutonomyLoop records goal to memory.
2. Planner builds deterministic `PlanStep` sequence based on tool availability; plan stored in `plans` namespace.
3. Worker executes each step through the sandboxed tool registry; results and errors written to `execution` namespace.
4. HealthMonitor scores each step; recovery strategies may replan, retry, or inject reflection.
5. Reflector summarizes `ExecutionTrace` with timestamps, storing reflections for future responses; controller favors latest reflection for replies.
6. MemoryManager maintains synchronized symbolic/vector stores; `export_state` exposes both stores and tool metadata for inspection.

**Invariants and Safety Guarantees**
- Tool names are unique; registration rejects duplicates and non-Tool instances.
- Sandbox restricts exposed built-ins to deterministic primitives; execution errors are wrapped as `SandboxError`.
- Memory writes are namespaced and timestamped; export preserves both symbolic and vector state for replay/debugging.
- Autonomy loop halts on failures, timeouts, or empty plans; recovery paths are deterministic and logged.
- Reflection summaries always include UTC timestamps for traceability.

## Consistency Checks
- **Import + syntax validation**: `python -m compileall sentinel` ensures modules import and compile cleanly.
- **Runtime wire-up**: `SentinelController.process_input` exercises planner, worker, reflector, autonomy, memory, and tool registry end-to-end.
- **Circular dependency expectations**: Subsystems interact through well-defined facades (`ToolRegistry`, `MemoryManager`); no circular imports are present in core modules.

## Diagrams
The Mermaid diagram above reflects the current controller→autonomy→tool→memory flow. Regenerate it whenever component boundaries or data flow change.

## Change Log
- Document regenerated to reflect current controller wiring, agent core flow, memory integration, toolset, safety guards, and interface modes.
