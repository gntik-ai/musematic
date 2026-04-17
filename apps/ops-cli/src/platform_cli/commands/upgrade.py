"""Upgrade command group."""

# mypy: disable-error-code=untyped-decorator

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from platform_cli.backup.orchestrator import BackupOrchestrator
from platform_cli.config import ExitCode
from platform_cli.constants import PLATFORM_COMPONENTS
from platform_cli.diagnostics.checker import DiagnosticRunner
from platform_cli.helm.runner import HelmRunner
from platform_cli.models import ComponentVersion, UpgradePlan
from platform_cli.output.console import get_console, print_table
from platform_cli.runtime import emit_event, exit_with_error, load_runtime_config

upgrade_app = typer.Typer(
    help="Plan and execute rolling platform upgrades.",
    invoke_without_command=True,
)


def _release_versions() -> dict[str, dict[str, Any]]:
    runner = HelmRunner()
    releases: dict[str, dict[str, Any]] = {}
    for component in PLATFORM_COMPONENTS:
        try:
            for release in runner.list_releases(component.namespace):
                releases[str(release.get("name"))] = release
        except RuntimeError:
            continue
    return releases


@upgrade_app.callback()
def upgrade(
    ctx: typer.Context,
    target_version: Annotated[str, typer.Option("--target-version")] = "latest",
    dry_run: bool = False,
    skip_backup: bool = False,
    force: bool = False,
) -> None:
    """Plan or execute a rolling upgrade."""

    config = load_runtime_config(ctx, image_tag=target_version)
    releases = _release_versions()
    versions = [
        ComponentVersion(
            component=component.name,
            current_version=str(
                releases.get(f"{config.namespace}-{component.name}", {}).get(
                    "app_version", "unknown"
                )
            ),
            target_version=target_version,
            upgrade_required=str(
                releases.get(f"{config.namespace}-{component.name}", {}).get(
                    "app_version", "unknown"
                )
            )
            != target_version,
            has_migration=component.has_migration,
        )
        for component in PLATFORM_COMPONENTS
    ]
    source_version = next(
        (item.current_version for item in versions if item.current_version != "unknown"),
        "unknown",
    )
    plan = UpgradePlan(
        source_version=source_version,
        target_version=target_version,
        components=versions,
    )
    emit_event(
        ctx,
        stage="upgrade-plan",
        status="planned",
        message="upgrade plan generated",
        details=plan.model_dump(mode="json"),
    )
    if not ctx.obj.json_output:
        rows = [
            (item.component, item.current_version, item.target_version, item.upgrade_required)
            for item in versions
        ]
        print_table(("Component", "Current", "Target", "Upgrade"), rows)
    if dry_run:
        return
    try:
        if not skip_backup:
            asyncio.run(BackupOrchestrator(config).create("pre-upgrade", force=force))
        runner = HelmRunner()
        values_dir = config.data_dir / "rendered" / "upgrade"
        values_dir.mkdir(parents=True, exist_ok=True)
        for component in PLATFORM_COMPONENTS:
            if not component.helm_chart:
                continue
            values_file = values_dir / f"{component.name}.yaml"
            values_file.write_text(
                yaml.safe_dump({"global": {"imageTag": target_version}}, sort_keys=True),
                encoding="utf-8",
            )
            runner.install(
                Path.cwd().parents[2] / "deploy" / "helm" / component.helm_chart,
                f"{config.namespace}-{component.name}",
                component.namespace,
                values_file,
            )
            runner.wait_for_ready(component.name, component.namespace)
        report = asyncio.run(DiagnosticRunner(config).run())
    except Exception as exc:
        message = (
            f"upgrade failed: {exc}. Rollback with "
            f"`helm rollback <release> <revision>` for the last upgraded component."
        )
        exit_with_error(ctx, message, code=ExitCode.PARTIAL_FAILURE)
    emit_event(
        ctx,
        stage="upgrade",
        status=report.overall_status.value,
        message="upgrade completed",
        details=report.model_dump(mode="json"),
    )
    if report.overall_status.value != "healthy":
        raise typer.Exit(int(ExitCode.PARTIAL_FAILURE.value))
    if not ctx.obj.json_output:
        get_console().print("Upgrade completed")
