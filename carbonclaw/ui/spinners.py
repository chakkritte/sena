"""Unicode spinner animations for terminal UI.

Inspired by https://github.com/gunnargray-dev/unicode-animations
Ported from the npm package of the same name.
"""

from __future__ import annotations

import time
from typing import Any

from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text

SPINNERS: dict[str, dict[str, Any]] = {
    "braille": {
        "frames": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        "interval": 80,
    },
    "thinking": {
        "frames": ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"],
        "interval": 80,
    },
    "brailledots": {
        "frames": ["⢀", "⡀", "⠄", "⠂", "⠁", "⠂", "⠄", "⡀"],
        "interval": 100,
    },
    "brailleline": {
        "frames": ["⠁", "⠉", "⠋", "⠛", "⠟", "⠿", "⠻", "⠹", "⠸", "⠘", "⠈"],
        "interval": 80,
    },
    "braillescroll": {
        "frames": ["⠁", "⠂", "⠄", "⡀", "⢀", "⠠", "⠐", "⠈"],
        "interval": 100,
    },
    "blockpulse": {
        "frames": ["▏", "▎", "▍", "▌", "▋", "▊", "▉", "█", "▉", "▊", "▋", "▌", "▍", "▎", "▏"],
        "interval": 80,
    },
    "arrows": {
        "frames": ["←", "↖", "↑", "↗", "→", "↘", "↓", "↙"],
        "interval": 100,
    },
    "moon": {
        "frames": ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"],
        "interval": 200,
    },
    "clock": {
        "frames": ["🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚", "🕛"],
        "interval": 100,
    },
    "earth": {
        "frames": ["🌍", "🌎", "🌏"],
        "interval": 180,
    },
    "runner": {
        "frames": ["🚶", "🏃"],
        "interval": 200,
    },
    "pulse": {
        "frames": ["░", "▒", "▓", "█", "▓", "▒"],
        "interval": 180,
    },
    "dots": {
        "frames": ["⠋", "⠙", "⠚", "⠞", "⠖", "⠦", "⠴", "⠲", "⠐", "⠰"],
        "interval": 80,
    },
    "circle": {
        "frames": ["◐", "◓", "◑", "◒"],
        "interval": 120,
    },
    "triangle": {
        "frames": ["◢", "◣", "◤", "◥"],
        "interval": 100,
    },
}


class UnicodeSpinner:
    """A Rich-renderable Unicode spinner.

    Usage inside a ``rich.live.Live`` display with ``auto_refresh=True``:

        spinner = UnicodeSpinner("braille", text="Loading...")
        with Live(spinner, auto_refresh=True, refresh_per_second=15):
            ...
    """

    def __init__(
        self,
        name: str = "braille",
        text: str = "",
        *,
        style: str = "dim",
        speed: float = 1.0,
    ) -> None:
        """Initialize a Unicode spinner.

        Args:
            name: Spinner key from SPINNERS.
            text: Optional label text shown after the spinner.
            style: Rich style string.
            speed: Playback speed multiplier.
        """
        spec = SPINNERS.get(name)
        if spec is None:
            raise ValueError(f"Unknown spinner: {name}. Available: {', '.join(SPINNERS)}")
        self.frames: list[str] = spec["frames"]
        self.interval = spec["interval"] / 1000.0  # ms -> seconds
        self.text = text
        self.style = style
        self.speed = speed
        self._start = time.monotonic()

    def _current_frame(self) -> str:
        """Return the current animation frame based on elapsed time."""
        elapsed = time.monotonic() - self._start
        index = int((elapsed * self.speed) / self.interval) % len(self.frames)
        return self.frames[index]

    def __rich__(self) -> Text:
        """Return a Rich Text renderable for the current frame."""
        frame = self._current_frame()
        label = f"{frame} {self.text}" if self.text else frame
        return Text(label, style=self.style)

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Yield Rich console segments for the current frame."""
        yield self.__rich__()
