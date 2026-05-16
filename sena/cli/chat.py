"""Interactive chat command with Claude Code-style UI."""

from __future__ import annotations

import asyncio
import readline
from pathlib import Path
from typing import Any

import typer
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm
from rich.text import Text

from sena.cli.main import app, console
from sena.cli.slash import SlashRegistry
from sena.config.settings import SenaConfig
from sena.context.manager import ContextManager, TokenCounter
from sena.core.models import CompletionRequest, Message, ToolCall
from sena.memory.sqlite import SQLiteMemory
from sena.prompts.base import PromptTemplate
from sena.providers.registry import ProviderRegistry
from sena.tools.base import ToolRegistry
from sena.tools.browser import BrowserTool
from sena.tools.file import FilePatchTool, FileReadTool, FileWriteTool
from sena.tools.git import GitTool
from sena.tools.github_cli import GitHubTool
from sena.tools.mcp import register_mcp_tools
from sena.tools.python_interpreter import PythonTool
from sena.tools.search import FileSearchTool
from sena.tools.shell import ShellTool
from sena.tools.web_search import WebSearchTool
from sena.ui.banner import print_banner
from sena.ui.streaming import StreamingDisplay


def _build_system_prompt(config: SenaConfig) -> str:
    template = PromptTemplate()
    return template.render("system", context={"config": config.model_dump()})


def _print_user(text: str) -> None:
    console.print(
        Panel(
            Text(text, style="bold blue"),
            border_style="blue",
            title="[bold]you[/bold]",
            title_align="left",
            padding=(0, 1),
        )
    )


def _print_shell_escape(text: str) -> None:
    console.print(
        Panel(
            # Strip the ! and add $
            Text(f"$ {text[1:].strip()}", style="bold magenta"),
            border_style="magenta",
            title="[bold]shell[/bold]",
            title_align="left",
            padding=(0, 1),
        )
    )


def _print_assistant(text: str) -> None:
    console.print(
        Panel(
            Markdown(text, code_theme="monokai"),
            border_style="green",
            title="[bold]Sena[/bold]",
            title_align="left",
            padding=(0, 1),
        )
    )


def _print_tool(name: str, result: str, is_error: bool = False) -> None:
    display = result[:1200]
    if len(result) > 1200:
        display += f"\n\n[dim]... {len(result) - 1200} more characters[/dim]"
    color = "red" if is_error else "dim"
    border = "red" if is_error else "yellow"
    title = f"[bold {color}]{name}[/bold {color}]" if is_error else f"[bold]{name}[/bold]"
    console.print(
        Panel(
            Text(display, style=color),
            border_style=border,
            title=title,
            title_align="left",
            padding=(0, 1),
        )
    )


def _print_status(model: str, messages: list[Message]) -> None:
    total = TokenCounter.count_messages(messages)
    max_total = 128_000
    pct = min(100, int((total / max_total) * 100)) if max_total > 0 else 0
    color = "green" if pct < 60 else "yellow" if pct < 85 else "red"
    bar_filled = int(pct / 5)
    bar = f"[{'=' * bar_filled}{' ' * (20 - bar_filled)}]"
    status = (
        f"[dim]{model}[/dim] | Context: [{color}]{bar}[/] "
        f"[{color}]{pct}%[/] ({total:,}/{max_total:,})"
    )
    console.print(status, style="dim")


async def _execute_tools_with_approval(
    tool_calls: list[ToolCall],
    registry: ToolRegistry,
    config: SenaConfig,
) -> list[Message]:
    """Execute tool calls with optional interactive approval."""
    results: list[Message] = []
    for tc in tool_calls:
        tool = registry.get(tc.name)
        if tool and tool.requires_approval:
            from sena.cli.main import cli_approval_callback
            approved = await cli_approval_callback(tc.name, tc.arguments)
            if not approved:
                _print_tool(
                    tc.name,
                    "User declined execution.",
                    is_error=True,
                )
                results.append(
                    Message(
                        role="tool",
                        content="User declined execution.",
                        tool_call_id=tc.id,
                        name=tc.name,
                    )
                )
                continue
        result = await registry.execute(tc.name, tc.arguments)
        _print_tool(tc.name, result.content, is_error=result.is_error)
        results.append(
            Message(
                role="tool",
                content=result.content,
                tool_call_id=tc.id,
                name=tc.name,
            )
        )
    return results


