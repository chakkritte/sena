"""Splash banner for the CarbonClaw terminal interface."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from carbonclaw import __version__

BANNER_LINES = [
    ("  ██████╗ █████╗ ██████╗ ██████╗  ██████╗ ███╗   ██╗", "bold green"),
    (" ██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔═══██╗████╗  ██║", "bold green"),
    (" ██║     ███████║██████╔╝██████╔╝██║   ██║██╔██╗ ██║", "bold green"),
    (" ██║     ██╔══██║██╔══██╗██╔══██╗██║   ██║██║╚██╗██║", "bold green"),
    (" ╚██████╗██║  ██║██║  ██║██████╔╝╚██████╔╝██║ ╚████║", "bold green"),
    ("  ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝  ╚═════╝ ╚═╝  ╚═══╝", "bold green"),
    ("           ██████╗██╗      █████╗ ██╗    ██╗        ", "bold green"),
    ("          ██╔════╝██║     ██╔══██╗██║    ██║        ", "bold green"),
    ("          ██║     ██║     ███████║██║ █╗ ██║        ", "bold green"),
    ("          ██║     ██║     ██╔══██║██║███╗██║        ", "bold green"),
    ("          ╚██████╗███████╗██║  ██║╚███╔███╔╝        ", "bold green"),
    ("           ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝         ", "bold green"),
]


def print_banner(
    console: Console,
    provider: str = "Ollama",
    model: str = "llama3.2",
    endpoint: str = "http://localhost:11434",
    is_local: bool = True,
    carbon_total: float = 0.0,
) -> None:
    """Print the CarbonClaw splash banner with a dynamic status box."""
    banner = Text()
    for line, style in BANNER_LINES:
        banner.append(line + "\n", style=style)

    # Sub-banner slogan
    slogan = Text("\n       ✦ Sustainability. Local-First. Zero Limits. ✦\n", style="bold white")
    
    # Status Box construction
    status_color = "green" if is_local else "blue"
    mode_text = "local" if is_local else "cloud"
    status_msg = f" ● {mode_text}    Ready — type /help to begin"
    
    # Using Table for consistent spacing in the box
    from rich.table import Table
    from rich.box import ROUNDED, DOUBLE_EDGE
    
    info_table = Table(show_header=False, box=None, padding=(0, 1))
    info_table.add_column("Key", style="dim", width=10)
    info_table.add_column("Value", style="bold white")
    
    info_table.add_row("Provider", provider)
    info_table.add_row("Model", model)
    info_table.add_row("Endpoint", endpoint)
    info_table.add_row("Carbon", f"🌱 {carbon_total:.6f} kg CO2" if carbon_total > 0 else "🌱 0.000000 kg CO2")

    # Main layout
    from rich.console import Group
    from rich.rule import Rule
    
    status_group = Group(
        info_table,
        Rule(style="dim"),
        Text(status_msg, style=f"bold {status_color}")
    )
    
    status_panel = Panel(
        status_group,
        border_style="dim",
        padding=(0, 1),
        width=70
    )

    console.print(banner)
    console.print(slogan)
    console.print(status_panel)
    console.print(f"  carbonclaw v{__version__}\n", style="dim")
