"""Worker pool command."""

from __future__ import annotations

import asyncio

import typer

from sena.cli.main import app, console


@app.command()
def worker(
    provider: str | None = typer.Option(None, "--provider", "-p"),
    num_workers: int = typer.Option(1, "--num-workers", "-n"),
) -> None:
    """Run a remote agent worker pool."""
    try:
        from sena.workers.pool import run_worker
    except ImportError as e:
        console.print(f"[red]Missing dependency:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[green]Starting {num_workers} worker(s) with provider {provider or 'default'}[/green]")
    try:
        asyncio.run(run_worker(provider=provider, num_workers=num_workers))
    except KeyboardInterrupt:
        console.print("[dim]Worker stopped.[/dim]")
