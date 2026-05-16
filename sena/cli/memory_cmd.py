"""Memory management commands."""

from __future__ import annotations

import asyncio

import typer
from rich.table import Table

from sena.cli.main import app, console
from sena.memory.sqlite import SQLiteMemory


@app.command()
def memory(
    action: str = typer.Argument(..., help="Action: list, add, search, delete."),
    content: str | None = typer.Argument(None, help="Content for add/search."),
    namespace: str = typer.Option("default", "--namespace", "-n", help="Memory namespace."),
) -> None:
    """Manage persistent memory entries."""
    mem = SQLiteMemory()

    async def _run() -> None:
        if action == "add":
            if not content:
                console.print("[red]Content required for add.[/red]")
                raise typer.Exit(1)
            entry_id = await mem.store(content, namespace=namespace)
            console.print(f"[green]Added[/green] {entry_id}")
        elif action == "list":
            entries = await mem.retrieve("", namespace=namespace, limit=50)
            if not entries:
                console.print(f"[dim]No entries in '{namespace}'.[/dim]")
                return
            table = Table()
            table.add_column("ID", style="dim")
            table.add_column("Content")
            table.add_column("Created")
            for e in entries:
                table.add_row(str(e.id)[:8], e.content[:60], e.created_at or "")
            console.print(table)
        elif action == "search":
            if not content:
                console.print("[red]Query required for search.[/red]")
                raise typer.Exit(1)
            entries = await mem.retrieve(content, namespace=namespace, limit=10)
            if not entries:
                console.print(f"[dim]No results for '{content}'.[/dim]")
                return
            for e in entries:
                console.print(f"[bold]{str(e.id)[:8]}[/bold] {e.content[:120]}")
        elif action == "delete":
            if not content:
                console.print("[red]ID required for delete.[/red]")
                raise typer.Exit(1)
            ok = await mem.delete(content)
            console.print("[green]Deleted[/green]" if ok else "[red]Not found[/red]")
        else:
            console.print(f"[red]Unknown action:[/red] {action}")

    asyncio.run(_run())
