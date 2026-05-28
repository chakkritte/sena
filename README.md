# CarbonClaw 🤖

[![License: MIT](https://img.shields.io/badge/License-MIT-c4715a.svg)](https://opensource.org/licenses/MIT) [![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python)](https://www.python.org) [![GitHub Repo Size](https://img.shields.io/github/repo-size/chakkritte/carbonclaw?color=c4715a)](https://github.com/chakkritte/carbonclaw) [![GitHub Issues](https://img.shields.io/github/issues/chakkritte/carbonclaw?color=c4715a)](https://github.com/chakkritte/carbonclaw/issues)

<p align="center">
  <img src="images/carbonclaw-logo.png" alt="CarbonClaw Logo" width="250"/>
</p>

CarbonClaw is a **Sustainability-Focused, Local-First, and Privacy-First** AI agent runtime for autonomous software engineering and self-evolving workflows.

![CarbonClaw Demo](images/carbonclaw.png)

## 🚀 One-Line Installation

### Linux / macOS (Bash)
```bash
curl -fsSL https://raw.githubusercontent.com/chakkritte/carbonclaw/main/install.sh | bash
```

### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/chakkritte/carbonclaw/main/install.ps1 | iex
```
*Requires Python 3.12+ and Git (uv will be auto-installed if missing).*

## 🌟 Key Features

- **Self-Healing CI**: Autonomous daemon mode (`/heal`) that watches for test failures and automatically creates and verifies fixes.
- **Knowledge Graph Memory**: AST-based code parsing for deep structural awareness and blast-radius analysis.
- **Model Distillation**: Background benchmarking pipeline ("shadow trials") that autonomously discovers the most carbon-efficient models for your specific tasks.
- **Visual Architecture**: Vision model integration (`VisionTool`) for architecture diagram verification and UI mockup analysis.
- **Multi-Agent Orchestration**: Automated plan -> code -> test -> review -> docs workflows.
- **Swarm Debate Mode**: Multi-agent collaboration where specialized agents debate and iterate on solutions for higher quality.
- **Hybrid Memory**: Fused keyword (SQLite) and semantic (ChromaDB) search for superior context recall.
- **Parallel Tool Execution**: Async turn-level concurrency for faster execution of complex tasks.
- **Strategic Evolution**: Agents learn from interactions and autonomously improve their routing strategies.
- **Claude Code-Style Chat**: Interactive chat with multi-line input, draft preservation, and persistent chat renderer.
- **Browser Automation**: Full web interaction and scraping via Playwright.
- **Strictly Typed**: 100% Mypy compliance for enterprise reliability.
- **Observability**: Built-in OpenTelemetry tracing for monitoring execution paths and token costs.
- **Sustainability**: Real-time carbon emission tracking via `codecarbon`, active per-session or per-task **Carbon Budgeting** (`--carbon-budget`) to enforce limits, and proactive recommendations for local/greener models on simple tasks.
- **Carbon-Aware Scheduling**: Intelligently delay resource-heavy cloud tasks to run during solar or wind grid peaks, yielding projected CO₂ savings (supported via `carbonclaw schedule-*` and `/schedule` slash commands).
- **Advanced Research**: Multi-step Map-Reduce research pipeline for deep web analysis and comprehensive report generation.
- **Slide Generation**: Automated PowerPoint generation via `PptxGenJS` integration and specialized slide agents.
- **Smart Routing**: Autonomous model selection based on task type (Coding, Research, Slides) and complexity (inspired by OpenClaude).
- **Agent Overrides**: Pin specific agents (Planner, Coding, Review) to different models/providers for maximum efficiency.
- **Privacy First**: Built-in `/audit` command to scan conversation history for potential data leaks.
- **Advanced Web**: `/fetch` command for JS-rendered web scraping using a full browser engine.
- **Headless Mode**: Robust FastAPI server for remote agent execution and integration into other apps.
- **Human-in-the-Loop**: Mandatory approval gates for sensitive system operations, with colored diff previews and session-based **Auto-Accept**.

## 🛠 Quick Start

```bash
# Run the interactive setup wizard (Configure providers, keys, and persona)
carbonclaw setup

# Start an interactive chat
carbonclaw chat

# Run a one-shot engineering task
carbonclaw run "Refactor carbonclaw/core/base.py to use Protocol instead of ABC"
```

### 🧰 CLI Subcommands Reference

CarbonClaw comes equipped with highly specialized CLI utilities for local automation, telemetry, and daemon execution:

| Command | Category | Description |
| :--- | :--- | :--- |
| `carbonclaw chat` | Interaction | Start a persistent, contextual engineering conversation with slash commands. |
| `carbonclaw run "..."` | Execution | Execute a one-shot task autonomously. Supports `--carbon-budget`. |
| `carbonclaw setup` / `init` | Setup | Run the interactive setup wizard to configure providers, keys, and persona. |
| `carbonclaw status` | Dashboard | View real-time system status and sustainability metrics in a live TUI. |
| `carbonclaw doctor` | Diagnostics | Diagnose system health, verify API keys, and check Python/Playwright dependencies. |
| `carbonclaw doc-sync` | Automation | Audit modified Python files via AST and auto-generate/inject missing docstrings. |
| `carbonclaw healer-daemon` | Automation | Start a file-watching background daemon to autonomously heal test and lint errors on save. |
| `carbonclaw playback-list` | Telemetry | List all historically tracked engineering sessions and carbon emission metrics. |
| `carbonclaw playback <id>` | Telemetry | Step through and replay the exact thoughts, tool calls, and logs of a past session. |
| `carbonclaw schedule-add "..."` | Carbon-Aware | Schedule a task to run automatically during green grid peak (low-carbon) hours. |
| `carbonclaw schedule-list` | Carbon-Aware | List queued and completed scheduled tasks with their carbon savings. |
| `carbonclaw schedule-daemon` | Carbon-Aware | Run the polling background daemon to process queued carbon-aware tasks. |
| `carbonclaw template-list` | Swarm | List all locally installed agent configuration templates. |
| `carbonclaw template-pull <name>` | Swarm | Pull and install a specialized agent configuration template from the marketplace. |


## 💬 Chat Features

The `carbonclaw chat` command provides a modern AI coding CLI experience:

| Feature | How to Use |
|---------|-----------|
| **Multi-line input** | End a line with `\` or type ` ``` ` to start a code block |
| **Draft preservation** | Press `Ctrl+C` while typing — draft is restored on next prompt |
| **History search** | `/history <query>` or native `Ctrl+R` |
| **Sustainability** | `/carbon` shows aggregated carbon emissions |
| **Task Scheduling** | `/schedule <task>` queues tasks for green peak hours, `/schedule list` shows queue, `/schedule now! <task_id>` overrides |
| **Session Playback** | `/playback <session_id>` replays thoughts/tool logs of a past agent session, `/playback` lists sessions |
| **Smart Routing** | `/strategy <mode>` toggles routing (sustainability, latency, balanced) |
| **Provider Setup** | `/provider <name>` interactively switch LLM providers |
| **Advanced Fetch** | `/fetch <url>` renders JS-heavy pages via Playwright |
| **Deep Research** | `/research <query>` executes Map-Reduce analysis pipeline |
| **Privacy Audit** | `/audit` scans history for potential PII or secret leaks |
| **Open editor** | `/editor` opens `$EDITOR` to compose long messages |
| **Slash commands** | `/help`, `/clear`, `/undo`, `/redo`, `/mode`, `/compact`, `/export`, `/import` |
| **Shell escape** | `!command` runs shell commands and injects results into the conversation |
| **Approval gates** | Dangerous operations show colored diffs before asking `Proceed? [y/n]` |

## 📖 Documentation

For detailed guides, architecture, and advanced usage, see [CLAUDE.md](./CLAUDE.md).

## 📅 Roadmap (Next 1-3 Months)

### Month 1: IDE Integration & Swarm Expansion
- [x] **IDE / Extension Integration**: Launch extension API backend endpoints to provide inline sustainability badges and execution security gates directly inside editors.
- [x] **Multi-Agent Debate UI**: Add a rich, interactive TUI for viewing Swarm Debates in real-time, allowing humans to interject and vote on agent proposals.
- [x] **Playwright Visual Testing**: Agents can write and execute visual regression tests using the integrated `VisionTool` and Pillow comparison.

### Month 2: Proactive Automation & CI/CD
- [x] **Event-Driven Workflows**: Connect CarbonClaw to GitHub/GitLab Webhooks to autonomously heal CI build pipelines, creating and verifying automated branch fixes.
- [x] **Self-Documenting Code**: Launch `doc-sync` AST auditing daemon to continuously audit modified files and inject missing docstrings in real-time.
- [ ] **Automated Benchmark Dashboard**: A hosted dashboard comparing the carbon efficiency of open-source models based on CarbonClaw's anonymous telemetry data.


### Month 3: Deep Repo Awareness & Ecosystem
- [ ] **Advanced Graph Memory Expansion**: Connect the AST Knowledge Graph to Git history (blame, churn) to predict which files are most likely to introduce bugs during a refactor.
- [ ] **Custom Plugin Ecosystem**: Stabilize the plugin API so users can publish and share custom tools (e.g., `carbonclaw-tool-aws`, `carbonclaw-tool-jira`).
- [ ] **Local Model Fine-Tuning**: A CLI command to automatically export successful "lessons learned" and code fixes into a LoRA dataset for fine-tuning small local models.

## License

MIT
