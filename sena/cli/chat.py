"""Interactive chat command with Claude Code-style UI."""

from __future__ import annotations

import asyncio
import contextlib
import json
import readline
from pathlib import Path
from typing import Any

import typer

from sena.cli.main import app, console
from sena.cli.slash import SlashRegistry
from sena.config.settings import SenaConfig
from sena.context.manager import ContextManager
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
from sena.tools.search import FileSearchTool
from sena.tools.shell import ShellTool
from sena.tools.web_search import WebSearchTool
from sena.ui.banner import print_banner
from sena.ui.chat_renderer import ChatRenderer
from sena.ui.streaming import StreamingDisplay


def _build_system_prompt(config: SenaConfig) -> str:
    from sena.context.instructions import InstructionTierManager
    itm = InstructionTierManager()
    instruction_context = itm.aggregate()

    template = PromptTemplate()
    system_prompt = template.render("system", context={"config": config.model_dump()})

    if instruction_context:
        system_prompt += "\n\nWORKSPACE CONTEXT & INSTRUCTIONS:\n" + instruction_context

    return system_prompt


class DraftManager:
    """Manages draft text preservation across interruptions."""

    def __init__(self) -> None:
        """Initialize draft manager with default path."""
        self._draft_path = Path.home() / ".config" / "sena" / ".draft"
        self._draft: str | None = None

    def save(self, text: str) -> None:
        """Save draft text to disk."""
        self._draft_path.parent.mkdir(parents=True, exist_ok=True)
        self._draft_path.write_text(text, encoding="utf-8")
        self._draft = text

    def load(self) -> str | None:
        """Load draft text from disk."""
        if self._draft is not None:
            return self._draft
        if self._draft_path.exists():
            self._draft = self._draft_path.read_text(encoding="utf-8")
            return self._draft
        return None

    def clear(self) -> None:
        """Clear the current draft."""
        self._draft = None
        if self._draft_path.exists():
            self._draft_path.unlink()


def _read_input(console: Any, draft_manager: DraftManager) -> str:
    r"""Read user input with multi-line support.

    Supports:
    - Backslash continuation (line ending with \)
    - Triple-backtick code block auto-detection
    - Empty line to send multi-line input
    - Draft restoration from previous interruption
    """
    # Restore previous draft if any
    draft = draft_manager.load()
    if draft:
        console.print("[dim]Restored draft (edit or press Enter to send):[/dim]")
        # Pre-fill readline buffer with the draft
        readline.set_startup_hook(lambda: readline.insert_text(draft))
    else:
        readline.set_startup_hook(None)

    try:
        first_line = str(console.input("[bold blue]> [/bold blue]"))
    except KeyboardInterrupt:
        draft_manager.clear()
        readline.set_startup_hook(None)
        raise

    readline.set_startup_hook(None)

    stripped = first_line.strip()

    # If it's a slash command, shell escape, or empty — return as-is (single line)
    if not stripped or stripped.startswith("/") or stripped.startswith("!"):
        draft_manager.clear()
        return first_line

    lines = [first_line]
    in_code_block = stripped.startswith("```")

    while True:
        # Check if we should continue reading
        last_stripped = lines[-1].rstrip()
        continuation = last_stripped.endswith("\\")
        code_block_closed = in_code_block and last_stripped == "```" and len(lines) > 1

        if not continuation and not in_code_block and len(lines) == 1:
            # Single line input — done
            draft_manager.clear()
            return first_line

        if code_block_closed:
            # Remove trailing ``` and return
            draft_manager.clear()
            return "\n".join(lines)

        if continuation:
            # Remove trailing backslash from the last line
            lines[-1] = lines[-1].rstrip()[:-1]

        # Prompt for next line
        try:
            next_line = str(console.input("[dim]... [/dim]"))
        except KeyboardInterrupt:
            # Save partial draft
            draft_manager.save("\n".join(lines))
            raise

        if not next_line.strip() and not in_code_block and not continuation:
            # Empty line in normal multi-line mode — finalize
            draft_manager.clear()
            return "\n".join(lines)

        lines.append(next_line)

        if in_code_block and next_line.strip() == "```":
            # Code block closed
            draft_manager.clear()
            return "\n".join(lines)


