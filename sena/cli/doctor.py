"""System health and diagnostics."""

from __future__ import annotations

import asyncio
import shutil
import sys

from rich.table import Table

from sena.cli.main import app, console
from sena.config.settings import SenaConfig
from sena.providers.registry import ProviderRegistry


async def _check_provider(name: str, config: SenaConfig) -> tuple[str, str, str]:
    try:
        provider = ProviderRegistry.create(name, config)
        healthy = await provider.health()
        status = "[green]OK[/green]" if healthy else "[red]Unavailable[/red]"
        detail = f"Models: {len(await provider.list_models())}"
    except Exception as e:
        status = "[red]Error[/red]"
        detail = str(e)[:60]
    return name, status, detail


@app.command()
def doctor() -> None:
    """Check system health and provider connectivity."""
    console.print("[bold]Sena Doctor[/bold] — System diagnostics\n")

    # Python version
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 12)
    console.print(
        f"Python: {py_version} {'[green]OK[/green]' if py_ok else '[red]<3.12 required[/red]' }"
    )

    # External tools
    for cmd, label in [("git", "Git"), ("docker", "Docker"), ("uv", "uv")]:
        path = shutil.which(cmd)
        status = f"[green]{path}[/green]" if path else "[yellow]not found[/yellow]"
        console.print(f"{label}: {status}")

    # Providers
    config = SenaConfig()
    console.print("\n[bold]Providers[/bold]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Provider")
    table.add_column("Status")
    table.add_column("Detail")

    async def _check_all() -> None:
        for name in ProviderRegistry.available():
            creds = config.get_provider_config(name)
            has_key = bool(creds.api_key) or name == "ollama"
            if not has_key:
                table.add_row(name, "[dim]No API key[/dim]", "")
                continue
            _, status, detail = await _check_provider(name, config)
            table.add_row(name, status, detail)

    asyncio.run(_check_all())
    console.print(table)
