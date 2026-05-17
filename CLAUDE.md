# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

All development tasks are managed through `uv`. The project uses `hatchling` as the build backend.

```bash
# Install dependencies (including dev extras)
uv sync --all-extras

# Run the CLI
uv run carbonclaw --version
uv run carbonclaw chat --provider ollama --model llama3.2

# Run tests
uv run pytest carbonclaw/tests -v
uv run pytest carbonclaw/tests/unit/test_providers.py -v

# Lint and type check
uv run ruff check carbonclaw
uv run mypy carbonclaw
```

**Tool configuration (from `pyproject.toml`):**
- `ruff`: target Python 3.12, line length 100, lint rules include `E F W I N D UP B C4 SIM ASYNC`
- `mypy`: strict mode, `disallow_untyped_defs = true`
- `pytest`: `asyncio_mode = auto`, tests under `carbonclaw/tests`

## High-Level Architecture

### Unified Provider Abstraction

All LLM providers implement `BaseProvider` (`carbonclaw/core/base.py`) with two methods:
- `complete(request)` — non-streaming
- `stream(request)` — yields `StreamChunk` objects

The key design decision is `StreamChunk` (`carbonclaw/core/models.py`), a normalized chunk format that carries either text content or a `ToolCallChunk` fragment. Providers translate vendor-specific streaming deltas into this format. **OpenRouter and DeepSeek reuse `OpenAIProvider`** instantiated with different base URLs and API keys; they are not separate classes.

### Streaming Tool Call Accumulation

Tool calls arrive fragmented across multiple stream chunks. Both `ReactAgent.stream_run()` and `_run_agent_turn()` in `carbonclaw/cli/chat.py` implement the same accumulator pattern:

1. Track `current_tool` as a dict with `id`, `name`, `arguments` (string).
2. On `tc.is_start`, initialize `current_tool`.
3. On `tc.arguments_delta`, append to the arguments string.
4. On `tc.is_end`, parse the accumulated JSON and emit a `ToolCall`.
5. After the stream ends, handle any dangling `current_tool` by parsing its arguments one final time.

This pattern is duplicated in three places (`ReactAgent.run`, `ReactAgent.stream_run`, `_run_agent_turn`). If you change the tool call parsing logic, you must update all three.

### ReAct Agent Loop

`ReactAgent` (`carbonclaw/agents/base.py`) runs a fixed `max_iterations` loop (default 10). Each iteration:
1. Streams a completion request including prior messages and tool definitions.
2. Accumulates the response into an assistant `Message`.
3. If the message contains `tool_calls`, executes each tool and appends tool result messages.
4. If no tool calls, returns the content.

The loop does not distinguish between "thinking" and "acting" — it is purely message-driven based on whether the model emits tool calls.

### Smart Task Routing

CarbonClaw uses a **SmartRouter** (`carbonclaw/core/router.py`) to dynamically select the best provider and model for each task. The decision is based on:
- **Task Type**: Detected via keyword matching in `carbonclaw/routing/classifier.py` (Coding, Research, Slides, General).
- **Task Complexity**: Heuristic score (0.0 to 1.0) based on prompt length and keywords.
- **Sustainability Strategy**: Prioritizes local models (Ollama) for simple tasks to minimize CO2 emissions.
- **Metrics Tracking**: Learns from provider latency and error rates using Exponential Moving Average (EMA).

### Advanced Agents & Pipelines

- **SupervisorAgent** (`carbonclaw/agents/supervisor.py`): Orchestrates specialized agents. Handles `RESEARCH` by delegating to `ResearchAgent` and `SLIDES` by injecting `PptxGenJS` context.
- **ResearchAgent** (`carbonclaw/agents/research.py`): Implements a **Map-Reduce** pipeline. It searches via DuckDuckGo, fetches pages via Playwright, summarizes each source in parallel (Map), and synthesizes a final report (Reduce).
- **ReactAgent** (`carbonclaw/agents/base.py`): The foundation for all tool-using agents. Uses `repair_json` to handle malformed outputs from smaller local models.

### Specialized Tools

- **RunNodeJSTool** (`carbonclaw/tools/nodejs.py`): Executes Node.js code snippets in a temp directory, supporting dynamic `npm install` and Base64 file returns. Used for PowerPoint generation via `pptxgenjs`.
- **BrowserTool** (`carbonclaw/tools/browser.py`): High-fidelity web interaction using Playwright.
- **WebSearchTool** (`carbonclaw/tools/web_search.py`): DuckDuckGo search integration via `duckduckgo_search`.

### Chat UI Rendering

`carbonclaw/cli/chat.py` uses `StreamingDisplay` (`carbonclaw/ui/streaming.py`) for streaming output. The display wraps `rich.live.Live` with `transient=False`, meaning the panel remains on screen after streaming ends. **Do not call `_print_assistant()` after streaming completes** — this creates a duplicate panel. The `_print_assistant()` helper is only used in `--no-stream` mode.

Tool results are rendered in yellow-bordered panels (red if `is_error`). Dangerous shell commands trigger an interactive `rich.prompt.Confirm` unless `auto_approve_safe_commands` is enabled in config.

### Configuration Resolution

`CarbonClawConfig` (`carbonclaw/config/settings.py`) resolves settings in this order (highest to lowest):
1. Constructor arguments / code overrides
2. Environment variables (`CARBONCLAW_*`, nested with `__`)
3. `pyproject.toml` under `[tool.carbonclaw]`
4. User config at `~/.config/carbonclaw/config.toml`
5. Class defaults

Provider credentials are nested: `CARBONCLAW_OPENAI__API_KEY` maps to `config.openai.api_key`. The `_ProjectSource` and `_UserSource` classes implement the custom TOML resolution.

### Tool Registry and Schema Generation

`ToolRegistry` (`carbonclaw/tools/base.py`) registers `BaseTool` instances. Tool definitions are generated manually via `input_schema` on each tool class, not introspected from Python functions. The registry provides `definitions()` which returns `ToolDefinition` objects normalized to OpenAI-compatible JSON Schema.

Tool execution is always `async`. Results are returned as `ToolResult` with `tool_call_id`, `name`, `content`, and `is_error`.

### Memory Backends

- **SQLiteMemory** (`carbonclaw/memory/sqlite.py`): Async SQLite with namespace support. Default path is `~/.config/carbonclaw/memory.db`. Stores `MemoryEntry` with JSON metadata.
- **ChromaMemory** (`carbonclaw/vector/chroma.py`): Optional ChromaDB for semantic search. Not loaded unless explicitly configured.

### Distributed Runtime

The `distributed/` module provides building blocks for multi-node deployments:
- `StateSerializer` — JSON serialization of agent execution state
- `RPCClient` / `RPCServer` — JSON-RPC 2.0 over HTTP
- `TaskQueue` — priority queue with submit/complete/fail/cancel lifecycle

These are intentionally simple; production multi-node setups are expected to swap in Redis or a message broker.

### Important File Relationships

- `carbonclaw/cli/main.py` imports all command modules at the bottom to register Typer subcommands.
- `carbonclaw/providers/registry.py` maps provider names to classes. Adding a new provider requires updating `_PROVIDER_MAP` and `get_provider_config()` in `CarbonClawConfig`.
- `carbonclaw/agents/supervisor.py` hardcodes agent names (`"planner"`, `"coding"`, `"review"`).
- `carbonclaw/__init__.py` exports `__version__`.
