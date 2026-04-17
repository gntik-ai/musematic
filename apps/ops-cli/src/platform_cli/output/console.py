"""Rich-powered interactive console output helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TextIO

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

_console: Console = Console()

_STATUS_STYLES = {
    "healthy": "green",
    "degraded": "yellow",
    "unhealthy": "red",
    "unknown": "dim",
    "pending": "dim",
    "in_progress": "cyan",
    "completed": "green",
    "failed": "red",
    "skipped": "yellow",
}


def configure_console(*, no_color: bool = False, file: TextIO | None = None) -> Console:
    """Configure the global Rich console."""

    global _console
    _console = Console(no_color=no_color, file=file)
    return _console


def get_console() -> Console:
    """Return the configured Rich console."""

    return _console


def _status_text(value: str) -> Text:
    return Text(value, style=_STATUS_STYLES.get(value, "white"))


def print_status(component: str, status: str, latency: float | None) -> None:
    """Print a single status line."""

    latency_suffix = "—" if latency is None else f"{latency:.1f}ms"
    get_console().print(
        f"{component:<24}",
        _status_text(status),
        latency_suffix,
        sep="  ",
    )


def print_step(index: int, total: int, component: str, status: str, duration: float) -> None:
    """Print a numbered installation or orchestration step."""

    get_console().print(
        f"[{index}/{total}] {component}",
        _status_text(status),
        f"[dim][{duration:.1f}s][/dim]",
    )


def print_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    """Render a Rich table."""

    table = Table(show_header=True, header_style="bold")
    for header in headers:
        table.add_column(header)
    for row in rows:
        table.add_row(*[str(cell) for cell in row])
    get_console().print(table)


def print_credentials_panel(email: str, password: str, url: str) -> None:
    """Display one-time administrator credentials."""

    panel = Panel.fit(
        f"[bold]Admin Credentials[/bold]\nEmail: {email}\nPassword: {password}\nURL: {url}",
        title="Shown once only",
        border_style="green",
    )
    get_console().print(panel)


def print_error(message: str, remediation: str | None = None) -> None:
    """Render an error panel with optional remediation guidance."""

    body = message
    if remediation:
        body = f"{body}\n\n[bold]Remediation[/bold]\n{remediation}"
    get_console().print(Panel.fit(body, title="Error", border_style="red"))


def create_progress() -> Progress:
    """Create a standard progress bar instance for long-running operations."""

    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=get_console(),
    )
