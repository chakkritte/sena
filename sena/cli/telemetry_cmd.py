"""Telemetry CLI: view and manage usage records."""

from __future__ import annotations

import typer
from rich.table import Table

from sena.cli.main import app, console
from sena.telemetry.store import TelemetryStore


@app.command()
def telemetry(
    clear: bool = typer.Option(False, "--clear", help="Clear all telemetry records."),
) -> None:
    """Show aggregated LLM usage telemetry."""
    store = TelemetryStore()

    if clear:
        store.clear()
        console.print("[dim]Telemetry cleared.[/dim]")
        return

    summary = store.summary()
    if summary["total_requests"] == 0:
        console.print("[dim]No telemetry records found.[/dim]")
        return

    console.print(f"[bold]Total requests:[/bold] {summary['total_requests']}")
    console.print(
        f"[bold]Total tokens:[/bold] {summary['total_tokens']:,} "
        f"({summary['total_prompt_tokens']:,} prompt / "
        f"{summary['total_completion_tokens']:,} completion)"
    )

    table = Table(title="Usage by Model", show_header=True)
    table.add_column("Model", style="bold cyan")
    table.add_column("Requests", justify="right")
    table.add_column("Prompt Tokens", justify="right")
    table.add_column("Completion Tokens", justify="right")
    table.add_column("Total Tokens", justify="right")

    for model, stats in summary["by_model"].items():
        table.add_row(
            model,
            str(stats["requests"]),
            f"{stats['prompt']:,}",
            f"{stats['completion']:,}",
            f"{stats['prompt'] + stats['completion']:,}",
        )
    console.print(table)
