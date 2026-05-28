# 🤖 CarbonClaw: Sustainability-Focused, Local-First, and Privacy-First AI Agent Runtime

## 🌟 Overview
CarbonClaw is an advanced, AI-native runtime designed to automate complex software engineering tasks, manage multi-agent collaboration, and facilitate self-evolving research workflows. It acts as a powerful orchestration layer, allowing human users to direct sophisticated, multi-step processes that span planning, coding, testing, reviewing, and documentation.

CarbonClaw brings the principle of **autonomous development** to the command line, moving beyond simple API calls to solve entire development cycles.

## 💡 Core Philosophy
The system's core philosophy is built on **Observability, Reliability, and Iteration**:
1.  **Observability:** Every step is tracked via OpenTelemetry tracing, providing granular visibility into execution paths, decision-making, and token costs.
2.  **Reliability:** Mandatory human-in-the-loop (HITL) approval gates are enforced for sensitive or high-impact operations, now featuring **Impact Analysis**.
3.  **Iteration:** Agents are designed to self-evolve, learning from successful and failed workflows to improve future performance through **Strategic Evolution**.
4.  **Sustainability:** Active carbon budgeting enforces hard emission limits per session or task, while grid carbon intensity forecasting postpones non-urgent actions to solar/wind peak hours.

## 🛠️ Tech Stack & Architecture
The architecture is modular and adheres to strict engineering standards:

*   **Languages:** Python (Primary), TypeScript/JavaScript (Frontend/Tools).
*   **Frameworks:** FastAPI (Implied API structure), Playwright (Browser Automation), OpenTelemetry (Observability).
*   **Database:** SQLite + ChromaDB (**Hybrid Memory**).
*   **Design Pattern:** Composition over Inheritance (Modular agent design).
*   **Quality:** 100% Mypy compliance enforced across the project.

## 📂 Project Structure Deep Dive

The repository is organized into several distinct, composable modules:

### 👤 `carbonclaw/agents/` (The Brains)
This directory houses the specialized, callable AI agents, implementing the core decision-making logic.
*   `base.py`: Defines the foundational `Agent` class with **Parallel Tool Execution** support.
*   `supervisor.py`: Coordinates agents via event bus, featuring a new **Swarm Debate** workflow.
*   `evolution.py`: Implements **Strategic Evolution** for autonomous router optimization.
*   `healer.py`: **Self-Healing CI** daemon that automatically fixes failing test suites.
*   `planner.py`: Responsible for breaking down high-level goals into actionable, ordered steps.
*   `coding.py`: Executes code generation, adhering to best practices and syntax rules.
*   `qa.py`: Runs rigorous testing, including unit and integration tests.
*   `review.py`: Performs code audits, checking for security flaws, style violations, and optimization opportunities.
*   `docs.py`: Generates comprehensive documentation artifacts based on the codebase.

### 🌐 `carbonclaw/tools/` (The Hands)
The Adapter layer that allows the AI to interact with the external environment. These tools are the system's sensory and motor functions.
*   `file.py`: File system operations (read, write, search).
*   `shell.py`: Executes system shell commands, featuring **Docker Sandbox Integration**.
*   `vision.py`: **Visual Architecture Verification**, enabling agents to parse diagrams and mockups.
*   `git.py`: Full Git integration (status, diff, commit).
*   `web_search.py`: Interfaces with external search APIs (e.g., Google, Bing).
*   `browser.py`: Wrapper around Playwright for full browser automation, scraping, and **Visual/Vision** support.

### 🧠 `carbonclaw/context/` & `carbonclaw/memory/` (The Memory)
These modules manage the state and long-term recall of the system.
*   **Context:** Manages the current session state, history, and immediate variables.
*   **Memory:** Featuring **HybridMemory** (SQLite + ChromaDB) and **KnowledgeGraphMemory** (AST-based parsing for deep repository awareness).

### ⚙️ `carbonclaw/providers/` & `carbonclaw/core/router.py` (The Connections)
This is the critical abstraction layer. It allows the core logic to remain agnostic of the underlying LLM provider.
*   **Smart Router:** Dynamically selects the best model/provider based on **Task Type**, **Complexity**, and **Learned Strategic Adjustments**.
*   **Benchmarker:** Runs **Model Distillation (Shadow Trials)** in the background to autonomously find the most carbon-efficient models.
*   **Task Classifier:** Keyword-based classification in `routing/classifier.py` for zero-latency categorization.

