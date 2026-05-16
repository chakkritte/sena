# Sena

Sena is an AI-native runtime and orchestration system for autonomous software engineering, research workflows, tool execution, and multi-agent collaboration.

## Features

- **Multi-Provider LLM Support**: OpenAI, Anthropic, Google Gemini, Ollama, OpenRouter, DeepSeek
- **Streaming Chat**: Real-time responses with markdown rendering and syntax highlighting
- **Tool Execution**: Secure shell commands, file operations, and git introspection
- **Persistent Memory**: SQLite-backed memory with namespaces for sessions and projects
- **Vector Memory**: Semantic search with ChromaDB for code-aware retrieval (optional)
- **ReAct Agents**: Planner, coding, and review agents with tool use
- **Multi-Agent Orchestration**: Supervisor agent that coordinates plan -> code -> review workflows
- **Context Management**: Token budgeting, conversation summarization, and sliding window trimming
- **Docker Sandbox**: Isolated command execution with configurable resource limits
- **Terminal-Native UX**: Rich CLI + full-screen Textual TUI with `!` shell escape shortcut
- **Web Dashboard**: FastAPI-based web UI with SSE streaming
- **Agent Snapshots**: Save and restore agent execution state
- **Worker Pools**: Remote agent worker pools with priority task queue
- **Plugin System**: Dynamic discovery via Python entry points
- **Distributed Runtime**: Agent state serialization, RPC layer, and priority task queue

## Quick Installation

### Prerequisites

- **Python 3.12+**
- **uv** (recommended) or **pip**
- **Git**
- **Ollama** (for local LLMs, optional)
- **Docker** (for sandbox execution, optional)
- **ChromaDB** (for vector memory, optional)

### Install with uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/your-org/sena.git
cd sena

# Create virtual environment and install dependencies
uv sync --all-extras

# Verify installation
uv run sena --version
```

### Install with pip

```bash
# Clone the repository
git clone https://github.com/your-org/sena.git
cd sena

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Verify installation
sena --version
```

### Optional Components

```bash
# Vector memory (ChromaDB)
uv add chromadb

# Web dashboard (FastAPI + uvicorn)
uv add fastapi uvicorn

# Docker sandbox (already in core deps)
# Ensure Docker is running: docker info
```

## Configuration

Sena uses a layered configuration system. Set your provider API keys via environment variables:

```bash
# OpenAI
export SENA_OPENAI__API_KEY="sk-..."

# Anthropic
export SENA_ANTHROPIC__API_KEY="sk-ant-..."

# Google Gemini
export SENA_GEMINI__API_KEY="..."

# OpenRouter
export SENA_OPENROUTER__API_KEY="..."

# DeepSeek
export SENA_DEEPSEEK__API_KEY="..."
```

For local LLMs with Ollama, no API key is required:

```bash
# Ensure Ollama is running
ollama serve

# Pull a model (e.g., llama3.2)
ollama pull llama3.2
```

You can also create a user config file:

```bash
sena config --init
# Edit ~/.config/sena/config.toml
```

Or set config values directly:

```bash
sena config default_provider ollama
sena config default_model llama3.2
```

### Model Context Protocol (MCP)

Sena supports external tools via the Model Context Protocol. You can configure MCP servers in your `config.toml`:

```toml
[mcp_servers.filesystem]
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/search"]

[mcp_servers.postgres]
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"]
```

**Auto-Support for Ollama**: When the default provider is set to `ollama`, Sena automatically attempts to connect to the [ollama-web-tools-mcp](https://github.com/chakkritte/ollama-web-tools-mcp) server if it's available via `npx`.

## Quick Start

```bash
# Interactive chat with tool use
sena chat --provider ollama --model llama3.2
# Inside chat, use !ls to run shell commands

# One-shot task execution
sena run "Refactor auth.py to use async/await" --provider openai

# Generate a step-by-step plan
sena plan "Add OAuth2 authentication support"

# List available models
sena models --provider ollama

# Manage persistent memory
sena memory add "Project uses FastAPI and SQLAlchemy"
sena memory search "database"

# Full-screen TUI chat
sena tui --provider ollama --model llama3.2

# Save and restore agent snapshots
sena snapshot list
sena snapshot restore <id>

# Launch web dashboard
sena web --host 127.0.0.1 --port 8080

# Run a worker pool
sena worker --num-workers 2 --provider ollama

# Check system health and provider connectivity
sena doctor

# Get/set configuration
sena config default_provider
sena config default_model llama3.2
```

## Architecture

```
sena/
├── cli/           # Typer + Rich terminal interface (chat, run, plan, doctor)
├── core/          # Shared Pydantic models, base classes, async event bus
├── context/       # Token budgeting, summarization, sliding window trimming
├── providers/     # LLM adapter layer (OpenAI, Anthropic, Gemini, Ollama, etc.)
├── tools/         # Tool runtime (shell, file, git)
├── memory/        # SQLite-backed persistent memory
├── vector/        # ChromaDB semantic memory (optional)
├── agents/        # ReAct agents + Supervisor orchestration
├── sandbox/       # Docker-based command execution sandbox
├── distributed/   # Serialization, RPC, priority task queue
├── plugins/       # Dynamic plugin discovery via entry points
├── ui/            # Textual full-screen TUI + streaming display
├── web/           # FastAPI web dashboard
├── workers/       # Remote agent worker pools
├── config/        # Layered configuration system
└── tests/         # pytest unit tests
```

## Advanced Usage

### Multi-Agent Workflows

Use the Supervisor to orchestrate plan -> code -> review pipelines:

```python
from sena.agents.supervisor import SupervisorAgent
import asyncio

