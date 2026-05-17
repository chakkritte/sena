"""Interactive chat command with Claude Code-style UI."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import readline
import tempfile
from pathlib import Path
from typing import Any

import typer

from carbonclaw.cli.main import app, console
from carbonclaw.cli.slash import SlashRegistry
from carbonclaw.config.settings import CarbonClawConfig
from carbonclaw.context.manager import ContextManager
from carbonclaw.core.models import CompletionRequest, Message, ToolCall, StreamChunk
from carbonclaw.memory.sqlite import SQLiteMemory
from carbonclaw.prompts.base import PromptTemplate
from carbonclaw.providers.registry import ProviderRegistry
from carbonclaw.tools.base import ToolRegistry
from carbonclaw.tools.browser import BrowserTool
from carbonclaw.tools.file import FilePatchTool, FileReadTool, FileWriteTool
from carbonclaw.tools.git import GitTool
from carbonclaw.tools.github_cli import GitHubTool
from carbonclaw.tools.mcp import register_mcp_tools
from carbonclaw.tools.search import FileSearchTool
from carbonclaw.tools.shell import ShellTool
from carbonclaw.tools.web_search import WebSearchTool
from carbonclaw.ui.banner import print_banner
from carbonclaw.ui.chat_renderer import ChatRenderer
from carbonclaw.ui.streaming import StreamingDisplay


def _build_system_prompt(config: CarbonClawConfig) -> str:
    from carbonclaw.context.instructions import InstructionTierManager
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
        self._draft_path = Path.home() / ".config" / "carbonclaw" / ".draft"
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


async def _execute_tools_with_approval(
    tool_calls: list[ToolCall],
    tools: ToolRegistry,
    config: CarbonClawConfig,
    renderer: ChatRenderer | None = None,
) -> list[Message]:
    """Execute tools, potentially asking for human approval."""
    from carbonclaw.cli.main import cli_approval_callback

    results = []
    for call in tool_calls:
        # Check if approval is needed
        needs_approval = True
        safe_commands = ["ls", "pwd", "git status", "git diff", "cat", "grep", "find"]
        
        if config.auto_approve_safe_commands and call.name == "shell":
            cmd = call.arguments.get("command", "")
            if any(cmd.startswith(s) for s in safe_commands):
                needs_approval = False
        
        if config.auto_approve_file_writes and call.name in ("file_write", "file_patch"):
            needs_approval = False

        approved = True
        if needs_approval:
            # If we have a renderer, we need to temporarily stop it to show the prompt
            if renderer:
                renderer.pause()
                approved = await cli_approval_callback(call.name, call.arguments)
                renderer.resume()
            else:
                approved = await cli_approval_callback(call.name, call.arguments)

        if approved:
            result = await tools.execute(call.name, call.arguments)
            results.append(
                Message(
                    role="tool",
                    content=result.content,
                    tool_call_id=call.id,
                    name=call.name,
                )
            )
            if renderer:
                renderer.add_tool_result(call.name, result.content)
        else:
            results.append(
                Message(
                    role="tool",
                    content="Action cancelled by user.",
                    tool_call_id=call.id,
                    name=call.name,
                )
            )
            if renderer:
                renderer.add_tool_result(call.name, "Cancelled")
    
    return results


async def _run_agent_turn(
    messages: list[Message],
    provider: Any,
    tools: ToolRegistry,
    model: str,
    config: CarbonClawConfig,
    streaming: bool = True,
    renderer: ChatRenderer | None = None,
) -> None:
    """Run one ReAct turn."""
    from carbonclaw.telemetry.carbon import track_carbon
    
    max_iterations = 10
    with track_carbon("chat_session", enabled=config.carbon_tracking_enabled) as ct:
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
                    with StreamingDisplay(console, title="CarbonClaw") as stream:
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
                response = await provider.complete(request)
                msg = response.message
                if msg.content:
                    content_parts.append(msg.content)
                if msg.tool_calls:
                    tool_calls = msg.tool_calls

            if current_tool is not None:
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

        if config.carbon_tracking_enabled:
            emissions = ct.last_emissions
            if emissions > 0:
                console.print(f"\n[dim]🌱 Turn emissions: {emissions:.6f} kg CO2[/dim]")


async def _chat_loop(
    provider_name: str | None,
    model: str | None,
    streaming: bool,
) -> None:
    config = CarbonClawConfig()
    provider_name = provider_name or config.default_provider
    model = model or config.default_model or "llama3.2"

    try:
        provider = ProviderRegistry.create(provider_name, config)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    # Readline history
    history_path = Path.home() / ".config" / "carbonclaw" / "chat_history"
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
    from carbonclaw.tools.agent import InvokeAgentTool
    from carbonclaw.tools.plan import EnterPlanModeTool
    from carbonclaw.tools.skill import ActivateSkillTool
    from carbonclaw.tools.ui import UpdateTopicTool
    tools.register(InvokeAgentTool(provider, memory, tools.list_tools(), model=model))
    tools.register(ActivateSkillTool())
    tools.register(EnterPlanModeTool())
    tools.register(UpdateTopicTool())

    # Register MCP tools
    mcp_clients = await register_mcp_tools(tools, config)

    from carbonclaw.core.router import SmartRouter, RoutingStrategy
    router = SmartRouter(config)

    slash = SlashRegistry()
    
    async def _cmd_strategy(_messages: list[Message], args: str, _registry: SlashRegistry) -> SlashResult:
        """Change the routing strategy."""
        try:
            strategy = RoutingStrategy(args.strip().lower())
            config.routing_strategy = strategy.value
            return SlashResult(output=f"Routing strategy updated to: [bold green]{strategy.value}[/bold green]")
        except ValueError:
            valid = ", ".join([s.value for s in RoutingStrategy])
            return SlashResult(output=f"[red]Invalid strategy.[/red] Valid: {valid}")

    slash.register("strategy", "Change model routing strategy (sustainability, latency, balanced).", _cmd_strategy)
    
    ctx_mgr = ContextManager(provider, model=model)

    renderer = ChatRenderer(console, model=model, provider=provider_name)
    
    # Determine endpoint and locality
    prov_config = config.get_provider_config(provider_name)
    endpoint = prov_config.base_url or "https://api.anthropic.com" # Default example
    if provider_name.lower() == "openai":
        endpoint = prov_config.base_url or "https://api.openai.com/v1"
    elif provider_name.lower() == "gemini":
        endpoint = "https://generativelanguage.googleapis.com"
    elif provider_name.lower() == "ollama":
        endpoint = prov_config.base_url or "http://localhost:11434"
    
    is_local = provider_name.lower() in ("ollama", "local", "llama.cpp")

    from carbonclaw.telemetry.carbon import CarbonStore
    carbon_total = CarbonStore().total_emissions()

    print_banner(
        console,
        provider=provider_name.capitalize(),
        model=model,
        endpoint=endpoint,
        is_local=is_local,
        carbon_total=carbon_total
    )
    
    console.print(f"Chatting with [bold green]{provider_name}/{model}[/bold green]")
    console.print("[dim]Type /help for commands, !command for shell, or Ctrl+C to exit.[/dim]\n")

    system_prompt = _build_system_prompt(config)
    messages: list[Message] = [Message(role="system", content=system_prompt)]

    try:
        while True:
            try:
                user_input = _read_input(console, draft_manager)
            except EOFError:
                break
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted.[/yellow]")
                break

            if not user_input.strip():
                continue

            # Handle slash commands
            slash_result = await slash.dispatch(messages, user_input)
            if slash_result:
                if slash_result.messages is not None:
                    messages = slash_result.messages
                if slash_result.output:
                    console.print(slash_result.output)
                if slash_result.new_model:
                    model = slash_result.new_model
                if slash_result.done:
                    break
                continue

            # Handle shell escape
            if user_input.startswith("!"):
                cmd = user_input[1:].strip()
                if not cmd:
                    continue
                console.print(f"[dim]Running: {cmd}[/dim]")
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                out = stdout.decode().strip()
                err = stderr.decode().strip()
                combined = f"{out}\n{err}".strip()
                if combined:
                    console.print(combined)
                    messages.append(Message(role="user", content=f"Output of `{cmd}`:\n{combined}"))
                continue

            # Regular message
            messages.append(Message(role="user", content=user_input))
            
            # Dynamic routing if allowed
            active_provider = provider
            active_model = model
            
            if not provider_name or provider_name == "auto":
                strat_name = config.routing_strategy
                try:
                    strat = RoutingStrategy(strat_name)
                except ValueError:
                    strat = RoutingStrategy.SUSTAINABILITY
                
                p_name, m_id = router.route(user_input, messages[:-1], strategy=strat)
                
                curr_p_name = active_provider.__class__.__name__.lower().replace("provider", "")
                if p_name != curr_p_name:
                    try:
                        active_provider = ProviderRegistry.create(p_name, config)
                        active_model = m_id
                        console.print(f"[dim]⚡ Smart routed to [bold]{p_name}/{m_id}[/bold] ({strat_name} strategy)[/dim]")
                    except Exception:
                        pass # Fallback

            # Record history
            with open(history_path, "a", encoding="utf-8") as f:
                f.write(user_input.replace("\n", "\\n") + "\n")

            # Run agent turn
            import time
            start_t = time.time()
            success = True
            try:
                await _run_agent_turn(
                    messages,
                    active_provider,
                    tools,
                    active_model,
                    config,
                    streaming=streaming,
                    renderer=renderer,
                )
            except Exception as e:
                success = False
                raise e
            finally:
                latency = (time.time() - start_t) * 1000
                router.update_metrics(
                    active_provider.__class__.__name__.lower().replace("provider", ""), 
                    latency, 
                    success
                )

    finally:
        # Disconnect MCP clients safely
        if mcp_clients:
            try:
                # Use a shielded task to ensure disconnection attempts aren't cancelled halfway
                async def _cleanup():
                    await asyncio.gather(
                        *(client.disconnect() for client in mcp_clients),
                        return_exceptions=True
                    )
                await asyncio.shield(_cleanup())
            except (asyncio.CancelledError, Exception):
                pass
        
        # Save history
        with contextlib.suppress(OSError):
            readline.write_history_file(str(history_path))


@app.command()
def chat(
    provider: str | None = typer.Option(None, "--provider", "-p", help="LLM provider to use."),
    model: str | None = typer.Option(None, "--model", "-m", help="Model ID to use."),
    no_streaming: bool = typer.Option(False, "--no-streaming", help="Disable real-time streaming."),
) -> None:
    """Start an interactive chat session with CarbonClaw."""
    asyncio.run(_chat_loop(provider, model, not no_streaming))
