"""Automated self-update command."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from sena.cli.main import app

console = Console()


def _find_sena_repo() -> Path | None:
    """Find the Sena source directory via importlib."""
    spec = importlib.util.find_spec("sena")
    if spec is None or spec.origin is None:
        return None
    # spec.origin points to sena/__init__.py; go up one level to the repo root
    repo = Path(spec.origin).resolve().parent.parent
    if (repo / ".git").exists():
        return repo
    return None


@app.command(name="update")
def update_sena() -> None:
    """Update Sena to the latest version from GitHub."""
    console.print(
        Panel("🚀 [bold blue]Starting Sena Auto-Update[/bold blue]", border_style="blue")
    )

    # 1. Try to auto-discover Sena repo; fall back to current directory
    repo = _find_sena_repo()
    cwd = Path.cwd()
    if repo is None and (cwd / ".git").exists():
        repo = cwd

    if repo is None:
        console.print(
            "[red]Error:[/red] Could not find Sena git repository. "
            "Please run `sena update` from the Sena project directory."
        )
        raise typer.Exit(1)

    if repo != cwd:
        console.print(f"[dim]Switching to {repo} ...[/dim]")
        os.chdir(repo)

    try:
        # 2. Check for local changes
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], text=True
        ).strip()
        if status:
            console.print(
                "[yellow]Warning:[/yellow] You have uncommitted changes."
            )
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
        try:
            subprocess.check_call(["uv", "sync"])
        except (subprocess.CalledProcessError, FileNotFoundError):
            console.print(
                "[yellow]Warning:[/yellow] 'uv sync' failed or uv not found. "
                "Trying 'pip install -e .'..."
            )
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-e", "."]
            )

        console.print(
            Panel(
                "[green]✔ Update successful![/green]\n"
                "Sena is now at the latest version.",
                border_style="green",
            )
        )

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error during update:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        raise typer.Exit(1)
