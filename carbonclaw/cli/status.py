"""Sustainability and system status dashboard."""

from __future__ import annotations

import asyncio
from datetime import datetime

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

from carbonclaw.cli.main import app
from carbonclaw.config.settings import CarbonClawConfig
from carbonclaw.telemetry.carbon import CarbonStore
from carbonclaw.providers.registry import ProviderRegistry


def make_dashboard(config: CarbonClawConfig, store: CarbonStore) -> Layout:
    """Create the dashboard layout."""
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=3),
    )

    layout["main"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )

    layout["left"].split_column(
        Layout(name="carbon"),
        Layout(name="grid"),
    )

    # Header
    layout["header"].update(
        Panel(
            Text("CarbonClaw Sustainability & Status Dashboard", justify="center", style="bold green"),
            border_style="green",
        )
    )

    # Carbon Stats
    total_emissions = store.total_emissions()
    # Estimate savings: assuming cloud is 5x more carbon intensive for simple tasks
    savings = total_emissions * 4.0 
    
    carbon_table = Table.grid(padding=1)
    carbon_table.add_column(style="bold cyan")
    carbon_table.add_column()
    carbon_table.add_row("Total Emissions:", f"{total_emissions:.6f} kg CO2")
    carbon_table.add_row("Estimated Savings:", f"[green]{savings:.6f} kg CO2[/green]")
    carbon_table.add_row("Equivalent:", f"{total_emissions * 4.0:.2f} km driven by car")

    layout["carbon"].update(
        Panel(carbon_table, title="[bold]Sustainability Metrics[/bold]", border_style="cyan")
    )

    # Grid Intensity (Placeholder for real API)
    grid_progress = Progress(
        TextColumn("{task.description}"),
        BarColumn(bar_width=None),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    )
    grid_progress.add_task("[green]Renewable Share", completed=65)
    grid_progress.add_task("[yellow]Grid Carbon Intensity", completed=32)

    layout["grid"].update(
        Panel(grid_progress, title="[bold]Live Grid Status (Est.)[/bold]", border_style="yellow")
    )

    # Provider Health
    provider_table = Table(title="Provider Performance", box=None)
    provider_table.add_column("Provider")
    provider_table.add_column("Latency")
    provider_table.add_column("Status")

    # In a real app, these would come from SmartRouter's persistent metrics
    provider_table.add_row("Ollama (Local)", "[green]45ms[/green]", "✅")
    provider_table.add_row("Anthropic", "[yellow]850ms[/yellow]", "✅")
    provider_table.add_row("OpenAI", "[red]1200ms[/red]", "⚠️")

    layout["right"].update(
        Panel(provider_table, title="[bold]Agent Infrastructure[/bold]", border_style="magenta")
    )

    # Footer
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    layout["footer"].update(
        Panel(Text(f"Last updated: {now} | Mode: {config.routing_strategy}", justify="center"), border_style="dim")
    )

    return layout


@app.command()
def status(
    live: bool = typer.Option(False, "--live", "-l", help="Run in live update mode."),
) -> None:
    """View the sustainability and system status dashboard."""
    config = CarbonClawConfig()
    store = CarbonStore()
    
    if not live:
        console = Console()
        console.print(make_dashboard(config, store))
        return

    with Live(make_dashboard(config, store), refresh_per_second=1) as live_display:
        try:
            while True:
                import time
                time.sleep(1)
                live_display.update(make_dashboard(config, store))
        except KeyboardInterrupt:
            pass


import typer
from carbonclaw.cli.main import console
