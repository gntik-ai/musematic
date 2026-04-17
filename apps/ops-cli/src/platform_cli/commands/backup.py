"""Backup command group."""

# mypy: disable-error-code=untyped-decorator

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Annotated

import typer

from platform_cli.backup.orchestrator import (
    BackupOrchestrator,
    BackupVerificationError,
)
from platform_cli.backup.scheduler import BackupScheduler
from platform_cli.config import ExitCode
from platform_cli.output.console import get_console, print_table
from platform_cli.runtime import (
    emit_event,
    exit_with_error,
    get_state,
    load_runtime_config,
)

backup_app = typer.Typer(
    help="Create, restore, verify, and inspect platform backups.",
    no_args_is_help=True,
)
schedule_app = typer.Typer(help="Manage automated backup schedules.", no_args_is_help=True)


def _parse_stores(value: str | None) -> set[str] | None:
    if value is None:
        return None
    items = {item.strip() for item in value.split(",") if item.strip()}
    return items or None


def _human_size(size_bytes: int) -> str:
    size = float(size_bytes)
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    unit = units[0]
    for candidate in units:
        unit = candidate
        if size < 1024.0 or candidate == units[-1]:
            break
        size /= 1024.0
    if unit == "B":
        return f"{int(size)} {unit}"
    return f"{size:.1f} {unit}"


def _render_verification_results(error: BackupVerificationError) -> None:
    rows = []
    for result in error.results:
        rows.append(
            (
                result.store,
                "pass" if result.ok else "fail",
                result.actual_checksum or "",
                result.expected_checksum,
                result.error or "",
            )
        )
    print_table(("Store", "Status", "Actual", "Expected", "Error"), rows)


@backup_app.command("create")
def create_backup(
    ctx: typer.Context,
    tag: str | None = None,
    storage_location: Annotated[
        str | None, typer.Option("--storage-location", envvar="PLATFORM_CLI_BACKUP_STORAGE")
    ] = None,
    force: bool = False,
) -> None:
    """Create a new full-platform backup."""

    config = load_runtime_config(ctx, backup_storage=storage_location)
    orchestrator = BackupOrchestrator(config)
    try:
        manifest = asyncio.run(
            orchestrator.create(
                tag,
                force=force,
                headless=get_state(ctx).json_output,
            )
        )
    except Exception as exc:
        exit_with_error(ctx, str(exc))

    emit_event(
        ctx,
        stage="backup-create",
        status=manifest.status.value,
        message="backup created",
        details=manifest.model_dump(mode="json"),
    )

    if not get_state(ctx).json_output:
        get_console().print(
            f"Backup {manifest.backup_id} created — status: {manifest.status.value} — "
            f"{manifest.total_duration_seconds:.1f}s total"
        )

    if manifest.status == "partial":
        raise typer.Exit(int(ExitCode.PARTIAL_FAILURE.value))
    if manifest.status == "failed":
        raise typer.Exit(int(ExitCode.GENERAL_ERROR.value))


