"""Backup command group."""

# mypy: disable-error-code=untyped-decorator

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from platform_cli.backup.orchestrator import BackupOrchestrator
from platform_cli.output.console import get_console, print_table
from platform_cli.runtime import emit_event, exit_with_error, load_runtime_config

backup_app = typer.Typer(
    help="Create, restore, and inspect platform backups.",
    no_args_is_help=True,
)


def _parse_stores(value: str | None) -> set[str] | None:
    if value is None:
        return None
    items = {item.strip() for item in value.split(",") if item.strip()}
    return items or None


@backup_app.command("create")
def create_backup(
    ctx: typer.Context,
    tag: str | None = None,
    stores: str | None = None,
    storage_location: Annotated[
        str | None, typer.Option("--storage-location", envvar="PLATFORM_CLI_BACKUP_STORAGE")
    ] = None,
    force: bool = False,
) -> None:
    """Create a new backup manifest."""

    config = load_runtime_config(ctx, backup_storage=storage_location)
    orchestrator = BackupOrchestrator(config)
    try:
        manifest = asyncio.run(orchestrator.create(tag, _parse_stores(stores), force=force))
    except Exception as exc:
        exit_with_error(ctx, str(exc))
    emit_event(
        ctx,
        stage="backup-create",
        status=manifest.status.value,
        message="backup created",
        details=manifest.model_dump(mode="json"),
    )
    if not ctx.obj.json_output:
        get_console().print(
            f"Backup {manifest.backup_id} created with status {manifest.status.value}"
        )


@backup_app.command("restore")
def restore_backup(
    ctx: typer.Context,
    backup_id: str,
    stores: str | None = None,
    verify_only: bool = False,
    force: bool = False,
) -> None:
    """Restore or verify an existing backup."""

    del force
    config = load_runtime_config(ctx)
    orchestrator = BackupOrchestrator(config)
    try:
        restored = asyncio.run(
            orchestrator.restore(backup_id, _parse_stores(stores), verify_only=verify_only)
        )
    except Exception as exc:
        exit_with_error(ctx, str(exc))
    emit_event(
        ctx,
        stage="backup-restore",
        status="completed",
        message="backup restored" if not verify_only else "backup verified",
        details={"backup_id": backup_id, "verify_only": verify_only, "restored": restored},
    )
    if not ctx.obj.json_output:
        get_console().print("Verification completed" if verify_only else "Restore completed")


@backup_app.command("list")
def list_backups(
    ctx: typer.Context,
    limit: int = 20,
) -> None:
    """List available backup manifests."""

    config = load_runtime_config(ctx)
    manifests = BackupOrchestrator(config).list(limit=limit)
    emit_event(
        ctx,
        stage="backup-list",
        status="completed",
        message="listed backups",
        details={
            "count": len(manifests),
            "items": [item.model_dump(mode="json") for item in manifests],
        },
    )
    if not ctx.obj.json_output:
        rows = [
            (
                item.sequence_number,
                item.backup_id,
                item.tag or "",
                item.status.value,
                item.total_size_bytes,
            )
            for item in manifests
        ]
        print_table(("Seq", "Backup ID", "Tag", "Status", "Bytes"), rows)
