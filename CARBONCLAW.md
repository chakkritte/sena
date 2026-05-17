# 🤖 CarbonClaw: Sustainability-Focused, Local-First, and Privacy-First AI Agent Runtime

## 🌟 Overview
CarbonClaw is an advanced, AI-native runtime designed to automate complex software engineering tasks, manage multi-agent collaboration, and facilitate self-evolving research workflows. It acts as a powerful orchestration layer, allowing human users to direct sophisticated, multi-step processes that span planning, coding, testing, reviewing, and documentation.

CarbonClaw brings the principle of **autonomous development** to the command line, moving beyond simple API calls to solve entire development cycles.

## 💡 Core Philosophy
The system's core philosophy is built on **Observability, Reliability, and Iteration**:
1.  **Observability:** Every step is tracked via OpenTelemetry tracing, providing granular visibility into execution paths, decision-making, and token costs.
2.  **Reliability:** Mandatory human-in-the-loop (HITL) approval gates are enforced for sensitive or high-impact operations.
3.  **Iteration:** Agents are designed to self-evolve, learning from successful and failed workflows to improve future performance.

## 🛠️ Tech Stack & Architecture
The architecture is modular and adheres to strict engineering standards:

*   **Languages:** Python (Primary), TypeScript/JavaScript (Frontend/Tools).
*   **Frameworks:** FastAPI (Implied API structure), Playwright (Browser Automation), OpenTelemetry (Observability).
*   **Database:** SQLite (Local persistence for memory/context).
*   **Design Pattern:** Composition over Inheritance (Modular agent design).
*   **Quality:** 100% Mypy compliance enforced across the project.

## 📂 Project Structure Deep Dive

The repository is organized into several distinct, composable modules:

### 👤 `carbonclaw/agents/` (The Brains)
This directory houses the specialized, callable AI agents, implementing the core decision-making logic.
*   `base.py`: Defines the foundational `Agent` class and execution lifecycle.
*   `planner.py`: Responsible for breaking down high-level goals into actionable, ordered steps.
*   `coding.py`: Executes code generation, adhering to best practices and syntax rules.
*   `qa.py`: Runs rigorous testing, including unit and integration tests.
*   `review.py`: Performs code audits, checking for security flaws, style violations, and optimization opportunities.
*   `docs.py`: Generates comprehensive documentation artifacts based on the codebase.
*   `generalist.py`: A fallback or primary agent for unclassified tasks.

### 🌐 `carbonclaw/tools/` (The Hands)
The Adapter layer that allows the AI to interact with the external environment. These tools are the system's sensory and motor functions.
*   `file.py`: File system operations (read, write, search).
*   `shell.py`: Executes system shell commands (sandboxed).
*   `git.py`: Full Git integration (status, diff, commit).
*   `web_search.py`: Interfaces with external search APIs (e.g., Google, Bing).
*   `browser.py`: Wrapper around Playwright for full browser automation and scraping.

### 🧠 `carbonclaw/context/` & `carbonclaw/memory/` (The Memory)
These modules manage the state and long-term recall of the system.
*   **Context:** Manages the current session state, history, and immediate variables.
*   **Memory:** Provides persistent, long-term memory, allowing the system to retain knowledge across multiple sessions (e.g., user preferences, project history).

### ⚙️ `carbonclaw/providers/` & `carbonclaw/core/router.py` (The Connections)
This is the critical abstraction layer. It allows the core logic to remain agnostic of the underlying LLM provider.
*   **Smart Router:** Dynamically selects the best model/provider based on task complexity, latency, and sustainability goals. It prioritizes local models (Ollama) for simple tasks to minimize carbon footprint.
*   It includes adapters for major models (OpenAI, Gemini, Anthropic, Ollama) ensuring seamless swapping and rate-limit handling.

### 🖥️ `carbonclaw/cli/` (The Interface)
The primary user-facing entry points. These scripts wrap the complex agent interactions into simple, actionable CLI commands (e.g., `carbonclaw run`, `carbonclaw chat`).

## 🚀 Getting Started (Quick Start Guide)

### Prerequisites
*   Python 3.12+
*   `uv` (Recommended for dependency management)
*   Git

### 1. Installation
Execute the provided installation script:
```bash
curl -fsSL https://raw.githubusercontent.com/chakkritte/carbonclaw/main/install.sh | bash
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
| `carbonclaw chat` | **Interactive Chat** | Starts a persistent, contextual conversation with the AI. |
| `carbonclaw run "..."` | **One-Shot Task** | Executes a specific, self-contained task (e.g., "Refactor X file"). |
| `carbonclaw plan` | **Goal Planning** | Takes a high-level goal and outputs a multi-step, actionable plan for human review. |
| `carbonclaw doctor` | **System Health** | Runs diagnostics on dependencies, configuration, and local environment integrity. |

## 🔮 Roadmap & Future Work
CarbonClaw is continually evolving. Key upcoming phases include:
*   **Phase 4:** Implementing Event-Driven CI/CD Workflows.
*   **Phase 5:** Advanced Graph Memory integration for complex knowledge retrieval.
*   **Phase 6:** Local Language Server Protocol (LSP) Integration for IDE support.

---
*Built with a commitment to engineering excellence and autonomous computation.*