async def main():
    supervisor = await SupervisorAgent.create_default("openai")
    result = await supervisor.run_workflow(
        "Add pagination to the API endpoints",
        auto_plan=True,
        auto_review=True,
    )
    print(result)

asyncio.run(main())
```

### Context Management

Token budgeting and conversation summarization are handled automatically:

```python
from sena.context.manager import ContextManager, TokenBudget
from sena.providers.registry import ProviderRegistry
from sena.core.models import Message

provider = ProviderRegistry.create("openai")
ctx = ContextManager(
    provider=provider,
    budget=TokenBudget(max_total=128_000, max_completion=4096),
    auto_summarize=True,
)

messages = [Message(role="user", content="...very long conversation...")]
prepared = await ctx.prepare(messages)
status = ctx.budget_status(prepared)
print(f"Tokens used: {status['total_tokens']}, remaining: {status['remaining']}")
```

### Docker Sandbox

Execute commands in isolated containers:

```python
from sena.sandbox.docker import DockerSandbox

sandbox = DockerSandbox(
    image="python:3.12-slim",
    timeout=60,
    memory_limit="512m",
    network_disabled=True,
)

result = await sandbox.execute(
    command="python -c 'print(2+2)'",
    cwd="./my-project",
)
print(result.stdout)  # "4\n"
```

### Vector Memory

Enable semantic search with ChromaDB:

```python
from sena.vector.chroma import ChromaMemory

memory = ChromaMemory(path="./chroma_data")
entry_id = await memory.store(
    "Authentication middleware uses JWT tokens",
    namespace="project-knowledge",
    metadata={"file": "auth.py"},
)
results = await memory.retrieve(
    query="How do we handle login?",
    namespace="project-knowledge",
    limit=5,
)
for r in results:
    print(f"Score: {r.score:.3f} | {r.content}")
```

### Agent Snapshots

Save and restore agent execution state:

```python
from sena.agents.snapshot import AgentSnapshot, ResumableAgent
from sena.core.models import AgentState

snapshot = AgentSnapshot()
state = AgentState(status="running", current_task="Refactor auth")
id = snapshot.save(state, agent_name="coding")

# Later, restore and resume
restored = snapshot.restore_state(id)
agent = ResumableAgent(provider, tools, memory)
result = await agent.resume(id)
```

### Web Dashboard

Launch the FastAPI web dashboard with SSE streaming:

```bash
# Requires fastapi and uvicorn
uv add fastapi uvicorn
sena web --host 127.0.0.1 --port 8080
```

The dashboard provides a chat interface with real-time streaming and task queue management.

### Worker Pools

Run remote agent workers that consume from a task queue:

```python
from sena.workers.pool import WorkerPool, TaskQueue
from sena.distributed.queue import Task

queue = TaskQueue()
pool = WorkerPool(num_workers=2, queue=queue)

await pool.start()

# Submit tasks
task = Task(agent_type="coding", payload={"task": "Refactor utils.py"})
await pool.submit(task)

# Check status
status = await pool.status()
print(status)
```

### Plugins

Create a plugin by implementing `SenaPlugin` and registering it via entry points:

```python
# my_plugin.py
from sena.plugins.base import SenaPlugin
from sena.tools.base import BaseTool

class MyPlugin(SenaPlugin):
    name = "my-plugin"

    def register_tools(self):
        return [MyCustomTool()]

# pyproject.toml
[project.entry-points."sena.plugins"]
my_plugin = "my_plugin:MyPlugin"
```

### Distributed Runtime

The distributed module provides building blocks for multi-node deployments:

- **StateSerializer**: Serialize/deserialize agent execution state
- **RPCClient/RPCServer**: JSON-RPC 2.0 over HTTP for remote agent calls
- **TaskQueue**: Priority task queue with submit/complete/fail/cancel lifecycle

These are designed to be swapped with Redis or a message broker for production multi-node setups.

## Development

```bash
# Run tests
uv run pytest sena/tests -v

# Run a single test file
uv run pytest sena/tests/unit/test_providers.py -v

# Run linter
uv run ruff check sena

# Run type checker
uv run mypy sena
```

## Roadmap

- [x] Multi-provider LLM support with streaming and tool calling
- [x] Tool execution (shell, file, git)
- [x] Persistent SQLite memory
- [x] ReAct agents (planner, coding, review, qa, docs)
- [x] Human-in-the-Loop (HITL) approval gates
- [x] Strict type safety (Mypy clean)
- [x] Context management (token budgeting, summarization, sliding window)
- [x] Vector memory (ChromaDB)
- [x] Docker sandbox
- [x] Multi-agent orchestration (supervisor)
- [x] Plugin system
- [x] Distributed runtime primitives
- [x] Full-screen Textual TUI (`sena tui`)
- [x] Agent state snapshots and resume (`sena snapshot`)
- [x] Web dashboard (`sena web`)
- [x] Remote agent worker pools (`sena worker`)
- [x] Browser automation tool (Playwright)
- [x] OpenTelemetry observability integration
- [x] **Phase 3: Persona Initialization & Self-Evolution** (`sena init`)
- [ ] **Phase 4: Event-Driven CI/CD Workflows** (GitHub/GitLab webhooks)
- [ ] **Phase 5: Advanced Graph Memory** (Knowledge Graph using NetworkX/Neo4j)
- [ ] **Phase 6: IDE Integration** (Language Server Protocol - LSP)
- [ ] **Phase 7: Multi-Modal Capabilities** (Vision & Voice support)

## License

MIT
