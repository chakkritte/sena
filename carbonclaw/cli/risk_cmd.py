"""CLI command for AST and Git history-aware refactoring risk analysis."""

from __future__ import annotations

from pathlib import Path
import typer
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from carbonclaw.cli.main import app, console
from carbonclaw.memory.graph import KnowledgeGraphMemory


@app.command(name="risk")
def risk_cmd(
    filepath: str = typer.Argument(..., help="The Python file to analyze for refactoring risk."),
) -> None:
    """Analyze a file's AST structures and Git history to predict refactoring risk and blast radius."""
    path = Path(filepath).absolute()
    if not path.exists():
        console.print(f"[bold red]Error:[/bold red] File '{filepath}' does not exist.")
        raise typer.Exit(code=1)

    if not path.suffix == ".py":
        console.print("[bold yellow]Warning:[/bold yellow] Risk analysis is optimized for Python (.py) source files.")

    # 1. Initialize and build AST graph representation for the file
    memory = KnowledgeGraphMemory()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description="Parsing AST knowledge graph and fetching Git history...", total=None)
        memory.analyze_file(path)
        stats = memory.analyze_git_churn(path)

    if "error" in stats:
        console.print(f"[bold red]Error during Git analysis:[/bold red] {stats['error']}")
        raise typer.Exit(code=1)

    # 2. Render Risk Score Gauge
    score = stats["risk_score"]
    if score < 30.0:
        color = "green"
        level = "LOW RISK"
        desc = "Safe to refactor. Low change frequency and limited contributor overlap."
    elif score < 65.0:
        color = "yellow"
        level = "MODERATE RISK"
        desc = "Proceed with care. Moderately high churn or multiple contributors."
    else:
        color = "red"
        level = "HIGH RISK"
        desc = "CRITICAL: Highly modified, high churn, multiple contributors. High chance of regression!"

    # 3. Create rich display layout
    console.print()
    console.print(
        Panel(
            f"[bold {color}]{level}[/bold {color}] — [bold white]{score}/100[/bold white]\n"
            f"[dim]{desc}[/dim]",
            title="🔍 Refactoring Risk Assessment",
            title_align="center",
            border_style=color,
            padding=(1, 2)
        )
    )

    # 4. Display Git telemetries
    git_table = Table(title="📈 Git Churn & Telemetry History", show_header=True, header_style="bold cyan")
    git_table.add_column("Metric", style="white")
    git_table.add_column("Value", justify="right", style="bold yellow")
    git_table.add_column("Risk Impact", style="dim")

    git_table.add_row(
        "Modification Frequency (Commits)",
        str(stats["commits_count"]),
        "High churn increases risk" if stats["commits_count"] > 15 else "Low churn"
    )
    git_table.add_row(
        "Unique Contributors (Authors)",
        str(stats["author_count"]),
        "High contributor overlap" if stats["author_count"] > 3 else "Single/few authors"
    )
    git_table.add_row(
        "Lines Added / Deleted",
        f"+{stats['lines_added']} / -{stats['lines_deleted']}",
        "High line churn" if (stats["lines_added"] + stats["lines_deleted"]) > 500 else "Stable codebase"
    )

    console.print(git_table)

    # 5. Display Blast Radius
    blast_radius = stats["blast_radius"]
    console.print()
    if not blast_radius:
        console.print("🎯 [bold green]Blast Radius: None detected.[/bold green]")
        console.print("[dim]No downstream project files currently import symbols from this file.[/dim]")
    else:
        blast_table = Table(
            title=f"💥 Downstream Blast Radius ({len(blast_radius)} files affected)",
            show_header=True,
            header_style="bold red"
        )
        blast_table.add_column("Affected File Path", style="cyan")
        blast_table.add_column("Dependency Relation", style="white")

        for f in blast_radius:
            try:
                rel_path = Path(f).relative_to(Path.cwd()) if Path(f).is_absolute() else f
            except Exception:
                rel_path = f
            blast_table.add_row(str(rel_path), "Imports symbols from this module")

        console.print(blast_table)
        console.print("[dim]Modifying interfaces or signatures in this file will require checking the above downstream files.[/dim]")
    console.print()
