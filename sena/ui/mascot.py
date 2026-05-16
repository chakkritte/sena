"""Sena mascot animation — Hanuman in Thai Ancient Boxing (Muay Thai / Ram Muay)."""

from __future__ import annotations

import time
from typing import Any

from rich.console import Console, ConsoleOptions, RenderResult
from rich.panel import Panel
from rich.text import Text


# Hanuman Thai Boxing mascot — right-facing walk cycle with stepping poses
# Each frame shows a distinct step in the walk for smooth animation
HANUMAN_WALK_RIGHT: list[list[str]] = [
    # Frame 0: Left leg forward, arms balanced
    [
        "           ♛  ╭─╮╭─╮╭─╮╭─╮  ♛      ",
        "           ⚔  │S││E││N││A│  ⚔      ",
        "              ╰─╯╰─╯╰─╯╰─╯         ",
        "              ╭─────────╮          ",
        "             ╱ ◕       ◕ ╲         ",
        "            │     ▽       │        ",
        "            │  ╭───────╮  │        ",
        "             ╰─┤ ●   ● ├─╯         ",
        "               │╭───╮│             ",
        "            ╭──┤│███│├──╮          ",
        "           ╱   ││███││   ╲         ",
        "          ◞    ││███││    ◟        ",
        "               ││   ││             ",
        "               ││   ││             ",
        "              ◝││   ││◜            ",
        "             ◟ ◜     ◝ ◞           ",
        "                ╰───╯              ",
        "                 ◟◞                ",
    ],
    # Frame 1: Transition — weight shifting
    [
        "            ♛ ╭─╮╭─╮╭─╮╭─╮ ♛       ",
        "            ⚔ │S││E││N││A│ ⚔       ",
        "              ╰─╯╰─╯╰─╯╰─╯         ",
        "              ╭─────────╮          ",
        "             ╱ ◕       ◕ ╲         ",
        "            │     ▽       │        ",
        "            │  ╭───────╮  │        ",
        "             ╰─┤ ●   ● ├─╯         ",
        "               │╭───╮│             ",
        "           ╭───┤│███│├───╮         ",
        "          ╱    ││███││    ╲        ",
        "         ◞     ││███││     ◟       ",
        "               ││   ││             ",
        "               ││   ││             ",
        "              ◝││   ││◜            ",
        "             ◟ ◜     ◝ ◞           ",
        "                ╰───╯              ",
        "                 ◟◞                ",
    ],
    # Frame 2: Right leg forward
    [
        "           ♛  ╭─╮╭─╮╭─╮╭─╮  ♛      ",
        "           ⚔  │S││E││N││A│  ⚔      ",
        "              ╰─╯╰─╯╰─╯╰─╯         ",
        "              ╭─────────╮          ",
        "             ╱ ◕       ◕ ╲         ",
        "            │     ▽       │        ",
        "            │  ╭───────╮  │        ",
        "             ╰─┤ ●   ● ├─╯         ",
        "               │╭───╮│             ",
        "            ╭──┤│███│├──╮          ",
        "           ╱   ││███││   ╲         ",
        "          ◞    ││███││    ◟        ",
        "               ││   ││             ",
        "               ││   ││             ",
        "              ◜││   ││◝            ",
        "             ◞ ◝     ◜ ◟           ",
        "                ╰───╯              ",
        "                 ◟◞                ",
    ],
    # Frame 3: Transition back
    [
        "            ♛ ╭─╮╭─╮╭─╮╭─╮ ♛       ",
        "            ⚔ │S││E││N││A│ ⚔       ",
        "              ╰─╯╰─╯╰─╯╰─╯         ",
        "              ╭─────────╮          ",
        "             ╱ ◕       ◕ ╲         ",
        "            │     ▽       │        ",
        "            │  ╭───────╮  │        ",
        "             ╰─┤ ●   ● ├─╯         ",
        "               │╭───╮│             ",
        "           ╭───┤│███│├───╮         ",
        "          ╱    ││███││    ╲        ",
        "         ◞     ││███││     ◟       ",
        "               ││   ││             ",
        "               ││   ││             ",
        "              ◜││   ││◝            ",
        "             ◞ ◝     ◜ ◟           ",
        "                ╰───╯              ",
        "                 ◟◞                ",
    ],
]

