"""Streaming text display for assistant responses."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

from sena.ui.spinners import UnicodeSpinner


class StreamingDisplay:
    """Displays a streaming assistant message with live updates."""

    def __init__(self, console: Console, title: str = "Sena") -> None:
        """Initialize the streaming display.

        Args:
            console: Rich console instance.
            title: Panel title.
        """
        self.console = console
        self.title = title
        self._text = ""
        self._live: Live | None = None
        self._spinner = UnicodeSpinner("braille", text="Thinking...", style="dim")

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

    def _render(self) -> Panel:
        content = Markdown(self._text, code_theme="monokai") if self._text else self._spinner
        return Panel(
            content,
            border_style="green",
            title=f"[bold]{self.title}[/bold]",
            title_align="left",
            padding=(0, 1),
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