async def _execute_tools_with_approval(
    tool_calls: list[ToolCall],
    registry: ToolRegistry,
    config: SenaConfig,
    renderer: ChatRenderer | None = None,
) -> list[Message]:
    """Execute tool calls with optional interactive approval."""
    results: list[Message] = []
    for tc in tool_calls:
        tool = registry.get(tc.name)
        if tool and tool.requires_approval:
            from sena.cli.main import cli_approval_callback
            approved = await cli_approval_callback(tc.name, tc.arguments)
            if not approved:
                if renderer:
                    renderer.add_tool_result(
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
        if renderer:
            renderer.add_tool_result(tc.name, result.content, is_error=result.is_error)
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
    renderer: ChatRenderer | None = None,
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
            if renderer:
                renderer.start_assistant()
                async for chunk in provider.stream(request):
                    if chunk.content:
                        content_parts.append(chunk.content)
                        renderer.append_stream(chunk.content)
                    if chunk.tool_call:
                        tc = chunk.tool_call
                        if tc.is_start:
                            current_tool = {
                                "id": tc.id or "",
                                "name": tc.name or "",
                                "arguments": "",
                            }
                            renderer.add_tool_call(tc.name or "tool")
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
                renderer.end_assistant()
            else:
                # Fallback when no renderer is provided
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
                            elif tc.is_end and current_tool is not None:
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

        if not streaming and assistant_content and renderer:
            renderer.start_assistant()
            renderer.append_stream(assistant_content)
            renderer.end_assistant()

        if not tool_calls:
            break

        result_msgs = await _execute_tools_with_approval(
            tool_calls, tools, config, renderer=renderer
        )
        messages.extend(result_msgs)
    else:
        if renderer:
            renderer.start_assistant()
            renderer.append_stream("Reached maximum tool iterations.")
            renderer.end_assistant()


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
        raise typer.Exit(1) from None

    # Readline history
    history_path = Path.home() / ".config" / "sena" / "chat_history"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError, FileNotFoundError):
        readline.read_history_file(str(history_path))
    # Enable native Ctrl+R reverse search
    with contextlib.suppress(Exception):
        readline.parse_and_bind(r'"\C-r": reverse-search-history')

    draft_manager = DraftManager()
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

    # Advanced Tools
    from sena.tools.agent import InvokeAgentTool
    from sena.tools.plan import EnterPlanModeTool
    from sena.tools.skill import ActivateSkillTool
    from sena.tools.ui import UpdateTopicTool
    tools.register(InvokeAgentTool(provider, memory, tools.list_tools(), model=model))
    tools.register(ActivateSkillTool())
    tools.register(EnterPlanModeTool())
    tools.register(UpdateTopicTool())

    # Register MCP tools
    mcp_clients = await register_mcp_tools(tools, config)

    slash = SlashRegistry()
    ctx_mgr = ContextManager(provider, model=model)

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

    # Load session history from memory
    try:
        # Retrieve last 20 messages (reverse chronological, so we reverse it back)
        past_entries = await memory.retrieve("", namespace="session", limit=20)
        for entry in reversed(past_entries):
            try:
                data = json.loads(entry.content)
                messages.append(Message(role=data["role"], content=data["content"]))
            except (json.JSONDecodeError, KeyError):
                # Fallback for old simple text entries
                messages.append(Message(role="user", content=entry.content))
        if len(past_entries) > 0:
            console.print(f"[dim]Loaded {len(past_entries)} messages from history.[/dim]\n")
    except Exception:
        pass

    renderer = ChatRenderer(console, model=model, provider=provider_name)

    try:
        with renderer:
            while True:
                try:
                    user_input = _read_input(console, draft_manager)
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[dim]Goodbye.[/dim]")
                    break

                stripped = user_input.strip()

                # Interactive slash command selection
                if stripped == "/":
                    from rich.prompt import Prompt

                    cmds = slash._commands
                    unique_cmds = {}
                    for c in cmds.values():
                        unique_cmds[c.name] = c

                    options = sorted(unique_cmds.keys())
                    choices_str = ", ".join([f"[cyan]/{o}[/cyan]" for o in options])
                    console.print(f"[dim]Available commands:[/dim] {choices_str}")

                    cmd_name = Prompt.ask(
                        "Select command",
                        choices=options,
                        show_choices=False,
                    )
                    user_input = f"/{cmd_name}"
                    stripped = user_input
                    renderer.add_user(user_input)

                if stripped.lower() in ("exit", "quit", "/exit", "/quit"):
                    console.print("[dim]Goodbye.[/dim]")
                    break

                if not stripped:
                    continue

                # Add to readline history for arrow key support
                readline.add_history(user_input)
                with contextlib.suppress(OSError):
                    readline.write_history_file(str(history_path))

                # Dispatch slash commands before sending to the LLM
                slash_result = await slash.dispatch(messages, stripped)
                if slash_result is not None:
                    if slash_result.messages is not None:
                        messages = slash_result.messages
                        # If messages were cleared (only system remains), clear renderer too
                        if len(messages) <= 1:
                            renderer.clear()
                    if slash_result.output:
                        console.print(slash_result.output)
                    if slash_result.new_model:
                        model = slash_result.new_model
                        # Re-create provider if model or provider changed
                        provider = ProviderRegistry.create(config.default_provider, config)
                        ctx_mgr = ContextManager(provider, model=model)
                        # Update renderer model reference
                        renderer.model = model
                    if slash_result.done:
                        console.print("[dim]Goodbye.[/dim]")
                        break
                    continue

                # Shell escape shortcut
                if stripped.startswith("!"):
                    cmd = stripped[1:].strip()
                    if cmd:
                        renderer.add_user(f"$ {cmd}")
                        result = await tools.execute("shell", {"command": cmd})
                        renderer.add_tool_result("shell", result.content, is_error=result.is_error)
                        # Add to history so agent can see it if next message refers to it
                        messages.append(Message(role="user", content=stripped))
                        messages.append(
                            Message(
                                role="tool",
                                content=result.content,
                                tool_call_id="shell_escape",
                                name="shell",
                            )
                        )
                        continue
                    else:
                        console.print("[dim]Usage: !<command>[/dim]\n")
                        continue

                renderer.add_user(user_input)
                messages.append(Message(role="user", content=user_input))
                await memory.store(
                    json.dumps({"role": "user", "content": user_input}),
                    namespace="session",
                )

                # Auto-context compaction before LLM turn
                with contextlib.suppress(Exception):
                    messages = await ctx_mgr.prepare(
                        messages, tools=tools.definitions()
                    )

                try:
                    # We need to capture the assistant's response to store it
                    # The current _run_agent_turn appends directly to messages
                    start_idx = len(messages)
                    await _run_agent_turn(
                        messages,
                        provider,
                        tools,
                        model,
                        config,
                        streaming=streaming,
                        renderer=renderer,
                    )
                    # Store all new assistant/tool messages
                    for i in range(start_idx, len(messages)):
                        msg = messages[i]
                        if msg.content:
                            await memory.store(
                                json.dumps({"role": msg.role, "content": msg.content}),
                                namespace="session",
                            )
                except Exception as e:
                    renderer.add_tool_result("error", str(e), is_error=True)
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
