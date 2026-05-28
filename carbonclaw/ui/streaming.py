"""Streaming text display for assistant responses."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

from carbonclaw.ui.spinners import UnicodeSpinner


class StreamingDisplay:
    """Displays a streaming assistant message with live updates."""

    def __init__(self, console: Console, title: str = "CarbonClaw") -> None:
        """Initialize the streaming display.

        Args:
            console: Rich console instance.
            title: Panel title.
        """
        self.console = console
        self.title = title
        self._text = ""
        self._live: Live | None = None
        self._spinner = UnicodeSpinner("thinking", text="Thinking...", style="dim")

    def __enter__(self) -> StreamingDisplay:
        """Enter the live display context."""
        self._live = Live(
            self._render(),
            console=self.console,
            transient=False,
            auto_refresh=True,
            refresh_per_second=15,
        )
        self._live.__enter__()
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit the live display context."""
        if self._live:
            self._live.__exit__(*args)

    def set_status(self, text: str) -> None:
        """Update the status text of the spinner."""
        self._spinner.text = text
        if self._live:
            self._live.update(self._render())

    def _render(self) -> Any:
        if not self._text:
            return self._spinner
            
        content = Markdown(self._text, code_theme="monokai")
        width = min(self.console.width - 2, 100)
        return Panel(
            content,
            border_style="dim",
            title=f" {self.title} ",
            title_align="center",
            padding=(0, 2),
            width=width,
        )

    def append(self, text: str) -> None:
        """Append text and refresh the live display."""
        self._text += text
        if self._live:
            self._live.update(self._render())

    def set_text(self, text: str) -> None:
        """Replace text and refresh the live display."""
        self._text = text
        if self._live:
            self._live.update(self._render())

    def finalize(self) -> Panel:
        """Return the final panel and stop the live display."""
        self.__exit__(None, None, None)
        return self._render()