@backup_app.command("restore")
def restore_backup(
    ctx: typer.Context,
    backup_id: str,
    stores: str | None = None,
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Restore an existing backup."""

    config = load_runtime_config(ctx)
    orchestrator = BackupOrchestrator(config)
    try:
        manifest = orchestrator.manifests.load(backup_id)
    except Exception as exc:
        exit_with_error(ctx, str(exc))
        return

    selected = _parse_stores(stores)
    available = {artifact.store for artifact in manifest.artifacts}
    if selected is not None:
        missing = sorted(selected - available)
        if missing:
            missing_list = ", ".join(missing)
            available_list = ", ".join(sorted(available))
            exit_with_error(
                ctx,
                f"unknown stores requested: {missing_list}",
                details={"available_stores": sorted(available)},
                remediation=f"Available stores: {available_list}",
            )

    restore_order = [
        name
        for name in BackupOrchestrator.RESTORE_ORDER
        if name in (selected or available)
    ]

    if not yes and not get_state(ctx).json_output:
        get_console().print(
            f"The following stores will be restored from backup {manifest.backup_id}"
            f"{f' (tag: {manifest.tag})' if manifest.tag else ''}:"
        )
        for store in restore_order:
            get_console().print(f"  • {store}")
        if not typer.confirm("Warning: This will overwrite current data. Continue?"):
            raise typer.Exit(0)

    try:
        asyncio.run(
            orchestrator.restore(
                manifest.backup_id,
                selected,
                verify_only=False,
                headless=get_state(ctx).json_output,
            )
        )
    except BackupVerificationError as exc:
        if not get_state(ctx).json_output:
            first_failure = next(result for result in exc.results if not result.ok)
            if first_failure.actual_checksum is not None:
                get_console().print(
                    f"Checksum mismatch for store: {first_failure.store}\n"
                    f"  Expected: {first_failure.expected_checksum}\n"
                    f"  Got:      {first_failure.actual_checksum}"
                )
                get_console().print("Aborting restore — no stores have been modified.")
            _render_verification_results(exc)
        emit_event(
            ctx,
            stage="backup-restore",
            status="failed",
            message="backup verification failed",
            details={
                "backup_id": manifest.backup_id,
                "verify_only": False,
                "results": [asdict(result) for result in exc.results],
            },
        )
        raise typer.Exit(int(ExitCode.GENERAL_ERROR.value)) from None
    except Exception as exc:
        exit_with_error(ctx, str(exc))

    emit_event(
        ctx,
        stage="backup-restore",
        status="completed",
        message="backup restored",
        details={
            "backup_id": manifest.backup_id,
            "stores_restored": restore_order,
            "verify_only": False,
        },
    )
    if not get_state(ctx).json_output:
        get_console().print("Restore completed")


@backup_app.command("verify")
def verify_backup(ctx: typer.Context, backup_id: str) -> None:
    """Verify backup integrity without restoring any data."""

    config = load_runtime_config(ctx)
    orchestrator = BackupOrchestrator(config)
    try:
        manifest = orchestrator.manifests.load(backup_id)
        asyncio.run(
            orchestrator.restore(
                manifest.backup_id,
                verify_only=True,
                headless=get_state(ctx).json_output,
            )
        )
    except BackupVerificationError as exc:
        if not get_state(ctx).json_output:
            _render_verification_results(exc)
        emit_event(
            ctx,
            stage="backup-verify",
            status="failed",
            message="backup verification failed",
            details={
                "backup_id": backup_id,
                "results": [asdict(result) for result in exc.results],
            },
        )
        raise typer.Exit(int(ExitCode.GENERAL_ERROR.value)) from None
    except Exception as exc:
        exit_with_error(ctx, str(exc))
        return

    emit_event(
        ctx,
        stage="backup-verify",
        status="completed",
        message="backup verified",
        details={
            "backup_id": manifest.backup_id,
            "results": [asdict(result) for result in orchestrator.last_verification_results],
        },
    )
    if not get_state(ctx).json_output:
        get_console().print(
            f"All {len(orchestrator.last_verification_results)} artifacts verified successfully."
        )


@backup_app.command("list")
def list_backups(
    ctx: typer.Context,
    limit: int = 20,
) -> None:
    """List available backup manifests."""

    config = load_runtime_config(ctx)
    manifests = BackupOrchestrator(config).list(limit=limit)
    items = [
        {
            "backup_id": item.backup_id,
            "tag": item.tag,
            "created_at": item.created_at,
            "total_size_bytes": item.total_size_bytes,
            "store_count": len(item.artifacts),
            "status": item.status.value,
        }
        for item in manifests
    ]
    emit_event(
        ctx,
        stage="backup-list",
        status="completed",
        message="listed backups",
        details={"count": len(items), "items": items},
    )
    if get_state(ctx).json_output:
        return

    if not manifests:
        get_console().print("No backups are available.")
        return

    rows = [
        (
            item.tag or "auto",
            item.created_at,
            _human_size(item.total_size_bytes),
            f"{len(item.artifacts)}/{len(BackupOrchestrator.BACKUP_ORDER)}",
            item.status.value,
        )
        for item in manifests
    ]
    print_table(("Tag", "Created", "Size", "Stores", "Status"), rows)


@schedule_app.command("start")
def start_schedule(
    ctx: typer.Context,
    cron: Annotated[str, typer.Option("--cron")],
    retention_days: Annotated[int, typer.Option("--retention-days")] = 30,
    storage_location: Annotated[
        str | None, typer.Option("--storage-location", envvar="PLATFORM_CLI_BACKUP_STORAGE")
    ] = None,
) -> None:
    """Start the blocking scheduled backup daemon."""

    config = load_runtime_config(ctx, backup_storage=storage_location)
    scheduler = BackupScheduler(config)
    try:
        scheduler.start(cron_expression=cron, retention_days=retention_days)
    except Exception as exc:
        exit_with_error(ctx, str(exc))


@schedule_app.command("run-once")
def run_schedule_once(
    ctx: typer.Context,
    retention_days: Annotated[int, typer.Option("--retention-days")] = 30,
    storage_location: Annotated[
        str | None, typer.Option("--storage-location", envvar="PLATFORM_CLI_BACKUP_STORAGE")
    ] = None,
) -> None:
    """Execute one scheduled backup cycle immediately."""

    config = load_runtime_config(ctx, backup_storage=storage_location)
    scheduler = BackupScheduler(config)
    try:
        result = asyncio.run(scheduler.run_once(retention_days=retention_days))
    except Exception as exc:
        exit_with_error(ctx, str(exc))
        return

    emit_event(
        ctx,
        stage="backup-schedule",
        status=result.status.value,
        message="scheduled backup completed",
        details={
            "backup_id": result.backup_id,
            "pruned_count": result.pruned_count,
            "run_at": result.run_at,
            "error": result.error,
        },
    )

    if not get_state(ctx).json_output:
        get_console().print(
            f"Scheduled backup {result.backup_id or '-'} "
            f"finished with status {result.status.value}; "
            f"pruned {result.pruned_count} old manifests."
        )

    if result.status == "partial":
        raise typer.Exit(int(ExitCode.PARTIAL_FAILURE.value))
    if result.status == "failed":
        raise typer.Exit(int(ExitCode.GENERAL_ERROR.value))


backup_app.add_typer(schedule_app, name="schedule")
