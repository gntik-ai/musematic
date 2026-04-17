"""Diagnose command group."""

# mypy: disable-error-code=untyped-decorator

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from platform_cli.config import DeploymentMode, ExitCode
from platform_cli.diagnostics.checker import DiagnosticRunner
from platform_cli.output.console import get_console, print_table
from platform_cli.runtime import emit_event, load_runtime_config

diagnose_app = typer.Typer(
    help="Run platform diagnostics and health checks.",
    invoke_without_command=True,
)


@diagnose_app.callback()
def diagnose(
    ctx: typer.Context,
    deployment_mode: Annotated[
        DeploymentMode | None,
        typer.Option("--deployment-mode", envvar="PLATFORM_CLI_DEPLOYMENT_MODE"),
    ] = None,
    fix: bool = False,
    timeout: int = 5,
    checks: str | None = None,
) -> None:
    """Run platform diagnostics against the selected deployment mode."""

    config = load_runtime_config(ctx)
    mode = deployment_mode or DiagnosticRunner.auto_detect_mode(config)
    selected = {item.strip() for item in checks.split(",")} if checks else None
    runner = DiagnosticRunner(config, deployment_mode=mode, selected_checks=selected)
    report = asyncio.run(runner.run(timeout_per_check=timeout))
    fix_results = asyncio.run(runner.auto_fix(report)) if fix else None
    if fix_results:
        report.auto_fix_results = fix_results
    emit_event(
        ctx,
        stage="diagnose",
        status=report.overall_status.value,
        message="diagnostics completed",
        details=report.model_dump(mode="json"),
    )
    if not ctx.obj.json_output:
        rows = [
            (
                item.display_name,
                item.status.value,
                f"{item.latency_ms:.1f}" if item.latency_ms is not None else "—",
                item.error or "",
            )
            for item in report.checks
        ]
        print_table(("Component", "Status", "Latency (ms)", "Error"), rows)
        get_console().print(f"Overall: {report.overall_status.value}")
    if report.overall_status.value != "healthy":
        raise typer.Exit(int(ExitCode.PARTIAL_FAILURE.value))
