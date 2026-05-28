"""Slash command system for CarbonClaw chat.

Commands are dispatched before the message reaches the LLM, letting users
control the session (clear history, compact context, etc.).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.table import Table
from rich.console import Console

from carbonclaw.core.models import Message

SlashHandler = Callable[[list[Message], str, "SlashRegistry"], Awaitable["SlashResult"]]


@dataclass
class SlashResult:
    """Result of executing a slash command."""

    messages: list[Message] | None = None
    """Updated message list (e.g. after /clear)."""
    output: Any = ""
    """Text or Rich renderable to print to the user."""
    done: bool = False
    """If True, exit the chat loop."""
    new_model: str | None = None
    """Signal to switch the current session model."""


@dataclass
class SlashCommand:
    """A single slash command definition."""

    name: str
    description: str
    handler: SlashHandler
    aliases: tuple[str, ...] = field(default_factory=tuple)


class SlashRegistry:
    """Registry and dispatcher for slash commands."""

    def __init__(self) -> None:
        """Create a new registry with the built-in commands."""
        self._commands: dict[str, SlashCommand] = {}
        self._history: list[list[Message]] = []
        self._redo_stack: list[list[Message]] = []
        self._register_defaults()

    def register(
        self,
        name: str,
        description: str,
        handler: SlashHandler,
        aliases: tuple[str, ...] = (),
    ) -> None:
        """Register a new slash command."""
        cmd = SlashCommand(name, description, handler, aliases)
        self._commands[name] = cmd
        for alias in aliases:
            self._commands[alias] = cmd

    async def dispatch(self, messages: list[Message], raw_input: str) -> SlashResult | None:
        """Parse and run a slash command.

        Returns ``None`` if the input is not a recognised slash command.
        """
        stripped = raw_input.strip()
        if not stripped.startswith("/"):
            return None
        parts = stripped[1:].split(maxsplit=1)
        name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        cmd = self._commands.get(name)
        if cmd is None:
            return None
        # Snapshot current state for undo before executing
        self._history.append([m.model_copy() for m in messages])
        self._redo_stack.clear()
        return await cmd.handler(messages, args, self)

    def help_table(self) -> Table:
        """Return a Rich Table of all registered commands."""
        table = Table(title="Slash Commands", show_header=True, header_style="bold green")
        table.add_column("Command", style="bold cyan", no_wrap=True)
        table.add_column("Description")
        seen: set[str] = set()
        for cmd in self._commands.values():
            if cmd.name in seen:
                continue
            seen.add(cmd.name)
            aliases = f" ({', '.join(cmd.aliases)})" if cmd.aliases else ""
            table.add_row(f"/{cmd.name}{aliases}", cmd.description)
        return table

    # ------------------------------------------------------------------ #
    # Default commands
    # ------------------------------------------------------------------ #
    def _register_defaults(self) -> None:
        self.register(
            "clear",
            "Clear the conversation history (keeps the system prompt).",
            _cmd_clear,
            aliases=("cls",),
        )
        self.register(
            "compact",
            "Summarise the conversation and replace history with the summary.",
            _cmd_compact,
        )
        self.register(
            "help",
            "Show this help message.",
            _cmd_help,
            aliases=("h", "?"),
        )
        self.register(
            "debug",
            "Toggle debug mode (prints raw messages).",
            _cmd_debug,
        )
        self.register(
            "model",
            "Show the current model. Pass a model ID to switch.",
            _cmd_model,
        )
        self.register(
            "cost",
            "Show approximate token usage for the current session.",
            _cmd_cost,
        )
        self.register(
            "undo",
            "Undo the last action.",
            _cmd_undo,
        )
        self.register(
            "redo",
            "Redo the previously undone action.",
            _cmd_redo,
        )
        self.register(
            "export",
            "Export conversation history to a JSON file.",
            _cmd_export,
        )
        self.register(
            "import",
            "Import conversation history from a JSON file.",
            _cmd_import,
        )
        self.register(
            "provider",
            "List and switch between configured LLM providers.",
            _cmd_provider,
        )
        self.register(
            "fetch",
            "Advanced web scraping/fetching using BrowserTool.",
            _cmd_fetch,
        )
        self.register(
            "audit",
            "Scan history for potential leaks (secrets, keys).",
            _cmd_audit,
        )
        self.register(
            "mask",
            "Mask sensitive information in the current conversation context.",
            _cmd_mask,
        )
        self.register(
            "research",
            "Perform deep web research using Map-Reduce pipeline.",
            _cmd_research,
        )
        self.register(
            "mode",
            "Switch agent mode (normal, plan, code, review, qa, docs).",
            _cmd_mode,
        )
        self.register(
            "editor",
            "Open $EDITOR to compose a multi-line message.",
            _cmd_editor,
        )
        self.register(
            "history",
            "Search and re-use previous messages from chat history.",
            _cmd_history,
        )
        self.register(
            "init",
            "Initialize a project-specific CARBONCLAW.md file.",
            _cmd_init,
        )
        self.register(
            "carbon",
            "Show aggregated carbon emissions for this project.",
            _cmd_carbon,
        )
        self.register(
            "swarm",
            "Trigger a multi-agent swarm debate for the current task.",
            _cmd_swarm,
        )
        self.register(
            "heal",
            "Run autonomous self-healing CI loop for failing tests.",
            _cmd_heal,
        )
        self.register(
            "schedule",
            "Schedule a task to run during optimal, carbon-efficient hours.",
            _cmd_schedule,
            aliases=("sched",),
        )
        self.register(
            "playback",
            "Replay agent execution steps for a specific session.",
            _cmd_playback,
            aliases=("play",),
        )


# ---------------------------------------------------------------------- #
# Default handlers
# ---------------------------------------------------------------------- #


async def _cmd_playback(messages: list[Message], args: str, _registry: SlashRegistry) -> SlashResult:
    """Replay agent reasoning steps for a session."""
    from carbonclaw.telemetry.playback import TraceStore, render_session_playback
    from rich.prompt import Prompt
    from rich.table import Table

    store = TraceStore()
    session_id = args.strip()

    if not session_id:
        # If no session ID provided, list recent sessions
        sessions = store.sessions()
        if not sessions:
            return SlashResult(output="[dim]No recorded agent sessions found.[/dim]")

        from carbonclaw.cli.main import console

        table = Table(
            title="🎬 Tracked Agent Sessions", show_header=True, header_style="bold green"
        )
        table.add_column("Session ID", style="cyan")
        table.add_column("Agent Class", style="white")
        table.add_column("Total Steps", justify="right", style="magenta")
        table.add_column("Total Duration", justify="right", style="yellow")
        table.add_column("Total Emissions (g)", justify="right", style="green")
        table.add_column("Timestamp", style="dim")

        # Show latest 10 sessions
        for s in reversed(sessions[-10:]):
            table.add_row(
                s["session_id"],
                s["agent_name"].upper(),
                str(s["total_steps"]),
                f"{s['total_duration']:.2f}s",
                f"{s['total_emissions_kg'] * 1000.0:.3f}g",
                s["timestamp"].split("T")[0] if "T" in s["timestamp"] else s["timestamp"],
            )

        console.print(table)

        choice = Prompt.ask(
            "Enter a Session ID to replay (or press Enter to cancel)",
            default="",
            show_default=False,
        )
        session_id = choice.strip()
        if not session_id:
            return SlashResult(output="[dim]Playback cancelled.[/dim]")

    playback_group = render_session_playback(session_id)
    if playback_group is None:
        return SlashResult(output=f"[red]Error: Session '{session_id}' not found.[/red]")

    return SlashResult(output=playback_group)


async def _cmd_schedule(messages: list[Message], args: str, _registry: SlashRegistry) -> SlashResult:
    """Manage the carbon-aware task schedule."""
    from carbonclaw.telemetry.scheduler import SchedulerStore, execute_task
    from rich.table import Table

    store = SchedulerStore()
    subparts = args.strip().split(maxsplit=1)
    subcmd = subparts[0].lower() if subparts else ""
    subargs = subparts[1].strip() if len(subparts) > 1 else ""

    if subcmd == "list":
        tasks = store.tasks()
        if not tasks:
            return SlashResult(output="[dim]No scheduled tasks found.[/dim]")

        table = Table(title="🌱 Carbon-Aware Task Schedule", show_header=True, header_style="bold green")
        table.add_column("ID", style="cyan")
        table.add_column("Instruction", style="white")
        table.add_column("Status", style="bold")
        table.add_column("Scheduled At", style="dim")
        table.add_column("Est. Savings", justify="right", style="green")
        table.add_column("Emissions (kg CO2)", justify="right", style="bold red")

        for t in tasks:
            status_color = "yellow"
            if t.status == "completed":
                status_color = "green"
            elif t.status == "failed":
                status_color = "red"
            elif t.status == "running":
                status_color = "blue"

            table.add_row(
                t.id,
                t.command if len(t.command) < 40 else t.command[:37] + "...",
                f"[{status_color}]{t.status}[/{status_color}]",
                t.scheduled_at.split("T")[1][:5] if "T" in t.scheduled_at else t.scheduled_at,
                f"{t.carbon_savings_grams:.1f}g",
                f"{t.emissions_kg:.6f}" if t.status == "completed" else "-",
            )
        return SlashResult(output=table)

    elif subcmd == "now!":
        task_id = subargs
        if not task_id:
            return SlashResult(output="[red]Please specify a task ID. Usage: /schedule now! <task_id>[/red]")
        tasks = store.tasks()
        task = next((t for t in tasks if t.id == task_id), None)
        if not task:
            return SlashResult(output=f"[red]Task '{task_id}' not found.[/red]")
        if task.status in ["completed", "running"]:
            return SlashResult(output=f"[yellow]Task is already {task.status}.[/yellow]")

        from carbonclaw.cli.main import console
        console.print(f"🚀 [bold yellow]Executing task '{task_id}' immediately...[/bold yellow]")
        store.update_task_status(task_id, "running")
        try:
            emissions = await execute_task(task)
            store.update_task_status(task_id, "completed", emissions)
            return SlashResult(
                output=f"[bold green]✅ Task '{task_id}' successfully completed.[/bold green]\nEmissions: [white]{emissions:.6f} kg CO2[/white]"
            )
        except Exception as e:
            store.update_task_status(task_id, "failed")
            return SlashResult(output=f"[bold red]❌ Task execution failed:[/bold red] {e}")

    else:
        # Schedule a new task
        task_instruction = args.strip()
        if not task_instruction:
            return SlashResult(
                output=(
                    "[bold yellow]Usage:[/bold yellow]\n"
                    "- `/schedule <instruction>`: Schedule a new engineering task.\n"
                    "- `/schedule list`: View queued/completed tasks.\n"
                    "- `/schedule now! <task_id>`: Bypass queue and run immediately."
                )
            )

        # Detect mode based on keywords
        mode = "code"
        if "research" in task_instruction.lower():
            mode = "research"
        elif "swarm" in task_instruction.lower():
            mode = "swarm"

        task = store.add_task(task_instruction, mode)
        output = (
            f"🌱 [bold green]Task scheduled at optimal green hour![/bold green]\n"
            f"[bold]Task ID:[/bold] [cyan]{task.id}[/cyan]\n"
            f"[bold]Scheduled for:[/bold] {task.scheduled_at.split('T')[1][:5] if 'T' in task.scheduled_at else task.scheduled_at}\n"
            f"[bold]Projected Carbon Savings:[/bold] [bold white]{task.carbon_savings_grams:.2f}g CO2[/bold white]\n"
            f"[dim]Run 'carbonclaw schedule-daemon' to process queued tasks autonomously.[/dim]"
        )
        return SlashResult(output=output)


async def _cmd_heal(messages: list[Message], args: str, _registry: SlashRegistry) -> SlashResult:
    """Trigger the HealerAgent."""
    test_cmd = args.strip() or "uv run pytest"
    
    from carbonclaw.agents.supervisor import SupervisorAgent
    from carbonclaw.agents.healer import HealerAgent
    from carbonclaw.providers.registry import ProviderRegistry
    from carbonclaw.config.settings import CarbonClawConfig
    from carbonclaw.memory.sqlite import SQLiteMemory
    
    config = CarbonClawConfig()
    provider = ProviderRegistry.create(config.default_provider, config)
    memory = SQLiteMemory()
    
    supervisor = SupervisorAgent(provider, [], memory)
    healer = HealerAgent(supervisor, test_command=test_cmd)
    
    from carbonclaw.cli.main import console
    console.print(f"🩺 [bold yellow]Starting Self-Healing CI daemon (Cmd: {test_cmd})...[/bold yellow]")
    
    try:
        success = await healer.heal_loop()
        if success:
            return SlashResult(output="[bold green]✅ Healing successful or no errors found.[/bold green]")
        else:
            return SlashResult(output="[bold red]❌ Healing failed after max attempts.[/bold red]")
    except Exception as e:
        return SlashResult(output=f"[red]Healer error:[/red] {str(e)}")


async def _cmd_swarm(messages: list[Message], args: str, _registry: SlashRegistry) -> SlashResult:
    """Trigger a swarm debate."""
    task = args.strip()
    if not task:
        # If no task provided, use the last user message
        for msg in reversed(messages):
            if msg.role == "user" and not msg.content.startswith("/"):
                task = msg.content
                break
    
    if not task:
        return SlashResult(output="[red]Please provide a task or question for the swarm.[/red]")

    from carbonclaw.agents.supervisor import SupervisorAgent
    from carbonclaw.providers.registry import ProviderRegistry
    from carbonclaw.config.settings import CarbonClawConfig
    from carbonclaw.memory.sqlite import SQLiteMemory
    
    config = CarbonClawConfig()
    provider = ProviderRegistry.create(config.default_provider, config)
    memory = SQLiteMemory()
    
    supervisor = SupervisorAgent(provider, [], memory)
    
    from carbonclaw.cli.main import console
    console.print(f"🐝 [bold yellow]Initiating Swarm Debate:[/bold yellow] {task}")
    
    try:
        result = await supervisor.swarm_debate(task)
        return SlashResult(output=result)
    except Exception as e:
        return SlashResult(output=f"[red]Swarm failed:[/red] {str(e)}")


async def _cmd_carbon(_messages: list[Message], _args: str, _registry: SlashRegistry) -> SlashResult:
    """Show aggregated carbon emissions."""
    from carbonclaw.telemetry.carbon import CarbonStore
    store = CarbonStore()
    total = store.total_emissions()
    
    # Approximation: 1kg CO2 is roughly 4-5 km of driving a car
    driving_km = total * 5.0 
    
    output = (
        f"🌱 [bold green]Sustainability Report[/bold green]\n"
        f"Total carbon emissions: [bold white]{total:.6f} kg CO2[/bold white]\n"
        f"Equivalent to driving approx [bold]{driving_km:.2f} km[/bold] in a petrol car."
    )
    return SlashResult(output=output)


async def _cmd_init(messages: list[Message], _args: str, _registry: SlashRegistry) -> SlashResult:
    """Trigger an autonomous repository analysis to create CARBONCLAW.md."""
    prompt = (
        "Perform a deep analysis of this repository. "
        "1. List and read key files to understand the project structure and architecture.\n"
        "2. Identify coding conventions, technologies used, and project goals.\n"
        "3. Create a comprehensive CARBONCLAW.md file in the root directory summarizing these findings.\n"
        "The CARBONCLAW.md should serve as the primary instruction manual for future AI engineering sessions."
    )

    return SlashResult(
        messages=messages + [Message(role="user", content=prompt)],
        output=(
            "[bold blue]Initialization started.[/bold blue]\n"
            "CarbonClaw is now analyzing the repository to generate a project-specific [bold]CARBONCLAW.md[/bold].\n"
            "This may take a few moments as I explore the codebase..."
        )
    )


async def _cmd_clear(messages: list[Message], _args: str, _registry: SlashRegistry) -> SlashResult:
    system = [m for m in messages if m.role == "system"]
    return SlashResult(
        messages=system,
        output="[dim]Conversation history cleared.[/dim]",
    )


async def _cmd_compact(messages: list[Message], _args: str, _registry: SlashRegistry) -> SlashResult:
    system = [m for m in messages if m.role == "system"]
    return SlashResult(
        messages=system
        + [
            Message(
                role="user",
                content="Please provide a concise summary of our conversation so far.",
            ),
        ],
        output="[dim]Conversation compacted — awaiting summary from model.[/dim]",
    )


async def _cmd_help(_messages: list[Message], _args: str, registry: SlashRegistry) -> SlashResult:
    return SlashResult(output=registry.help_table())


async def _cmd_debug(_messages: list[Message], _args: str, _registry: SlashRegistry) -> SlashResult:
    return SlashResult(output="[dim]Debug mode toggled (not yet implemented).[/dim]")


async def _cmd_model(_messages: list[Message], args: str, _registry: SlashRegistry) -> SlashResult:
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt

    from carbonclaw.cli.models import _get_models, _update_config
    from carbonclaw.config.settings import CarbonClawConfig
    from carbonclaw.providers.registry import ProviderRegistry

    config = CarbonClawConfig()

    # 1. Select Provider
    providers = ProviderRegistry.available()
    from carbonclaw.cli.main import console
    console.print(Panel("🤖 [bold blue]Model Selection Wizard[/bold blue]", border_style="blue"))
    console.print(f"\nAvailable providers: [cyan]{', '.join(providers)}[/cyan]")
    selected_provider = Prompt.ask(
        "Select a provider",
        choices=providers,
        default=config.default_provider,
    )

    # 2. Fetch and Select Model
    console.print(f"Fetching models for [bold]{selected_provider}[/bold]...")
    model_ids = await _get_models(selected_provider, config)

    if not model_ids:
        console.print(f"[yellow]No models returned for {selected_provider}.[/yellow]")
        selected_model = Prompt.ask("Enter model ID manually")
    else:
        table = Table(title=f"Available Models — {selected_provider}")
        table.add_column("ID", style="cyan")
        for m in model_ids:
            table.add_row(m)
        console.print(table)

        selected_model = Prompt.ask(
            "Select a model ID",
            choices=model_ids,
            default=model_ids[0] if model_ids else "",
        )

    # 3. Apply changes
    console.print(f"\nYou selected: [bold green]{selected_provider} / {selected_model}[/bold green]")

    persist = Confirm.ask("Set as global default?")
    if persist:
        _update_config("default_provider", selected_provider)
        _update_config("default_model", selected_model)
        console.print("[green]Global configuration updated.[/green]")

    return SlashResult(
        output=f"[bold green]Session model switched to: {selected_model}[/bold green]",
        new_model=selected_model
    )


async def _cmd_cost(_messages: list[Message], _args: str, _registry: SlashRegistry) -> SlashResult:
    return SlashResult(output="[dim]Cost tracking (tokens) is not yet implemented.[/dim]")


async def _cmd_research(_messages: list[Message], args: str, _registry: SlashRegistry) -> SlashResult:
    """Perform deep research."""
    query = args.strip()
    if not query:
        return SlashResult(output="[red]Please provide a research query.[/red]")
    
    from carbonclaw.agents.research import ResearchAgent
    from carbonclaw.providers.registry import ProviderRegistry
    from carbonclaw.memory.sqlite import SQLiteMemory
    from carbonclaw.config.settings import CarbonClawConfig
    from carbonclaw.ui.streaming import StreamingDisplay
    from carbonclaw.telemetry.carbon import track_carbon
    
    config = CarbonClawConfig()
    provider = ProviderRegistry.create(config.default_provider, config)
    memory = SQLiteMemory()
    
    agent = ResearchAgent(provider, [], memory)
    
    console = Console()
    console.print(f"🔍 [bold blue]Starting Deep Research:[/bold blue] {query}")
    
    with track_carbon("research_pipeline") as ct:
        with StreamingDisplay(console, title=" Researching... ") as stream:
            # We wrap the async call
            try:
                result = await agent.research(query)
                stream.append(result.report)
            except Exception as e:
                return SlashResult(output=f"[red]Research failed:[/red] {str(e)}")

        emissions = ct.last_emissions
        footer = f"\n\n🌱 [dim]Research complete. {len(result.sources)} sources analyzed. Emissions: {emissions:.6f} kg CO2[/dim]"
        console.print(footer)
        
    return SlashResult(output=None) # Already printed


async def _cmd_mask(messages: list[Message], _args: str, _registry: SlashRegistry) -> SlashResult:
    """Mask sensitive information in history."""
    from carbonclaw.utils.privacy import mask_secrets
    new_messages = []
    masked_count = 0
    for m in messages:
        if m.role == "system":
            new_messages.append(m)
            continue
        original = m.content or ""
        masked = mask_secrets(original)
        if original != masked:
            masked_count += 1
            m.content = masked
        new_messages.append(m)
    
    return SlashResult(
        messages=new_messages,
        output=f"[bold green]Privacy Mask applied.[/bold green] Masked content in {masked_count} messages."
    )


async def _cmd_audit(_messages: list[Message], _args: str, _registry: SlashRegistry) -> SlashResult:
    """Scan history for potential leaks (secrets, keys)."""
    from carbonclaw.utils.privacy import scan_text
    
    findings = []
    for i, msg in enumerate(_messages):
        if not msg.content:
            continue
        results = scan_text(msg.content)
        for res in results:
            findings.append(f"- [yellow]Potential {res['type']} detected[/yellow] in {msg.role} message (pos {res['start']}).")

    if not findings:
        return SlashResult(output="[bold green]✅ Privacy Audit passed.[/bold green] No obvious leaks detected in current context.")
    
    output = "[bold red]⚠️ Privacy Audit Findings:[/bold red]\n" + "\n".join(findings)
    output += "\n\n[dim]Recommendation: Use /mask, /compact, or /clear if these are sensitive.[/dim]"
    return SlashResult(output=output)


async def _cmd_fetch(_messages: list[Message], args: str, _registry: SlashRegistry) -> SlashResult:
    """Fetch and render a URL using BrowserTool."""
    url = args.strip()
    if not url:
        return SlashResult(output="[red]Please provide a URL.[/red]")
    
    from carbonclaw.tools.browser import BrowserTool
    from rich.console import Console
    tool = BrowserTool()
    
    console = Console()
    console.print(f"[dim]🌐 Fetching and rendering {url}...[/dim]")
    
    # Run in a temporary browser session
    try:
        result = await tool.execute({"url": url, "action": "goto"})
        if result.is_error:
            return SlashResult(output=f"[red]Fetch failed:[/red] {result.content}")
        
        # Get markdown
        content = await tool.execute({"action": "markdown"})
        return SlashResult(output=f"## Content from {url}\n\n{content.content[:5000]}")
    except Exception as e:
        return SlashResult(output=f"[red]Error during fetch:[/red] {str(e)}")


async def _cmd_provider(_messages: list[Message], args: str, _registry: SlashRegistry) -> SlashResult:
    """List or switch providers."""
    from carbonclaw.config.settings import CarbonClawConfig
    config = CarbonClawConfig()
    
    available = ["openai", "anthropic", "gemini", "ollama"]
    
    target = args.strip().lower()
    if not target:
        output = "[bold white]Available Providers:[/bold white]\n"
        for p in available:
            active = " (active)" if p == config.default_provider else ""
            output += f"- {p}{active}\n"
        output += "\nUsage: `/provider <name>` to switch."
        return SlashResult(output=output)

    if target in available:
        config.default_provider = target
        return SlashResult(
            output=f"Provider switched to [bold green]{target}[/bold green]. Context will re-init.",
            new_model="auto" 
        )
    
    return SlashResult(output=f"[red]Unknown provider: {target}[/red]")


async def _cmd_mode(messages: list[Message], args: str, _registry: SlashRegistry) -> SlashResult:
    mode = args.strip().lower()
    if not mode:
        # Check if we have a mode stored in the system prompt
        current = "normal"
        for m in messages:
            if m.role == "system" and "AGENT MODE:" in (m.content or ""):
                current = m.content.split("AGENT MODE:")[1].split("\n")[0].strip() if m.content else "normal"
        return SlashResult(output=f"[dim]Current mode: {current}[/dim]")

    valid_modes = ["normal", "plan", "code", "review", "qa", "docs"]
    if mode not in valid_modes:
        return SlashResult(output=f"[red]Invalid mode: {mode}.[/red] Valid: {', '.join(valid_modes)}")

    # Update system prompt to change the agent's persona
    new_messages = []

    # Define prompts for each mode
    prompts = {
        "normal": "You are CarbonClaw, an AI software engineering assistant. Think step by step, then use tools when needed.",
        "plan": "You are a technical project planner. Break the user's request into clear, actionable steps. Each step should be specific and verifiable.",
        "code": "You are a senior software engineer. Write, edit, and review code using file and shell tools. Follow best practices.",
        "review": "You are a senior code reviewer. Review the provided code for correctness, performance, security, and style.",
        "qa": "You are an expert QA Engineer. Your goal is to ensure code quality through testing. Write robust test cases using pytest.",
        "docs": "You are a technical writer and documentation expert. Keep the project's documentation clear, accurate, and up-to-date.",
    }

    new_prompt = f"{prompts.get(mode)}\n\nAGENT MODE: {mode}"

    # Replace or add system prompt
    found_system = False
    for m in messages:
        if m.role == "system":
            m.content = new_prompt
            found_system = True
        new_messages.append(m)

    if not found_system:
        new_messages.insert(0, Message(role="system", content=new_prompt))

    return SlashResult(
        messages=new_messages,
        output=f"[bold green]Mode switched to: {mode}[/bold green]",
    )


async def _cmd_undo(_messages: list[Message], _args: str, registry: SlashRegistry) -> SlashResult:
    """Restore the previous message state from history."""
    if not registry._history:
        return SlashResult(output="[dim]Nothing to undo.[/dim]")
    previous = registry._history.pop()
    registry._redo_stack.append([m.model_copy() for m in _messages])
    return SlashResult(
        messages=previous,
        output="[dim]Undone last action.[/dim]",
    )


async def _cmd_redo(_messages: list[Message], _args: str, registry: SlashRegistry) -> SlashResult:
    """Restore a previously undone message state."""
    if not registry._redo_stack:
        return SlashResult(output="[dim]Nothing to redo.[/dim]")
    next_state = registry._redo_stack.pop()
    registry._history.append([m.model_copy() for m in _messages])
    return SlashResult(
        messages=next_state,
        output="[dim]Redone last action.[/dim]",
    )


async def _cmd_export(_messages: list[Message], args: str, _registry: SlashRegistry) -> SlashResult:
    """Serialize conversation to JSON file."""
    import json
    from pathlib import Path

    path = Path(args.strip() or "carbonclaw_export.json")
    data = [m.model_dump(mode="json") for m in _messages]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return SlashResult(output=f"[dim]Exported {len(_messages)} messages to {path}.[/dim]")


async def _cmd_import(_messages: list[Message], args: str, _registry: SlashRegistry) -> SlashResult:
    """Load conversation from JSON file."""
    import json
    from pathlib import Path

    path = Path(args.strip() or "carbonclaw_export.json")
    if not path.exists():
        return SlashResult(output=f"[red]File not found: {path}[/red]")
    raw = json.loads(path.read_text(encoding="utf-8"))
    loaded = [Message(**item) for item in raw]
    return SlashResult(
        messages=loaded,
        output=f"[dim]Imported {len(loaded)} messages from {path}.[/dim]",
    )


async def _cmd_editor(
    messages: list[Message], _args: str, _registry: SlashRegistry
) -> SlashResult:
    """Open $EDITOR to compose a multi-line message."""
    import asyncio
    import os
    import tempfile

    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write("\n# Write your message above this line.\n")
        temp_path = f.name

    try:
        proc = await asyncio.create_subprocess_exec(editor, temp_path)
        await proc.wait()
        content = await asyncio.to_thread(
            Path(temp_path).read_text, encoding="utf-8"
        )
        # Remove comment lines
        lines = [line for line in content.splitlines() if not line.strip().startswith("#")]
        text = "\n".join(lines).strip()
        if not text:
            return SlashResult(output="[dim]No message entered.[/dim]")
        return SlashResult(
            messages=messages + [Message(role="user", content=text)],
            output="[dim]Message composed in editor.[/dim]",
        )
    finally:
        await asyncio.to_thread(Path(temp_path).unlink, missing_ok=True)


async def _cmd_history(
    _messages: list[Message], args: str, _registry: SlashRegistry
) -> SlashResult:
    """Search and re-use a previous message from chat history."""
    from rich.prompt import Prompt

    history_path = Path.home() / ".config" / "carbonclaw" / "chat_history"
    if not history_path.exists():
        return SlashResult(output="[dim]No history file found.[/dim]")

    raw_lines = history_path.read_text(encoding="utf-8").splitlines()
    # Filter out empty lines and deduplicate while preserving order
    seen: set[str] = set()
    entries: list[str] = []
    for line in raw_lines:
        line = line.strip()
        if line and line not in seen:
            seen.add(line)
            entries.append(line)

    if not entries:
        return SlashResult(output="[dim]No history entries found.[/dim]")

    query = args.strip().lower()
    matches = (
        [e for e in entries if query in e.lower()]
        if query
        else list(reversed(entries[-20:]))
    )

    if not matches:
        return SlashResult(output=f"[dim]No history matches for '{query}'.[/dim]")

    # Display matches
    from carbonclaw.cli.main import console
    console.print("[dim]Select a message to reuse:[/dim]")
    for i, entry in enumerate(matches[:20], 1):
        preview = entry[:80] + "..." if len(entry) > 80 else entry
        console.print(f"  [cyan]{i:2}[/cyan]. {preview}")

    choice = Prompt.ask(
        "Enter number (or leave empty to cancel)",
        default="",
        show_default=False,
    )
    if not choice.strip():
        return SlashResult(output="[dim]Cancelled.[/dim]")

    try:
        idx = int(choice.strip()) - 1
        if 0 <= idx < len(matches):
            selected = matches[idx]
            return SlashResult(
                messages=_messages + [Message(role="user", content=selected)],
                output=f"[dim]Reused: {selected[:60]}...[/dim]",
            )
    except ValueError:
        pass

    return SlashResult(output="[dim]Invalid selection.[/dim]")
