"""Demo script to preview the Hanuman mascot animation."""

from __future__ import annotations

import time

from rich.console import Console
from rich.live import Live

from sena.ui.mascot import MascotAnimation, print_mascot_banner


def main() -> None:
    console = Console()
    console.print("\n[bold green]Static Banner:[/bold green]\n")
    print_mascot_banner(console)

    console.print("\n[bold green]Walking Animation (4 seconds):[/bold green]\n")
    mascot = MascotAnimation(speed=1.0)
    with Live(mascot, console=console, auto_refresh=True, refresh_per_second=12):
        time.sleep(4.0)

    console.print("\n[dim]Done.[/dim]\n")


if __name__ == "__main__":
    main()
