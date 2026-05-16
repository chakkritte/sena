"""Configuration management commands."""

from __future__ import annotations

import typer

from sena.cli.main import app, console
from sena.config.settings import SenaConfig


@app.command()
def config(
    key: str | None = typer.Argument(None, help="Config key to get/set."),
    value: str | None = typer.Argument(None, help="Value to set (omit to get)."),
    init: bool = typer.Option(False, "--init", help="Create default user config file."),
) -> None:
    """Get or set Sena configuration."""
    cfg = SenaConfig()

    if init:
        user_dir = cfg.ensure_user_dir()
        config_path = user_dir / "config.toml"
        if not config_path.exists():
            config_path.write_text(
                '# Sena user configuration\n'
                '# default_provider = "ollama"\n'
                '# default_model = "llama3.2"\n'
            )
            console.print(f"[green]Created[/green] {config_path}")
        else:
            console.print(f"[yellow]Already exists[/yellow] {config_path}")
        raise typer.Exit()

    if key is None:
        # Show all config
        for k, v in cfg.model_dump().items():
            if isinstance(v, dict):
                console.print(f"[bold]{k}[/bold]")
                for sub_k, sub_v in v.items():
                    console.print(f"  {sub_k} = {sub_v}")
            else:
                console.print(f"{k} = {v}")
        raise typer.Exit()

    if value is None:
        # Get value
        current = getattr(cfg, key, None)
        if current is None:
            console.print(f"[red]Unknown key:[/red] {key}")
            raise typer.Exit(1)
        console.print(f"{key} = {current}")
        raise typer.Exit()

    # Set value — write to user config TOML
    user_dir = cfg.ensure_user_dir()
    config_path = user_dir / "config.toml"
    lines: list[str] = []
    if config_path.exists():
        lines = config_path.read_text().splitlines()

    # Simple TOML line replacement
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
    console.print(f"[green]Set[/green] {key} = {value}")