# Hanuman walk-cycle: left-facing frames (mirrored with A N E S)
HANUMAN_WALK_LEFT: list[list[str]] = [
    # Frame 0
    [
        "           ♛  ╭─╮╭─╮╭─╮╭─╮  ♛      ",
        "           ⚔  │A││N││E││S│  ⚔      ",
        "              ╰─╯╰─╯╰─╯╰─╯         ",
        "              ╭─────────╮          ",
        "             ╱ ◕       ◕ ╲         ",
        "            │     ▽       │        ",
        "            │  ╭───────╮  │        ",
        "             ╰─┤ ●   ● ├─╯         ",
        "               │╭───╮│             ",
        "            ╭──┤│███│├──╮          ",
        "           ╱   ││███││   ╲         ",
        "          ◞    ││███││    ◟        ",
        "               ││   ││             ",
        "               ││   ││             ",
        "              ◝││   ││◜            ",
        "             ◟ ◜     ◝ ◞           ",
        "                ╰───╯              ",
        "                 ◟◞                ",
    ],
    # Frame 1
    [
        "            ♛ ╭─╮╭─╮╭─╮╭─╮ ♛       ",
        "            ⚔ │A││N││E││S│ ⚔       ",
        "              ╰─╯╰─╯╰─╯╰─╯         ",
        "              ╭─────────╮          ",
        "             ╱ ◕       ◕ ╲         ",
        "            │     ▽       │        ",
        "            │  ╭───────╮  │        ",
        "             ╰─┤ ●   ● ├─╯         ",
        "               │╭───╮│             ",
        "           ╭───┤│███│├───╮         ",
        "          ╱    ││███││    ╲        ",
        "         ◞     ││███││     ◟       ",
        "               ││   ││             ",
        "               ││   ││             ",
        "              ◝││   ││◜            ",
        "             ◟ ◜     ◝ ◞           ",
        "                ╰───╯              ",
        "                 ◟◞                ",
    ],
    # Frame 2
    [
        "           ♛  ╭─╮╭─╮╭─╮╭─╮  ♛      ",
        "           ⚔  │A││N││E││S│  ⚔      ",
        "              ╰─╯╰─╯╰─╯╰─╯         ",
        "              ╭─────────╮          ",
        "             ╱ ◕       ◕ ╲         ",
        "            │     ▽       │        ",
        "            │  ╭───────╮  │        ",
        "             ╰─┤ ●   ● ├─╯         ",
        "               │╭───╮│             ",
        "            ╭──┤│███│├──╮          ",
        "           ╱   ││███││   ╲         ",
        "          ◞    ││███││    ◟        ",
        "               ││   ││             ",
        "               ││   ││             ",
        "              ◜││   ││◝            ",
        "             ◞ ◝     ◜ ◟           ",
        "                ╰───╯              ",
        "                 ◟◞                ",
    ],
    # Frame 3
    [
        "            ♛ ╭─╮╭─╮╭─╮╭─╮ ♛       ",
        "            ⚔ │A││N││E││S│ ⚔       ",
        "              ╰─╯╰─╯╰─╯╰─╯         ",
        "              ╭─────────╮          ",
        "             ╱ ◕       ◕ ╲         ",
        "            │     ▽       │        ",
        "            │  ╭───────╮  │        ",
        "             ╰─┤ ●   ● ├─╯         ",
        "               │╭───╮│             ",
        "           ╭───┤│███│├───╮         ",
        "          ╱    ││███││    ╲        ",
        "         ◞     ││███││     ◟       ",
        "               ││   ││             ",
        "               ││   ││             ",
        "              ◜││   ││◝            ",
        "             ◞ ◝     ◜ ◟           ",
        "                ╰───╯              ",
        "                 ◟◞                ",
    ],
]


def mascot_banner() -> str:
    """Return a static multi-line Hanuman mascot string for the banner."""
    lines = [
        "            ♛ ╭─╮╭─╮╭─╮╭─╮ ♛       ",
        "            ⚔ │S││E││N││A│ ⚔       ",
        "              ╰─╯╰─╯╰─╯╰─╯         ",
        "              ╭─────────╮          ",
        "             ╱ ◕       ◕ ╲         ",
        "            │     ▽       │        ",
        "            │  ╭───────╮  │        ",
        "             ╰─┤ ●   ● ├─╯         ",
        "               │╭───╮│             ",
        "               ││███││             ",
        "              ╱││███││╲            ",
        "             ◞ ││███││ ◟           ",
        "               ││   ││             ",
        "               ││   ││             ",
        "              ╱ │   │ ╲            ",
        "             ◟  ◜   ◝  ◞           ",
        "                ╰───╯              ",
        "                 ◟◞                ",
    ]
    return "\n".join(lines)


class MascotAnimation:
    """Rich-renderable Hanuman mascot that walks back and forth.

    Usage inside a ``rich.live.Live`` display::

        mascot = MascotAnimation(direction="right")
        with Live(mascot, auto_refresh=True, refresh_per_second=8):
            ...
    """

    def __init__(
        self,
        direction: str = "right",
        *,
        style: str = "bold green",
        speed: float = 1.0,
    ) -> None:
        """Initialize the mascot animation.

        Args:
            direction: Initial walking direction ("right" or "left").
            style: Rich style string.
            speed: Playback speed multiplier.
        """
        self.direction = direction
        self.style = style
        self.speed = speed
        self._start = time.monotonic()
        self._cycle_seconds = 4.0  # full left-right-left cycle

    def _current_frame(self) -> str:
        """Return the current multi-line mascot frame."""
        elapsed = time.monotonic() - self._start
        cycle_pos = (elapsed * self.speed) % self._cycle_seconds
        half = self._cycle_seconds / 2

        if cycle_pos < half:
            frames = HANUMAN_WALK_RIGHT
            progress = cycle_pos / half
        else:
            frames = HANUMAN_WALK_LEFT
            progress = (cycle_pos - half) / half

        index = min(int(progress * len(frames)), len(frames) - 1)
        return "\n".join(frames[index])

    def __rich__(self) -> Text:
        """Return a Rich Text renderable for the current frame."""
        return Text(self._current_frame(), style=self.style)

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Yield Rich console segments for the current frame."""
        yield self.__rich__()


def print_mascot_banner(console: Console) -> None:
    """Print a banner panel containing the static Hanuman mascot."""
    console.print(Panel(mascot_banner(), border_style="green", padding=(0, 2)))
