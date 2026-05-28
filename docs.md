# CarbonClaw Documentation

Detailed guide for architecture, advanced usage, and configuration.

## Table of Contents
1. [Architecture](#architecture)
2. [Advanced Usage](#advanced-usage)
3. [Model Context Protocol (MCP)](#model-context-protocol-mcp)
4. [Docker Sandbox](#docker-sandbox)
5. [Vector Memory](#vector-memory)
6. [Agent Snapshots](#agent-snapshots)
7. [Worker Pools](#worker-pools)
8. [Distributed Runtime](#distributed-runtime)
9. [Plugin System](#plugin-system)
10. [Core Sustainability & Autonomic Features](#core-sustainability--autonomic-features)
    - [Carbon-Aware Scheduling](#carbon-aware-scheduling)
    - [Carbon Budgeting & Limits](#carbon-budgeting--limits)
    - [VS Code / IDE Extension Integration](#vs-code--ide-extension-integration)
    - [ESG & Sustainability Dashboard](#esg--sustainability-dashboard)
    - [Automated Benchmark Dashboard](#automated-benchmark-dashboard)
    - [GitHub Webhook Healer CI](#github-webhook-healer-ci)
    - [Agent Template Marketplace](#agent-template-marketplace)
    - [Prompt Efficiency Optimizer](#prompt-efficiency-optimizer)
    - [Collaborative Agent Sessions](#collaborative-agent-sessions)
    - [Telemetry Session Playback](#telemetry-session-playback)
    - [AST-Based Self-Documenting Code](#ast-based-self-documenting-code)
    - [AST & Git-Aware Refactoring Risk Analysis](#ast--git-aware-refactoring-risk-analysis)
11. [Advanced Roadmap Features](#advanced-roadmap-features)
    - [CI/CD Healer Daemon](#cicd-healer-daemon)
    - [Playwright Visual Regression Testing](#playwright-visual-regression-testing)
    - [Swarm Debate Console TUI](#swarm-debate-console-tui)
    - [Local Model Fine-Tuning Export](#local-model-fine-tuning-export)

---

## Architecture

CarbonClaw is built with a modular, async-first architecture:

```
carbonclaw/
├── cli/           # Typer + Rich terminal interface (chat, run, plan, doctor)
├── core/          # Shared Pydantic models, base classes, async event bus
├── context/       # Token budgeting, summarization, sliding window trimming
├── providers/     # LLM adapter layer (OpenAI, Anthropic, Gemini, Ollama, etc.)
├── tools/         # Tool runtime (shell, file, git, browser)
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

---

## Advanced Usage

### Multi-Agent Workflows

Use the Supervisor to orchestrate complex pipelines:

```python
from carbonclaw.agents.supervisor import SupervisorAgent
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

Token budgeting and conversation summarization are handled automatically by the `ContextManager`.

---

## Model Context Protocol (MCP)

CarbonClaw supports external tools via MCP. Configure them in your `config.toml`:

```toml
[mcp_servers.filesystem]
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/search"]
```

**Ollama Support**: When using the `ollama` provider, CarbonClaw automatically connects to the [ollama-web-tools-mcp](https://github.com/chakkritte/ollama-web-tools-mcp) server if found.

---

## Docker Sandbox

Execute commands in isolated containers for security:

```python
from carbonclaw.sandbox.docker import DockerSandbox

sandbox = DockerSandbox(
    image="python:3.12-slim",
    timeout=60,
    memory_limit="512m",
)

result = await sandbox.execute(command="python -c 'print(2+2)'")
```

---

## Vector Memory

Enable semantic search with ChromaDB:

```python
from carbonclaw.vector.chroma import ChromaMemory

memory = ChromaMemory(path="./chroma_data")
await memory.store("JWT tokens are used for auth", namespace="docs")
results = await memory.retrieve(query="How to auth?", namespace="docs")
```

---

## Agent Snapshots

Save and restore execution state:

```python
from carbonclaw.agents.snapshot import AgentSnapshot
snapshot = AgentSnapshot()
id = snapshot.save(state, agent_name="coding")
```

---

## Worker Pools

Scale CarbonClaw using remote workers and a priority task queue.

---

## Distributed Runtime

Provides building blocks for multi-node deployments:
- **StateSerializer**: State persistence.
- **RPC Layer**: Remote agent calls.
- **TaskQueue**: Priority-based scheduling.

---

## Plugin System

CarbonClaw features a robust, stabilized dynamic plugin ecosystem enabling users to publish, share, and seamlessly load custom tools, providers, commands, and event handlers.

### Creating a Plugin

To define a plugin, inherit from `CarbonClawPlugin` (from `carbonclaw.plugins.base`) and implement the registration hooks:

```python
from carbonclaw.plugins.base import CarbonClawPlugin
from carbonclaw.core.base import BaseTool, BaseProvider
from typing import Any, Callable

class MyCustomPlugin(CarbonClawPlugin):
    name = "carbonclaw-tool-aws"
    version = "0.1.0"

    def activate(self) -> None:
        """Executed during startup when the plugin is loaded."""
        pass

    def deactivate(self) -> None:
        """Executed when the plugin is unloaded."""
        pass

    def register_tools(self) -> list[BaseTool]:
        """Return custom tools to inject into the global ToolRegistry."""
        return [MyAwsTool()]

    def register_providers(self) -> dict[str, type[BaseProvider]]:
        """Return custom LLM providers to inject into the ProviderRegistry."""
        return {"aws-bedrock": BedrockProvider}

    def register_commands(self) -> dict[str, Callable[..., Any]]:
        """Return CLI commands to dynamically attach to the Typer app."""
        return {"aws-deploy": deploy_command}

    def register_hooks(self) -> dict[str, Callable[..., Any]]:
        """Return event hooks to dynamically subscribe to the EventBus."""
        return {"agent.complete": log_completion_hook}
```

### Registration via Entry Points

Register your plugin package under the `carbonclaw.plugins` entry point group in `pyproject.toml`:

```toml
[project.entry-points."carbonclaw.plugins"]
aws = "carbonclaw_tool_aws.plugin:MyCustomPlugin"
```

Once installed, CarbonClaw automatically discovers the plugin and integrates its contributions into the runtime without requiring any changes to the core codebase.

---

## Core Sustainability & Autonomic Features

### Carbon-Aware Scheduling

CarbonClaw features an intelligent scheduling engine that delays carbon-intensive cloud workloads to wind and solar peak periods when local grid carbon intensity is lowest.

- **Store**: Uses a persistent Scheduler database (`SchedulerStore`) at `~/.config/carbonclaw/scheduled_tasks.jsonl`.
- **Estimation**: Autonomously determines projected CO₂ emissions and potential savings depending on task categorization (e.g. `research` gets a higher simulated electricity footprint than a brief `plan`).
- **CLI Commands**:
  - `carbonclaw schedule-add "Command"`: Queues a task for execution during optimal green-energy hours.
  - `carbonclaw schedule-list`: Renders the table of queued, active, or completed scheduling sessions.
  - `carbonclaw schedule-daemon`: Launches a persistent polling runner that executes due tasks when clean energy thresholds are reached.
- **Slash Commands**:
  - `/schedule <task_command>`: Queues a scheduled task from within the interactive CLI chat interface.
  - `/schedule list`: Displays the scheduled task queue dynamically.
  - `/schedule now! <task_id>`: Forces immediate execution, bypassing scheduling optimization.

### Carbon Budgeting & Limits

Enforce compliance with strict organizational or session carbon ceilings to limit runtime emissions.
- **Configuration**: Settings map directly to standard configuration fields (`carbon_budget`).
- **Ceiling Enforcement**: When a session exceeds its configured `--carbon-budget` threshold, further execution is suspended, preventing budget overrun.
- **CLI Flag**: Specify `--carbon-budget <grams>` during `carbonclaw run` to set a custom ceiling.

### VS Code / IDE Extension Integration

Connects editors directly to the sustainability intelligence backend to supply visual awareness and security gates.
- **Inline Sustainability Badge**: REST endpoint at `/api/extension/badge` accepts code snippets and calculates execution footprints and active grid status.
  - Returns raw metrics (e.g. estimated carbon grams, grid carbon intensity).
  - Emits color-coded visual indicator statuses (`🌱 Clean Grid` in green, `🟡 Moderate` in yellow, `🔴 Peak Fossil` in red).
- **Dangerous Action Gate**: REST endpoint at `/api/extension/approve` implements a remote approval request hook.
  - Executes deep **Impact Analysis** on shell command arguments.
  - Rejects dangerous commands (like `rm -rf` or file deletions) unless explicitly overridden, protecting environments from unauthorized modifications.

### ESG & Sustainability Dashboard

A modern, highly visual FastAPI-powered dashboard that aggregates organization-wide or developer telemetry.
- **Dashboard UI**: Rendered at `/esg/dashboard`, styled using Outfit typography and a premium dark-mode theme featuring:
  - Total aggregated carbon emissions tracking.
  - Forestry offsets and partner information (calculating exact equivalent trees planted and Wh clean energy restored).
  - A real-time **Model Efficiency Leaderboard** displaying the Carbon-to-Utility Ratio of open-source and commercial models.
  - Dynamic breakdowns of emissions grouped by individual project workspaces.
- **API Endpoint**: `/api/esg/stats` exposes raw structured data containing emission summaries, grid coefficients, offsets, and leaderboard stats.

### Automated Benchmark Dashboard

An advanced, real-telemetry-driven dashboard comparing the sustainability of different open-source and commercial models based on CarbonClaw's anonymous token and energy telemetry records.
- **Benchmark UI**: Rendered at `/esg/benchmark`, structured as a beautiful, interactive page with glassmorphism stats cards, visual CSS horizontal bar graphs, and dynamic ranking details.
- **Carbon-to-Utility Score**: Displays the dynamic efficiency ratio of models:
  $$\text{Efficiency Score} = \frac{\text{Model Utility Score (\%)}}{\text{CO}_2\text{ Emissions per 1000 Tokens (grams)}}$$
- **API Endpoint**: `/api/esg/benchmark` calculates the leaderboard in real-time by reading usage records from `TelemetryStore` (`telemetry.jsonl`) and applying dynamic calculations for active models while maintaining baselines for comparison.

### GitHub Webhook Healer CI

FastAPI webhook handler at `/webhooks/github` that listens for repository workflow failures.
- **Autonomic Healing**: Captures failing runs and immediately spins up an asynchronous background task.
- **HealerAgent Integration**: Invokes the `HealerAgent` in the background to automatically identify test or compile-time failures, formulate a fix, verify it, and stage the correction.

### Agent Template Marketplace

Enables sharing and pulling specialized agent configurations tailored to specific workflows.
- **Format**: Declarative TOML formats defining persona parameters (`routing_strategy`, `default_provider`, `system_prompt`, `tools`).
- **CLI Commands**:
  - `carbonclaw template-list`: Lists all installed agent templates.
  - `carbonclaw template-pull <name>`: Pulls a preset (such as `sustainability-swarm`) from the repository workspace.
  - `carbonclaw template-publish <name>`: Registers custom configuration presets.

### Prompt Efficiency Optimizer

A high-performance context compactor that optimizes raw prompts prior to dispatching them to LLM providers.
- **Compression**: Employs regex passes to filter verbose greetings, polite fillers (e.g. `Could you kindly`, `please`), and strips redundant consecutive spacing or linebreaks.
- **Savings Telemetry**: Tracks token reductions and logs exact compaction stats to improve speed, lower cost, and reduce grid footprint.

### Collaborative Agent Sessions

Enables multi-agent workspaces to operate concurrently over a shared SQLite registry.
- **Shared Caps**: Multi-agent sessions track combined carbon thresholds dynamically.
- **Resource Lock Management**: Implements concurrency primitives (`acquire_lock` and `release_lock`) so agents do not overwrite or modify identical files or assets simultaneously.

### Telemetry Session Playback

A step-by-step terminal replay debugger to audit and inspect historic agent sessions.
- **Traces**: Logs execution records (`thought`, `tools_called`, `tool_results`, `duration_secs`, `carbon_emissions_kg`) to `~/.config/carbonclaw/session_traces.jsonl`.
- **Replay CLI**:
  - `carbonclaw playback <session_id>`: Iterates sequentially through recorded steps with formatted Rich panels.
  - `carbonclaw playback-list`: Tables all session tracking logs.

### AST-Based Self-Documenting Code

The `/doc-sync` system keeps code documentation perfectly current with codebase updates.
- **AST Parsing**: Dynamically audits Python modules to identify classes, methods, or functions lacking docstrings.
- **Docstring Injection**: Invokes DocsAgent to generate premium PEP-257 docstrings and injects them precisely at the AST source target location, preserving leading indentation.
- **Git Sync**: Integrates with Git status to scan and document only newly added or modified files.

### AST & Git-Aware Refactoring Risk Analysis

Predict codebase refactoring risk and downstream blast radius prior to modifying code using a blended heuristic of Git churn and AST parsing.

- **Risk Score Heuristics**: Combines Git modification frequency, author density, net line churn, and AST structure complexity:
  $$\text{Base Risk} = (\text{Commits} \times 1.2) + (\text{Authors} \times 2.5) + (\text{Net Churn} \times 0.02)$$
  $$\text{Complexity Factor} = 1 + \left(\frac{\text{Classes} + \text{Functions}}{10.0}\right)$$
  $$\text{Risk Score} = \min(100.0, \text{Base Risk} \times \text{Complexity Factor})$$
- **CLI Commands**:
  - `carbonclaw risk <filepath>`: Runs full diagnostic risk profiling for a specific Python file, outputting rich tables and indicator levels:
    - `[green]LOW RISK[/green]` (Score < 30)
    - `[yellow]MODERATE RISK[/yellow]` (Score 30 to 60)
    - `[red]HIGH RISK[/red]` (Score > 60)
- **Slash Commands**:
  - `/risk <filepath>`: Executes and displays AST refactoring risk assessment from within the interactive TUI or CLI chat sessions.

---

## Advanced Roadmap Features

### CI/CD Healer Daemon

A background daemon that monitors files for immediate, proactive linting and testing corrections.
- **Usage**: `carbonclaw healer-daemon <path> --command "uv run ruff check"`
- **Execution Flow**: Watches a directory for Python changes. On save, executes the diagnostic command. If it yields an error, launches the `HealerAgent` to instantly fix and verify the file, providing a continuous autonomic self-healing loop.

### Playwright Visual Regression Testing

A Visual Verification Tool allowing agents to execute visual regression checks using headless chromium screenshots.
- **Visual Regression Tool**: `visual_regression_test`
- **Arguments**: `url`, `baseline_path`, `candidate_path`, `threshold`
- **Comparison Engine**: Captures screenshots using Playwright, measures pixel divergence using Pillow's Root-Mean-Square (RMS) error difference, and automatically establishes baselines when absent.

### Swarm Debate Console TUI

An interactive debate interface that elevates supervisor capabilities via collaborative swarm reasoning.
- **Execution Flow**: Orchestrates debate iterations between specialized agents (Planner, Coding, Review, QA) to refine drafts.
- **Human-in-the-Loop Interjections**: Outputs real-time progress using Rich formatting panels and pauses for human feedback options:
  - `(a)pprove`: Accepts the current consensus.
  - `(i)nterject`: Inputs custom human direction into the agent conversation log.
  - `(r)eject`: Rejects and instructs the swarm to restart the iteration.

### Local Model Fine-Tuning Export

A powerful pipeline allowing you to package your successful agent session runs, thoughts, tool calls, and self-healing fixes directly into a format ready for LoRA fine-tuning.

- **Usage**: `carbonclaw export-tuning --output lora_dataset.jsonl --format sharegpt`
- **Output Formats**:
  - `sharegpt`: Multi-turn conversational format pairing system prompt, human request, GPT agent thoughts/actions, and tool responses sequential lists.
  - `chatml`: Industry standard messages list dictionary format.
  - `alpaca`: Instruction, input, and outputs text aggregations.
- **Filtering Options**: Filter session exports by minimum execution steps using `--min-steps <count>`.

