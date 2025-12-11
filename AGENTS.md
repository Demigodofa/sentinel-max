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
| - AdaptivePlanner|          | - Symbolic store |        | - Built-in tools |
| - Worker         |          | - Vector search  |        | - Dynamic load   |
| - Autonomy loop  |          +------------------+        +------------------+
| - Reflection v3  |
| - Policy Engine  |
+------------------+
```

## Subsystem Responsibilities
### Controller (`sentinel.controller.SentinelController`)
- Initializes MemoryManager, MemoryContextBuilder, PolicyEngine, and Sandbox.
- Registers default tools (web search, internet extractor, code analyzer, microservice builder, echo generator, browser agent).
- Wires AdaptivePlanner, Worker (policy-aware TopologicalExecutor), ReflectionEngine/Reflector, and AutonomyLoop and routes user input through them.

### Agent Core
- **AdaptivePlanner**: Goal analysis, memory-grounded reasoning (MemoryContextBuilder), tool matching, subgoal generation, DAG construction with sanity checkpoints, plan metadata labeling, deterministic fallback, and persistence to `plans`/`planning_traces`.
- **Worker**: Executes plan steps respecting dependencies, applies PolicyEngine checks per node, runs tools inside the sandbox, and stores execution traces.
- **AutonomyLoop**: Records goals, runs planner→worker→reflection cycles with repeat-plan detection, replanning from reflections, time/failure guards, and memory logging.
- **ReflectionEngine + Reflector**: Multi-dimensional reflections (operational, strategic, self-model, user-preference, plan-critique) with issues, suggestions, plan_adjustment, and confidence; stored under `reflection.*` plus legacy summaries.
- **Sandbox**: Restricts tool execution to safe built-ins.
- **PatchAuditor / Self-Modification / HotReloader**: Guardrails for code-generation workflows (auditing checks for banned tokens and absolute paths).

### Memory
- **MemoryManager**: Unified symbolic/vector facade with semantic search fallback; used for planning, execution, reflection, and policy logging.
- **Memory Intelligence**: `MemoryRanker` (relevance + decay), `MemoryFilter` (noise/dup removal), `MemoryContextBuilder` (context windows). Logs to `memory_contexts` and `memory_rank_reports`.

### Policy
- **PolicyEngine**: Enforces metadata presence, permission allowlist, deterministic-first preferences, parallel limits, artifact collision checks, and unsafe argument detection. Feeds planning, execution, reflection, and autonomy decisions; logs to `policy_events`.

### Tools
- **ToolRegistry**: Thread-safe registry enforcing unique, typed Tool instances with schemas and permissions; dynamic loading supported.
- **Default tools**: deterministic web search, internet extractor, static code analyzer, microservice builder, browser agent, configurable echo tool.
- **Safety**: Sandbox + policy enforcement ensure no execution with missing metadata or unsafe arguments.

### Interfaces
- Single entry point (`main.py`) supports CLI, Tkinter GUI, and FastAPI server modes. All modes delegate to the controller pipeline.

## Planning + Autonomy Flow
1. Goal intake stored in memory under `goals`.
2. AdaptivePlanner derives policy-shaped DAGs with semantic metadata, using memory contexts and tool schemas; validations ensure no cycles or missing inputs.
3. PolicyEngine reviews plans (permissions, determinism, parallelism, artifacts) before execution.
4. Worker executes dependency-ordered batches; policy checks guard each node; outputs/errors persisted to `execution`.
5. ReflectionEngine summarizes execution, detects issues, proposes plan adjustments, and stores reflections.
6. Autonomy loop may replan based on reflections, enforcing cycle/time/failure bounds.
7. Controller responds with latest reflection; trace summary used as fallback.

## Memory Behaviors
- Text inputs stored in both symbolic and vector memories with timestamps and metadata.
- Structured facts stored per-namespace with overwrite controls and atomic persistence.
- Recent recall returns newest records; semantic search ranks by cosine similarity (hash-based fallback when model missing).
- Execution steps, reflections, policy events, and planning traces automatically recorded.
- Context/rank reports stored under `memory_contexts`/`memory_rank_reports`.

## Safety and Policy Rules
- Sandbox restricts Python built-ins; PolicyEngine blocks missing tool metadata, disallowed permissions, unsafe arguments, and excessive parallelism.
- PatchAuditor rejects patches containing banned tokens (e.g., `subprocess`, `rm -rf`) or absolute paths.
- CodeAnalyzerTool flags risky imports/calls and dunder access; returns a safety score and suggestions.

## Tooling and Capabilities
- Deterministic tool execution within a sandbox with limited built-ins.
- Dynamic tool loading by module path plus runtime registration of generated tools.
- Microservice generation with optional live server start and patch auditing.
- Vector-backed web extraction with summary and optional storage for retrieval.
- Static code safety assessment via AST heuristics.

## Data Flow and Invariants
- Tool names are unique; registration rejects duplicates and non-Tool instances. Tool metadata must exist for execution.
- TaskGraph validation prevents cycles/dangling inputs; metadata includes origin goal and reasoning trace when adaptive planner runs.
- PolicyEngine logs policy blocks/rewrites; Memory Intelligence logs contexts/rankings.
- Reflections include issues/suggestions/plan adjustments with confidence scores.

## CHANGELOG
- AdaptivePlanner, PolicyEngine, Memory Intelligence, and ReflectionEngine integrated across controller, planner, worker, and autonomy loop.
- System spec updated to include policy, memory intelligence pipelines, and new namespaces.
