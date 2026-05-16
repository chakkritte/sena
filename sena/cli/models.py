"""List available models."""

from __future__ import annotations

import asyncio

import typer
from rich.table import Table

from sena.cli.main import app, console
from sena.config.settings import SenaConfig
from sena.providers.registry import ProviderRegistry


@app.command()
def models(
    provider: str | None = typer.Option(None, "--provider", "-p", help="Provider to list models for."),
) -> None:
    """List available models for a provider."""
    config = SenaConfig()
    provider_name = provider or config.default_provider

    try:
        p = ProviderRegistry.create(provider_name, config)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    async def _list() -> None:
        model_ids = await p.list_models()
        if not model_ids:
            console.print(f"[yellow]No models found for {provider_name}.[/yellow]")
            return
        table = Table(title=f"Models — {provider_name}")
        table.add_column("Model ID", style="cyan")
        for m in model_ids:
            table.add_row(m)
        console.print(table)

    asyncio.run(_list())