async def _run_agent_turn(
    messages: list[Message],
    provider: Any,
    tools: ToolRegistry,
    model: str,
    config: SenaConfig,
    streaming: bool = True,
) -> None:
    """Run one ReAct turn."""
    max_iterations = 10
    for _ in range(max_iterations):
        content_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        current_tool: dict[str, Any] | None = None

        request = CompletionRequest(
            messages=messages,
            model=model,
            tools=tools.definitions(),
        )

        if streaming:
            # Stream into a live panel; it stays on screen when done
            with StreamingDisplay(console, title="Sena") as stream:
                async for chunk in provider.stream(request):
                    if chunk.content:
                        content_parts.append(chunk.content)
                        stream.append(chunk.content)
                    if chunk.tool_call:
                        tc = chunk.tool_call
                        if tc.is_start:
                            current_tool = {
                                "id": tc.id or "",
                                "name": tc.name or "",
                                "arguments": "",
                            }
                        elif tc.arguments_delta:
                            if current_tool is not None:
                                current_tool["arguments"] += tc.arguments_delta
                        elif tc.is_end:
                            if current_tool is not None:
                                import json

                                try:
                                    args = json.loads(current_tool["arguments"])
                                except json.JSONDecodeError:
                                    args = {}
                                tool_calls.append(
                                    ToolCall(
                                        id=current_tool["id"],
                                        name=current_tool["name"],
                                        arguments=args,
                                    )
                                )
                                current_tool = None
        else:
            # Non-streaming: single response
            response = await provider.complete(request)
            msg = response.message
            if msg.content:
                content_parts.append(msg.content)
            if msg.tool_calls:
                tool_calls = msg.tool_calls

        # Flush dangling tool call
        if current_tool is not None:
            import json

            try:
                args = json.loads(current_tool["arguments"])
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                ToolCall(
                    id=current_tool["id"],
                    name=current_tool["name"],
                    arguments=args,
                )
            )

        assistant_content = "".join(content_parts)
        assistant_msg = Message(
            role="assistant",
            content=assistant_content or None,
            tool_calls=tool_calls or None,
        )
        messages.append(assistant_msg)

        # Only print assistant panel if non-streaming
        if not streaming and assistant_content:
            _print_assistant(assistant_content)

        if not tool_calls:
            break

        result_msgs = await _execute_tools_with_approval(tool_calls, tools, config)
        messages.extend(result_msgs)
    else:
        _print_assistant("Reached maximum tool iterations.")


async def _chat_loop(
    provider_name: str | None,
    model: str | None,
    streaming: bool,
) -> None:
    config = SenaConfig()
    provider_name = provider_name or config.default_provider
    model = model or config.default_model or "llama3.2"

    try:
        provider = ProviderRegistry.create(provider_name, config)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Readline history
    history_path = Path.home() / ".config" / "sena" / "chat_history"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        readline.read_history_file(str(history_path))
    except (OSError, FileNotFoundError):
        pass

    memory = SQLiteMemory()
    tools = ToolRegistry()
    tools.register(ShellTool())
    tools.register(BrowserTool())
    tools.register(FileReadTool())
    tools.register(FileWriteTool())
    tools.register(FilePatchTool())
    tools.register(GitTool())
    tools.register(GitHubTool())
    tools.register(FileSearchTool())
    tools.register(WebSearchTool())
    
    # Register MCP tools
    mcp_clients = await register_mcp_tools(tools, config)
    
    slash = SlashRegistry()
    ctx_mgr = ContextManager(provider, model=model)

    # Session cost tracking
    session_usage: dict[str, int] = {"prompt": 0, "completion": 0}

    # Header
    console.print()
    print_banner(console)
    console.print(f"[dim]{provider_name}[/dim] / [bold cyan]{model}[/bold cyan]\n")
    console.print(
        "[dim]Type a message or [bold]exit[/bold] to quit. "
        "Use [bold]/help[/bold] for commands, [bold]![/bold] for shell escape.[/dim]\n"
    )

    system_prompt = _build_system_prompt(config)
    messages: list[Message] = [Message(role="system", content=system_prompt)]

    try:
        while True:
            try:
                user_input = console.input("[bold blue]> [/bold blue]")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye.[/dim]")
                break

            stripped = user_input.strip()
            if stripped.lower() in ("exit", "quit", "/exit", "/quit"):
                console.print("[dim]Goodbye.[/dim]")
                try:
                    readline.write_history_file(str(history_path))
                except OSError:
                    pass
                break

            if not stripped:
                continue

            # Dispatch slash commands before sending to the LLM
            slash_result = slash.dispatch(messages, stripped)
            if slash_result is not None:
                if slash_result.messages is not None:
                    messages = slash_result.messages
                if slash_result.output:
                    console.print(slash_result.output)
                if slash_result.done:
                    console.print("[dim]Goodbye.[/dim]")
                    break
                # After a slash command, skip the LLM turn and print status
                _print_status(model, messages)
                console.print()
                continue

            # Shell escape shortcut
            if stripped.startswith("!"):
                cmd = stripped[1:].strip()
                if cmd:
                    _print_shell_escape(stripped)
                    result = await tools.execute("shell", {"command": cmd})
                    _print_tool("shell", result.content, is_error=result.is_error)
                    # Add to history so agent can see it if next message refers to it
                    messages.append(Message(role="user", content=stripped))
                    messages.append(Message(role="tool", content=result.content, tool_call_id="shell_escape", name="shell"))
                    _print_status(model, messages)
                    console.print()
                    continue
                else:
                    console.print("[dim]Usage: !<command>[/dim]\n")
                    continue

            _print_user(stripped)
            messages.append(Message(role="user", content=user_input))
            await memory.store(user_input, namespace="session")

            # Auto-context compaction before LLM turn
            try:
                messages = await ctx_mgr.prepare(messages, tools=tools.definitions())
            except Exception:
                pass  # Don't block chat if compaction fails

            try:
                await _run_agent_turn(
                    messages, provider, tools, model, config, streaming=streaming
                )
            except Exception as e:
                _print_tool("error", str(e), is_error=True)

            _print_status(model, messages)
            console.print()
    finally:
        # Disconnect MCP clients
        for client in mcp_clients:
            await client.disconnect()


@app.command()
def chat(
    provider: str | None = typer.Option(None, "--provider", "-p", help="LLM provider to use."),
    model: str | None = typer.Option(None, "--model", "-m", help="Model ID to use."),
    no_stream: bool = typer.Option(False, "--no-stream", help="Disable streaming."),
) -> None:
    """Start an interactive chat session with tool use."""
    try:
        asyncio.run(_chat_loop(provider, model, not no_stream))
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
