"""Automated self-update command."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from sena.cli.main import app

console = Console()

@app.command(name="update")
def update_sena() -> None:
    """Update Sena to the latest version from GitHub."""
    console.print(Panel("🚀 [bold blue]Starting Sena Auto-Update[/bold blue]", border_style="blue"))
    
    # 1. Verify we are in a git repository
    if not Path(".git").exists():
        console.print("[red]Error:[/red] Not a git repository. Cannot update automatically.")
        raise typer.Exit(1)

    try:
        # 2. Check for local changes
        status = subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        if status:
            console.print("[yellow]Warning:[/yellow] You have uncommitted changes.")
            confirm = typer.confirm("Stash changes and proceed with update?")
            if not confirm:
                console.print("Update cancelled.")
                raise typer.Exit()
            console.print("Stashing changes...")
            subprocess.check_call(["git", "stash"])

        # 3. Pull latest changes
        console.print("Pulling latest changes from [bold]main[/bold]...")
        subprocess.check_call(["git", "pull", "origin", "main"])

        # 4. Sync dependencies
        console.print("Syncing dependencies with [bold]uv[/bold]...")
        # We assume uv is installed as it's the primary way to manage the project
        try:
            subprocess.check_call(["uv", "sync"])
        except (subprocess.CalledProcessError, FileNotFoundError):
            console.print("[yellow]Warning:[/yellow] 'uv sync' failed or uv not found. Trying 'pip install -e .'...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", "."])

        console.print(Panel("[green]✔ Update successful![/green]\nSena is now at the latest version.", border_style="green"))

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error during update:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        raise typer.Exit(1)
