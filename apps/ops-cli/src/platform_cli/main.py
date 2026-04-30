"""Typer application entry point for the platform CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from platform_cli.commands.admin import admin_app
from platform_cli.commands.backup import backup_app
from platform_cli.commands.diagnose import diagnose_app
from platform_cli.commands.install import install_app
from platform_cli.commands.observability import observability_app
from platform_cli.commands.superadmin import superadmin_app
from platform_cli.commands.upgrade import upgrade_app
from platform_cli.commands.vault import vault_app
from platform_cli.output.console import configure_console
from platform_cli.runtime import CLIState

app = typer.Typer(
    name="platform-cli",
    help="Installer and operations CLI for the Musematic platform.",
    no_args_is_help=True,
)


@app.callback()
def main_callback(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            help="Path to installer config YAML.",
            exists=False,
            dir_okay=False,
            file_okay=True,
            resolve_path=True,
            envvar="PLATFORM_CLI_CONFIG",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose", "-v", help="Enable verbose logging.", envvar="PLATFORM_CLI_VERBOSE"
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit structured NDJSON output.", envvar="PLATFORM_CLI_JSON"),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option(
            "--no-color",
            help="Disable colored interactive output.",
            envvar="PLATFORM_CLI_NO_COLOR",
        ),
    ] = False,
) -> None:
    """Configure global output and runtime state before running subcommands."""

    configure_console(no_color=no_color)
    ctx.obj = CLIState(
        config_path=config,
        verbose=verbose,
        json_output=json_output,
        no_color=no_color,
    )


app.add_typer(install_app, name="install")
app.add_typer(diagnose_app, name="diagnose")
app.add_typer(backup_app, name="backup")
app.add_typer(upgrade_app, name="upgrade")
app.add_typer(admin_app, name="admin")
app.add_typer(superadmin_app, name="superadmin")
app.add_typer(observability_app, name="observability")
app.add_typer(vault_app, name="vault")


def run() -> None:
    """Execute the Typer application."""

    app()
