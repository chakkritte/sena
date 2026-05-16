"""Interactive model selection wizard."""

from __future__ import annotations

import asyncio
from typing import Any

import typer
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

from sena.cli.main import app, console
from sena.config.settings import SenaConfig
from sena.providers.registry import ProviderRegistry


async def _get_models(provider_name: str, config: SenaConfig) -> list[str]:
    try:
        p = ProviderRegistry.create(provider_name, config)
        return await p.list_models()
    except Exception as e:
        console.print(f"[red]Error fetching models for {provider_name}:[/red] {e}")
        return []


def _update_config(key: str, value: str) -> None:
    config = SenaConfig()
    user_dir = config.ensure_user_dir()
    config_path = user_dir / "config.toml"
    
    lines: list[str] = []
    if config_path.exists():
        lines = config_path.read_text().splitlines()

    new_line = f'{key} = {repr(value)}'
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key} ="):
            lines[i] = new_line
            found = True
            break
    if not found:
        lines.append(new_line)

    config_path.write_text("\n".join(lines) + "\n")
    console.print(f"[green]✔ Updated {key} to {value}[/green]")


@app.command()
def models(
    provider: str | None = typer.Option(None, "--provider", "-p", help="Provider to list models for."),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", help="Enable or disable wizard mode."),
) -> None:
    """List and configure models via an interactive wizard."""
    config = SenaConfig()

    if not interactive or provider:
        # Non-interactive mode (existing behavior)
        provider_name = provider or config.default_provider
        async def _list() -> None:
            model_ids = await _get_models(provider_name, config)
            if not model_ids:
                return
            table = Table(title=f"Models — {provider_name}")
            table.add_column("Model ID", style="cyan")
            for m in model_ids:
                table.add_row(m)
            console.print(table)
        asyncio.run(_list())
        return

    # Interactive Wizard Mode
    console.print(Panel("🤖 [bold blue]Sena Model Wizard[/bold blue]", border_style="blue"))
    
    # 1. Select Provider
    providers = ProviderRegistry.available()
    console.print(f"\nAvailable providers: [cyan]{', '.join(providers)}[/cyan]")
    selected_provider = Prompt.ask(
        "Select a provider",
        choices=providers,
        default=config.default_provider,
    )

    # 2. Fetch and Select Model
    console.print(f"Fetching models for [bold]{selected_provider}[/bold]...")
    model_ids = asyncio.run(_get_models(selected_provider, config))
    
    if not model_ids:
        console.print(f"[yellow]No models returned for {selected_provider}.[/yellow]")
        selected_model = Prompt.ask("Enter model ID manually")
    else:
        # Show table first
        table = Table(title=f"Available Models — {selected_provider}")
        table.add_column("ID", style="cyan")
        for m in model_ids:
            table.add_row(m)
        console.print(table)
        
        selected_model = Prompt.ask(
            "Select a model ID",
            choices=model_ids,
            default=model_ids[0] if model_ids else "",
        )

    # 3. Apply changes
    console.print(f"\nYou selected: [bold green]{selected_provider} / {selected_model}[/bold green]")
    
    if Confirm.ask("Set as default provider and model?"):
        _update_config("default_provider", selected_provider)
        _update_config("default_model", selected_model)
        console.print("\n[bold green]Configuration updated successfully![/bold green]")
    else:
        console.print("\n[dim]No changes made to configuration.[/dim]")
