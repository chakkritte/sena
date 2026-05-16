"""Claude Code-style chat renderer for the terminal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from sena.context.manager import TokenBudget, TokenCounter
from sena.core.models import Message
from sena.ui.spinners import UnicodeSpinner


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
    """Renders a Claude Code-style persistent chat interface."""

    # Color scheme inspired by Claude Code
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
        self._live: Live | None = None
        self._current_stream: str = ""
        self._tool_spinner: UnicodeSpinner | None = None

    def __enter__(self) -> ChatRenderer:
        """Enter the live display context."""
        self._live = Live(
            self._render(),
            console=self.console,
            transient=False,
            auto_refresh=False,
            refresh_per_second=15,
            vertical_overflow="visible",
        )
        self._live.__enter__()
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit the live display context."""
        if self._live:
            self._live.__exit__(*args)

    def _token_status(self) -> Text:
        """Build the token usage status text."""
        # Count tokens from raw messages if available
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

    def _render_message(self, msg: RenderedMessage, index: int) -> RenderableType:
        """Render a single message based on its role."""
        if msg.role == "user":
            text = Text(msg.content, style=f"bold {self.USER_COLOR}")
            return Panel(
                text,
                border_style=self.BORDER_USER,
                title="[bold]you[/bold]",
                title_align="left",
                padding=(0, 1),
                width=min(self.console.width - 4, 100),
            )

        if msg.role == "system":
            return Panel(
                Text(msg.content, style=self.SYSTEM_COLOR),
                border_style=self.SYSTEM_COLOR,
                title="[dim]system[/dim]",
                title_align="left",
                padding=(0, 1),
            )

        if msg.role == "tool":
            title = f"[bold]{msg.tool_name or 'tool'}[/bold]"
            if msg.is_error:
                title = f"[bold red]{msg.tool_name or 'tool'}[/bold red]"
            content = msg.tool_result or msg.content or ""
            # Truncate long outputs
            display = content[:1200]
            if len(content) > 1200:
                display += f"\n\n[dim]... {len(content) - 1200} more characters[/dim]"
            style = self.ERROR_COLOR if msg.is_error else self.SYSTEM_COLOR
            border = self.BORDER_ERROR if msg.is_error else self.BORDER_TOOL
            return Panel(
                Text(display, style=style),
                border_style=border,
                title=title,
                title_align="left",
                padding=(0, 1),
            )

        if msg.role == "assistant":
            content = msg.content or ""
            if msg.streaming:
                content = content + "[dim]▌[/dim]"

            # Use Markdown for assistant messages, but extract code blocks for syntax highlighting
            renderable: RenderableType
            if content.strip():
                renderable = Markdown(content, code_theme="monokai")
            else:
                renderable = Text("[thinking...]", style="dim italic")

            return Panel(
                renderable,
                border_style=self.BORDER_ASSISTANT,
                title="[bold]Sena[/bold]",
                title_align="left",
                padding=(0, 1),
            )

        return Panel(str(msg.content), title=msg.role)

    def _render(self) -> RenderableType:
        """Render the full chat state."""
        items: list[RenderableType] = []

        # Header
        items.append(
            Rule(
                title=f"[bold]Sena[/bold] [dim]{self.provider} / {self.model}[/dim]",
                align="center",
            )
        )

        # Messages
        for i, msg in enumerate(self.messages):
            items.append(self._render_message(msg, i))

        # Status bar
        items.append(Text(""))
        items.append(self._token_status())

        return Group(*items)

    def _refresh(self) -> None:
        if self._live:
            self._live.update(self._render())

    def add_system(self, content: str) -> None:
        """Add a system message."""
        self.messages.append(RenderedMessage(role="system", content=content))
        self._refresh()

    def add_user(self, content: str, raw: Message | None = None) -> None:
        """Add a user message."""
        self.messages.append(RenderedMessage(role="user", content=content, raw=raw))
        self._refresh()

    def start_assistant(self, raw: Message | None = None) -> None:
        """Start a new assistant streaming message."""
        self._current_stream = ""
        self.messages.append(
            RenderedMessage(role="assistant", content="", streaming=True, raw=raw)
        )
        self._refresh()

    def append_stream(self, text: str) -> None:
        """Append streaming text to the current assistant message."""
        self._current_stream += text
        if self.messages and self.messages[-1].role == "assistant":
            self.messages[-1].content = self._current_stream
            self.messages[-1].streaming = True
        self._refresh()

    def end_assistant(self) -> None:
        """Finalize the current assistant streaming message."""
        if self.messages and self.messages[-1].role == "assistant":
            self.messages[-1].streaming = False
            self.messages[-1].content = self._current_stream
        self._current_stream = ""
        self._refresh()

    def add_tool_call(self, name: str) -> None:
        """Show a tool call indicator."""
        self.messages.append(
            RenderedMessage(
                role="tool",
                content=f"Executing {name}...",
                tool_name=name,
            )
        )
        self._refresh()

    def add_tool_result(self, name: str, result: str, is_error: bool = False) -> None:
        """Update or add a tool result."""
        # Find the last tool message with this name
        for msg in reversed(self.messages):
            if msg.role == "tool" and msg.tool_name == name and msg.tool_result is None:
                msg.tool_result = result
                msg.is_error = is_error
                self._refresh()
                return
        # Or append new
        self.messages.append(
            RenderedMessage(
                role="tool",
                tool_name=name,
                tool_result=result,
                is_error=is_error,
            )
        )
        self._refresh()

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()
        self._current_stream = ""
        self._refresh()
