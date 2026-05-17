"""Terminal status bar for CarbonClaw chat."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from carbonclaw.telemetry.carbon import CarbonStore
from carbonclaw.context.manager import TokenCounter

if TYPE_CHECKING:
    from carbonclaw.core.models import Message


def get_git_branch() -> str:
    """Get the current git branch name."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
    except Exception:
        return "n/a"


def get_short_path() -> str:
    """Get the current working directory, shortened with ~."""
    cwd = os.getcwd()
    home = str(Path.home())
    if cwd.startswith(home):
        return cwd.replace(home, "~", 1)
    return cwd


def render_status_bar(
    model: str,
    provider: str,
    messages: list[Message],
    max_tokens: int = 128000
) -> Panel:
    """Render a professional status bar as a Rich Panel."""
    # 1. Workspace & Branch
    path = get_short_path()
    branch = get_git_branch()
    
    # 2. Carbon
    store = CarbonStore()
    total_carbon = store.total_emissions()
    
    # 3. Context Usage
    current_tokens = TokenCounter.count_messages(messages)
    usage_pct = int((current_tokens / max_tokens) * 100) if max_tokens > 0 else 0
    
    # Color logic for usage
    usage_color = "green"
    if usage_pct > 80:
        usage_color = "red"
    elif usage_pct > 50:
        usage_color = "yellow"

    # Build the table
    table = Table.grid(expand=True)
    table.add_column(justify="left", style="dim", ratio=1)
    table.add_column(justify="center", style="dim", ratio=1)
    table.add_column(justify="center", style="dim", ratio=1)
    table.add_column(justify="center", style="dim", ratio=1)
    table.add_column(justify="right", style="dim", ratio=1)

    table.add_row(
        Text.from_markup(f" 📂 [white]{path}[/white]"),
        Text.from_markup(f" 🌿 [cyan]{branch}[/cyan]"),
        Text.from_markup(f" 🌱 [bold green]{total_carbon:.4f} kg CO2[/bold green]"),
        Text.from_markup(f" 🤖 [bold white]{provider}/{model}[/bold white]"),
        Text.from_markup(f" 🧠 [{usage_color}]{usage_pct}% used[/{usage_color}] "),
    )

    return Panel(
        table,
        border_style="dim",
        padding=(0, 0),
        height=3
    )
