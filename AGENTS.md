# Sentinel MAX — System Specification

This document is the living system specification for Sentinel MAX. It summarizes the current architecture and behaviors based on the implemented code, README, and subsystems.

## High-Level Architecture
```
+---------------------+       +-----------------+       +-----------------+
| User Interfaces     |       | Controller      |       | Logging         |
| - CLI / GUI / API   | <---> | (orchestrator)  | --->  | Structured logs |
+---------------------+       +-----------------+       +-----------------+
           |                              |                          |
           v                              v                          v
+------------------+          +------------------+        +------------------+
| Agent Core       | <------> | Memory           | <----> | Tool Registry    |
| - Planner        |          | - Symbolic store |        | - Built-in tools |
| - Worker         |          | - Vector search  |        | - Dynamic load   |
| - Autonomy loop  |          +------------------+        +------------------+
| - Reflection     |
+------------------+
```

## Subsystem Responsibilities
### Controller (`sentinel.controller.SentinelController`)
- Initializes MemoryManager, ToolRegistry, and Sandbox.
- Registers default tools (web search, internet extractor, code analyzer, microservice builder, echo generator).
- Wires Planner, Worker, Reflector, and AutonomyLoop and routes user input through them.

### Agent Core
- **Planner**: Generates deterministic plan steps from a goal, optionally recording them in memory.
- **Worker**: Executes plan steps sequentially, running tools inside the sandbox and storing execution traces.
- **AutonomyLoop**: Records goals, runs the planner→worker→reflection cycle, and manages timeouts.
- **Reflector**: Summarizes execution traces and persists reflections.
- **Sandbox**: Restricts tool execution to safe built-ins and raises SandboxError on violations.
- **PatchAuditor / Self-Modification / HotReloader**: Guardrails for code-generation workflows (currently stubbed, auditing checks for banned tokens and absolute paths).

### Memory
- **SymbolicMemory**: Thread-safe, namespaced fact store persisted to JSON with atomic writes.
- **VectorMemory**: Semantic store using sentence-transformers when available with deterministic hash fallback.
- **MemoryManager**: Unified facade storing text in both memories, managing facts, recent recall, semantic search, and export of memory state.

### Tools
- **ToolRegistry**: Thread-safe registry enforcing unique, typed Tool instances, dynamic loading, and dispatch.
- **Default tools**: deterministic web search, internet extractor (scrape/clean/summarize with optional vector storage), static code analyzer (AST heuristics), microservice builder (audited FastAPI generator/start helper), and configurable echo tool.
- **Web scraper**: deterministic HTML/text fetcher used by internet extractor.

### Interfaces
- Single entry point (`main.py`) supports CLI, Tkinter GUI, and FastAPI server modes. All modes delegate to the controller or server app.

## Tooling and Capabilities
- Deterministic tool execution within a sandbox with limited built-ins.
- Dynamic tool loading by module path plus runtime registration of generated tools.
- Microservice generation with optional live server start and patch auditing.
- Vector-backed web extraction with summary and optional storage for retrieval.
- Static code safety assessment via AST heuristics.

## Safety Rules
- Sandbox restricts Python built-ins and wraps callable globals before execution.
- PatchAuditor rejects patches containing banned tokens (e.g., `subprocess`, `rm -rf`) or absolute paths.
- CodeAnalyzerTool flags risky imports/calls and dunder access; returns a safety score and suggestions.
- MicroserviceBuilder executes generated code with safe built-ins, audits patches, and optionally stubs FastAPI when unavailable.

## Memory Behaviors
- Text inputs stored in both symbolic and vector memories with timestamps and metadata.
- Structured facts stored per-namespace with overwrite controls and atomic persistence.
- Recent recall returns newest records; semantic search ranks by cosine similarity (hash-based fallback when model missing).
- Execution steps and reflections are automatically recorded with namespaces (`execution`, `reflection`).

## Planning + Autonomy Flow
1. **Goal intake**: User input stored in memory under `goals`.
2. **Plan generation**: Planner derives deterministic steps based on goal keywords and available tools.
3. **Execution**: Worker iterates steps, invoking tools through the sandbox; stops on first failure.
4. **Reflection**: Reflector summarizes the trace and stores the summary in memory.
5. **Response**: Latest reflection content returned to the user; trace summary used as fallback.
6. **Loop control**: Autonomy loop currently runs a single cycle unless extended; optional timeout stops the loop.

## Integration Points
- Controller wires planner/worker/reflector/autonomy to shared MemoryManager, Sandbox, and ToolRegistry.
- MemoryManager used by planner (plan logging), worker (execution logging), reflector (summary storage), and autonomy (goal recording).
- Tools may store artifacts in VectorMemory (internet extractor) and are executed via the sandbox for safety.
- GUI/CLI/server modes delegate to the same controller and therefore share the same core pipeline.

## Current Features Implemented
- Deterministic planner, worker, autonomy loop, and reflection pipeline.
- Memory stack (symbolic + vector) with persistence and semantic search fallback.
- Sandbox-constrained tool execution and patch auditing guardrails.
- Built-in tools: web search, web scraping + extraction with summarization, static code analyzer, microservice builder with audited generation, echo generator.
- Multi-interface launcher (CLI, GUI, FastAPI backend entry points).

## Future Enhancements Planned
- Expand planner to support multi-step adaptive planning and LLM-backed reasoning.
- Extend autonomy loop for iterative planning/feedback cycles and user confirmation gates.
- Broaden toolset (data processing, code execution sandboxes, deployment helpers) with richer metadata and permissions.
- Integrate stronger policy engines and dynamic safety checks (e.g., runtime monitors, rate limits).
- Persist and query reflections/goals across sessions with configurable retention policies.

## CHANGELOG
- Agent Core subsystem implemented.
- Memory subsystem implemented.
- Tools subsystem implemented.

## AUTO-UPDATE POLICY
Codex must update this document whenever:
- A subsystem changes.
- New tools are added.
- Architecture is modified.
- Behaviors are extended.
- APIs or server endpoints change.
