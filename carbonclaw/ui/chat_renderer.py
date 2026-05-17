"""Claude Code-style chat renderer for the terminal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from carbonclaw.context.manager import TokenBudget, TokenCounter
from carbonclaw.core.models import Message
from carbonclaw.ui.streaming import StreamingDisplay


@dataclass
class RenderedMessage:
    """A message in the chat history."""

    role: str
    content: str = ""
    streaming: bool = False
    tool_name: str | None = None
    tool_result: str | None = None
    is_error: bool = False
    raw: Message | None = None


class ChatRenderer:
    """Renders a Claude Code-style chat interface without persistent Live display.

    Prints panels directly via ``console.print`` so ``console.input`` continues
    to work normally between turns.
    """

    USER_COLOR = "blue"
    ASSISTANT_COLOR = "green"
    TOOL_COLOR = "yellow"
    SYSTEM_COLOR = "dim"
    ERROR_COLOR = "red"
    BORDER_USER = "blue"
    BORDER_ASSISTANT = "green"
    BORDER_TOOL = "yellow"
    BORDER_ERROR = "red"

    def __init__(
        self,
        console: Console,
        model: str,
        provider: str,
        budget: TokenBudget | None = None,
    ) -> None:
        """Initialize the chat renderer.

        Args:
            console: Rich console instance.
            model: Model name for status display.
            provider: Provider name for status display.
            budget: Optional token budget.
        """
        self.console = console
        self.model = model
        self.provider = provider
        self.budget = budget or TokenBudget()
        self.messages: list[RenderedMessage] = []
        self._current_stream: str = ""
        self._stream_display: StreamingDisplay | None = None

    def __enter__(self) -> ChatRenderer:
        """Enter context — no-op, just returns self."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context — clean up any dangling stream display."""
        if self._stream_display:
            self._stream_display.__exit__(*args)
            self._stream_display = None

    def _token_status(self) -> Text:
        """Build the token usage status text."""
        raw_messages = [m.raw for m in self.messages if m.raw is not None]
        total = TokenCounter.count_messages(raw_messages)
        max_total = self.budget.max_total
        pct = min(100, int((total / max_total) * 100)) if max_total > 0 else 0

        if pct < 60:
            color = "green"
        elif pct < 85:
            color = "yellow"
        else:
            color = "red"

        bar_filled = int(pct / 5)
        bar_empty = 20 - bar_filled
        bar = f"[{'=' * bar_filled}{' ' * bar_empty}]"

        status = Text()
        status.append(f"{self.model}", style="dim cyan")
        status.append(" | ", style="dim")
        status.append(bar, style=color)
        status.append(f" {pct}%", style=color)
        status.append(f" ({total:,}/{max_total:,} tokens)", style="dim")
        return status

    def add_system(self, content: str) -> None:
        """Add a system message."""
        self.messages.append(RenderedMessage(role="system", content=content))

    def add_user(self, content: str, raw: Message | None = None) -> None:
        """Add a user message and print it."""
        self.messages.append(RenderedMessage(role="user", content=content, raw=raw))
        text = Text(content, style=f"bold {self.USER_COLOR}")
        width = min(self.console.width - 2, 100)
        self.console.print(
            Panel(
                text,
                border_style="dim",
                title=" you ",
                title_align="center",
                padding=(0, 2),
                width=width,
            )
        )

    def start_assistant(self, raw: Message | None = None) -> None:
        """Start a new assistant streaming message."""
        self._current_stream = ""
        self.messages.append(
            RenderedMessage(role="assistant", content="", streaming=True, raw=raw)
        )
        self._stream_display = StreamingDisplay(self.console, title=" CarbonClaw ")
        self._stream_display.__enter__()

    def append_stream(self, text: str) -> None:
        """Append streaming text to the current assistant message."""
        self._current_stream += text
        if self.messages and self.messages[-1].role == "assistant":
            self.messages[-1].content = self._current_stream
            self.messages[-1].streaming = True
        if self._stream_display:
            self._stream_display.append(text)

    def pause(self) -> None:
        """Pause the current streaming display to allow console input."""
        if self._stream_display:
            self._stream_display.__exit__(None, None, None)
            self._stream_display = None

    def resume(self) -> None:
        """Resume the streaming display if we were in the middle of a message."""
        if self.messages and self.messages[-1].role == "assistant" and self.messages[-1].streaming:
            self._stream_display = StreamingDisplay(self.console, title=" CarbonClaw ")
            self._stream_display.__enter__()
            self._stream_display.set_text(self._current_stream)

    def set_status(self, text: str) -> None:
        """Update the status of the current stream display."""
        if self._stream_display:
            self._stream_display.set_status(text)

    def end_assistant(self) -> None:

        """Finalize the current assistant streaming message."""
        if self.messages and self.messages[-1].role == "assistant":
            self.messages[-1].streaming = False
            self.messages[-1].content = self._current_stream
        self._current_stream = ""
        if self._stream_display:
            self._stream_display.__exit__(None, None, None)
            self._stream_display = None

    def _get_tool_info(self, name: str) -> tuple[str, str]:
        """Get icon and color for a tool."""
        info = {
            "shell": ("🐚", "bold cyan"),
            "file_write": ("📝", "bold green"),
            "file_patch": ("🔧", "bold green"),
            "file_read": ("📖", "bold blue"),
            "browser": ("🌐", "bold magenta"),
            "git": ("🌿", "bold yellow"),
            "web_search": ("🔍", "bold blue"),
            "planner": ("📋", "bold white"),
        }
        return info.get(name, ("🛠️", "bold white"))

    def add_tool_call(self, name: str, arguments: dict[str, Any] | None = None) -> None:
        """Show a tool call indicator with optional arguments (Compact)."""
        icon, style = self._get_tool_info(name)
        self.messages.append(
            RenderedMessage(
                role="tool",
                content=f"Executing {name}...",
                tool_name=name,
            )
        )
        
        arg_str = ""
        if arguments:
            import json
            # Show a compact preview of arguments
            filtered = {k: v for k, v in arguments.items() if len(str(v)) < 150}
            if filtered:
                # Use a slightly brighter color for better readability (cyan/dim)
                arg_content = json.dumps(filtered)
                arg_str = f" [dim cyan]{arg_content}[/dim cyan]"
        
        self.console.print(f" [dim]──[/dim] {icon} [{style}]{name}[/{style}]{arg_str}")

    def add_tool_result(self, name: str, result: str, is_error: bool = False) -> None:
        """Update or add a tool result and print it with line-based truncation."""
        icon, _ = self._get_tool_info(name)
        
        for msg in reversed(self.messages):
            if (
                msg.role == "tool"
                and msg.tool_name == name
                and msg.tool_result is None
            ):
                msg.tool_result = result
                msg.is_error = is_error
                break
        else:
            self.messages.append(
                RenderedMessage(
                    role="tool",
                    tool_name=name,
                    tool_result=result,
                    is_error=is_error,
                )
            )

        title = f" {icon} {name} "
        if is_error:
            title = f" ❌ {name} "
        
        # Line-based truncation for a cleaner UI
        MAX_LINES = 15
        lines = result.splitlines()
        if len(lines) > MAX_LINES:
            display_lines = lines[:MAX_LINES]
            display = "\n".join(display_lines)
            remaining_lines = len(lines) - MAX_LINES
            remaining_chars = sum(len(line) for line in lines[MAX_LINES:])
            display += (
                f"\n\n[dim italic]... {remaining_lines} more lines ({remaining_chars} chars) omitted. [/dim italic]"
            )
        else:
            # Fallback to character-based truncation if lines are very long
            if len(result) > 5000:
                display = result[:5000] + f"\n\n[dim italic]... {len(result) - 5000} more characters omitted.[/dim italic]"
            else:
                display = result
        
        style = self.ERROR_COLOR if is_error else self.SYSTEM_COLOR
        border = "red" if is_error else "dim"
        width = min(self.console.width - 2, 100)

        # Apply Syntax Highlighting for specific tools
        from rich.syntax import Syntax
        content_renderable = Text(display, style=style)

        if not is_error:
            if name in ("file_read", "file_write"):
                # Try to detect language from messages history or assume based on content
                # For simplicity, we'll use a basic detection or default to python/markdown
                lang = "python"
                for msg in reversed(self.messages):
                    if msg.role == "tool" and msg.tool_name == name and msg.tool_result == result:
                        # Logic to find the path in arguments could go here
                        pass
                content_renderable = Syntax(display, lang, theme="monokai", line_numbers=True, word_wrap=True)
            elif name == "file_patch":
                content_renderable = Syntax(display, "diff", theme="monokai", word_wrap=True)

        self.console.print(
            Panel(
                content_renderable,
                border_style=border,
                title=title,
                title_align="center",
                padding=(0, 2),
                width=width,
            )
        )

    def print_status(self) -> None:
        """Print the token usage status bar."""
        self.console.print(self._token_status())

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()
        self._current_stream = ""
        if self._stream_display:
            self._stream_display.__exit__(None, None, None)
            self._stream_display = None
