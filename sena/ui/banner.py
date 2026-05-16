"""Splash banner for the Sena terminal interface."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from sena import __version__

BANNER_LINES = [
    ("  ███████╗███████╗███╗   ██╗ █████╗  ", "bold green"),
    ("  ██╔════╝██╔════╝████╗  ██║██╔══██╗ ", "bold green"),
    ("  ███████╗█████╗  ██╔██╗ ██║███████║ ", "bold green"),
    ("  ╚════██║██╔══╝  ██║╚██╗██║██╔══██║ ", "bold green"),
    ("  ███████║███████╗██║ ╚████║██║  ██║ ", "bold green"),
    ("  ╚══════╝╚══════╝╚═╝  ╚═══╝╚═╝  ╚═╝ ", "bold green"),
]


def print_banner(console: Console) -> None:
    """Print the Sena splash banner with version."""
    banner = Text()
    for line, style in BANNER_LINES:
        banner.append(line + "\n", style=style)
    banner.append(f"\n           v{__version__}", style="dim")
    console.print(Panel(banner, border_style="green", padding=(1, 2)))