### 🔬 `carbonclaw/agents/research.py` (Advanced Research)
Implements a state-of-the-art **Map-Reduce** research pipeline:
1.  **Search**: DuckDuckGo search for relevant sources.
2.  **Fetch**: High-fidelity page extraction using Playwright & Trafilatura.
3.  **Map**: Parallel summarization of each source using fast local models.
4.  **Reduce**: Synthesis of all summaries into a cited, structured report using high-capacity models.

### 🖥️ `carbonclaw/cli/` (The Interface)
The primary user-facing entry points. These scripts wrap the complex agent interactions into simple, actionable CLI commands (e.g., `carbonclaw run`, `carbonclaw chat`).
*   `status.py`: New rich TUI dashboard for sustainability and system status tracking.

## 🚀 Getting Started (Quick Start Guide)

### Prerequisites
*   Python 3.12+
*   `uv` (Recommended, will be automatically installed if missing)
*   Git

### 1. Installation
Execute the provided installation script:

**Linux / macOS (Bash):**
```bash
curl -fsSL https://raw.githubusercontent.com/chakkritte/carbonclaw/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/chakkritte/carbonclaw/main/install.ps1 | iex
```

### 2. Configuration
Initialize the local environment and set up your preferred LLM providers:
```bash
# Initialize agent persona and local state
carbonclaw init

# View available providers and set API keys
carbonclaw models
```

### 3. Usage Examples
| Command | Purpose | Description |
| :--- | :--- | :--- |
| `carbonclaw chat` | **Interactive Chat** | Starts a persistent, contextual conversation with the AI. Supports `/schedule`. |
| `carbonclaw run "..."` | **One-Shot Task** | Executes a specific, self-contained task. Supports `--carbon-budget`. |
| `carbonclaw plan` | **Goal Planning** | Takes a high-level goal and outputs a multi-step, actionable plan for human review. |
| `carbonclaw status` | **System Status** | View the sustainability and system status dashboard (Live TUI). |
| `carbonclaw doctor` | **System Health** | Runs diagnostics on dependencies, configuration, and local environment integrity. |
| `carbonclaw risk <file>` | **Risk Assessment** | Predict refactoring risk score and downstream blast radius using Git history and AST parsing. |
| `carbonclaw schedule-add "..."` | **Add Scheduled Task** | Schedule a task to run automatically during optimal, green-energy hours. |
| `carbonclaw schedule-list` | **List Schedule** | Renders a table of queued, running, and completed tasks with savings and emissions. |
| `carbonclaw schedule-daemon` | **Scheduler Daemon** | Runs a background daemon process that continuously polls and executes due tasks. |
| `carbonclaw playback <session_id>` | **Session Playback** | Steps through the recorded reasoning, duration, and emissions of an agent session. |
| `carbonclaw playback-list` | **List Sessions** | Displays all uniquely tracked historical agent sessions in a telemetry table. |
| `carbonclaw template-list` | **List Templates** | Lists all locally installed agent configuration templates. |
| `carbonclaw template-pull <name>` | **Pull Template** | Downloads and installs a specialized agent configuration template from the marketplace. |
| `carbonclaw template-publish <name>` | **Publish Template** | Registers your custom agent configuration template to the marketplace. |
| `carbonclaw doc-sync` | **Document Sync** | Audits modified files and auto-generates/injects missing Python docstrings via AST parsing. |
| `carbonclaw healer-daemon` | **Healer Daemon** | Start a file-watching background daemon that auto-heals lint and test failures on save. |


## 🔮 Roadmap & Future Work
CarbonClaw is continually evolving. Key upcoming phases include:
*   **Phase 4:** Implementing Event-Driven CI/CD Workflows.
*   **Phase 5:** Advanced Graph Memory integration for complex knowledge retrieval.
*   **Phase 6:** Local Language Server Protocol (LSP) Integration for IDE support.

---
*Built with a commitment to engineering excellence and autonomous computation.*