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
        self.console.print(
            Panel(
                text,
                border_style=self.BORDER_USER,
                title="[bold]you[/bold]",
                title_align="left",
                padding=(0, 1),
                width=min(self.console.width - 4, 100),
            )
        )

    def start_assistant(self, raw: Message | None = None) -> None:
        """Start a new assistant streaming message."""
        self._current_stream = ""
        self.messages.append(
            RenderedMessage(role="assistant", content="", streaming=True, raw=raw)
        )
        self._stream_display = StreamingDisplay(self.console, title="CarbonClaw")
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
            self._stream_display = StreamingDisplay(self.console, title="CarbonClaw")
            self._stream_display.__enter__()
            self._stream_display.set_text(self._current_stream)

    def end_assistant(self) -> None:
        """Finalize the current assistant streaming message."""
        if self.messages and self.messages[-1].role == "assistant":
            self.messages[-1].streaming = False
            self.messages[-1].content = self._current_stream
        self._current_stream = ""
        if self._stream_display:
            self._stream_display.__exit__(None, None, None)
            self._stream_display = None

    def add_tool_call(self, name: str) -> None:
        """Show a tool call indicator."""
        self.messages.append(
            RenderedMessage(
                role="tool",
                content=f"Executing {name}...",
                tool_name=name,
            )
        )

    def add_tool_result(self, name: str, result: str, is_error: bool = False) -> None:
        """Update or add a tool result and print it."""
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

        title = f"[bold]{name}[/bold]"
        if is_error:
            title = f"[bold red]{name}[/bold red]"
        display = result[:1200]
        if len(result) > 1200:
            display += (
                f"\n\n[dim]... {len(result) - 1200} more characters[/dim]"
            )
        style = self.ERROR_COLOR if is_error else self.SYSTEM_COLOR
        border = self.BORDER_ERROR if is_error else self.BORDER_TOOL
        self.console.print(
            Panel(
                Text(display, style=style),
                border_style=border,
                title=title,
                title_align="left",
                padding=(0, 1),
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
