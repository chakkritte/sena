"""Slash command system for Sena chat.

Commands are dispatched before the message reaches the LLM, letting users
control the session (clear history, compact context, etc.).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.table import Table

from sena.core.models import Message

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
            "Initialize a project-specific SENA.md file.",
            _cmd_init,
        )


# ---------------------------------------------------------------------- #
# Default handlers
# ---------------------------------------------------------------------- #


async def _cmd_init(messages: list[Message], _args: str, _registry: SlashRegistry) -> SlashResult:
    """Trigger an autonomous repository analysis to create SENA.md."""
    prompt = (
        "Perform a deep analysis of this repository. "
        "1. List and read key files to understand the project structure and architecture.\n"
        "2. Identify coding conventions, technologies used, and project goals.\n"
        "3. Create a comprehensive SENA.md file in the root directory summarizing these findings.\n"
        "The SENA.md should serve as the primary instruction manual for future AI engineering sessions."
    )

    return SlashResult(
        messages=messages + [Message(role="user", content=prompt)],
        output=(
            "[bold blue]Initialization started.[/bold blue]\n"
            "Sena is now analyzing the repository to generate a project-specific [bold]SENA.md[/bold].\n"
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

    from sena.cli.models import _get_models, _update_config
    from sena.config.settings import SenaConfig
    from sena.providers.registry import ProviderRegistry

    config = SenaConfig()

    # 1. Select Provider
    providers = ProviderRegistry.available()
    from sena.cli.main import console
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
        "normal": "You are Sena, an AI software engineering assistant. Think step by step, then use tools when needed.",
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

    path = Path(args.strip() or "sena_export.json")
    data = [m.model_dump(mode="json") for m in _messages]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return SlashResult(output=f"[dim]Exported {len(_messages)} messages to {path}.[/dim]")


async def _cmd_import(_messages: list[Message], args: str, _registry: SlashRegistry) -> SlashResult:
    """Load conversation from JSON file."""
    import json
    from pathlib import Path

    path = Path(args.strip() or "sena_export.json")
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

    history_path = Path.home() / ".config" / "sena" / "chat_history"
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
    from sena.cli.main import console
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
