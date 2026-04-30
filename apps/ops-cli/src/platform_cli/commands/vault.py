"""Vault integration commands."""

# mypy: disable-error-code=untyped-decorator

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer

from platform_cli.output.console import get_console, print_table
from platform_cli.runtime import (
    emit_event,
    exit_with_error,
    inferred_api_base_url,
    load_runtime_config,
)
from platform_cli.secrets.migration import migrate_from_k8s, verify_migration

vault_app = typer.Typer(
    help=(
        "Manage Vault integration: migrate, verify, status, flush-cache, rotate-token. "
        "The status command mirrors the deferred admin UI panel data."
    ),
    no_args_is_help=True,
)


def _headers(config: Any) -> dict[str, str]:
    if config.auth_token:
        return {"Authorization": f"Bearer {config.auth_token}"}
    return {}


async def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.request(method, url, headers=headers, json=json)
    response.raise_for_status()
    return response


@vault_app.command("migrate-from-k8s")
def migrate_from_k8s_command(
    ctx: typer.Context,
    namespaces: Annotated[
        list[str] | None,
        typer.Option("--namespace", help="Kubernetes namespace to scan. Repeatable."),
    ] = None,
    environment: Annotated[
        str, typer.Option("--env", help="Manifest environment label.")
    ] = "production",
    apply: Annotated[
        bool, typer.Option("--apply", help="Write matching Secrets to Vault.")
    ] = False,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", file_okay=False, dir_okay=True, resolve_path=True),
    ] = Path.cwd(),
) -> None:
    """Migrate canonical Kubernetes Secrets to Vault and emit a SHA-256 manifest."""

    try:
        manifest, manifest_path = migrate_from_k8s(
            namespaces=namespaces,
            environment=environment,
            apply=apply,
            output_dir=output_dir,
        )
    except Exception as exc:
        exit_with_error(ctx, str(exc))
    emit_event(
        ctx,
        stage="vault-migrate-from-k8s",
        status="completed",
        message="vault migration manifest emitted",
        details=manifest.to_dict() | {"manifest_path": str(manifest_path)},
    )
    if not ctx.obj.json_output:
        get_console().print(f"Wrote {manifest_path}")
        print_table(
            ("Success", "Failed", "Already migrated", "New"),
            [
                (
                    manifest.success_count,
                    manifest.failure_count,
                    manifest.already_migrated_count,
                    manifest.new_count,
                )
            ],
        )


@vault_app.command("verify-migration")
def verify_migration_command(
    ctx: typer.Context,
    manifest: Annotated[
        Path,
        typer.Option("--manifest", exists=True, dir_okay=False, resolve_path=True),
    ],
) -> None:
    """Verify Vault values against a migration manifest."""

    try:
        verified = verify_migration(manifest)
    except Exception as exc:
        exit_with_error(ctx, str(exc))
    emit_event(
        ctx,
        stage="vault-verify-migration",
        status="completed",
        message="vault migration verified",
        details=verified.to_dict(),
    )
    if not ctx.obj.json_output:
        print_table(
            ("Path", "Key", "Status", "Reason"),
            [
                (
                    entry.vault_path,
                    entry.k8s_secret_key,
                    "pass" if entry.success else "fail",
                    entry.reason,
                )
                for entry in verified.entries
            ],
        )


@vault_app.command("status")
def status_command(ctx: typer.Context) -> None:
    """Show the same Vault status data intended for /admin/security/vault."""

    config = load_runtime_config(ctx)
    try:
        response = asyncio.run(
            _request(
                "GET",
                f"{inferred_api_base_url(config)}/api/v1/admin/vault/status",
                headers=_headers(config),
            )
        )
    except Exception as exc:
        exit_with_error(ctx, str(exc))
    payload = response.json()
    emit_event(
        ctx,
        stage="vault-status",
        status="completed",
        message="vault status retrieved",
        details=payload if isinstance(payload, dict) else {"payload": payload},
    )
    if not ctx.obj.json_output and isinstance(payload, dict):
        print_table(("Key", "Value"), list(payload.items()))


@vault_app.command("flush-cache")
def flush_cache_command(
    ctx: typer.Context,
    pod: Annotated[str | None, typer.Option("--pod", help="Single pod to flush.")] = None,
    all_pods: Annotated[
        bool, typer.Option("--all-pods", help="Flush every control-plane pod.")
    ] = False,
) -> None:
    """Flush a control-plane Vault cache via the admin contract."""

    config = load_runtime_config(ctx)
    payload = {"pod": pod, "all_pods": all_pods}
    try:
        response = asyncio.run(
            _request(
                "POST",
                f"{inferred_api_base_url(config)}/api/v1/admin/vault/cache-flush",
                headers=_headers(config),
                json=payload,
            )
        )
    except Exception as exc:
        exit_with_error(ctx, str(exc))
    result = response.json()
    emit_event(
        ctx,
        stage="vault-flush-cache",
        status="completed",
        message="vault cache flush requested",
        details=result if isinstance(result, dict) else payload,
    )
    if not ctx.obj.json_output:
        get_console().print("Vault cache flush requested")


@vault_app.command("rotate-token")
def rotate_token_command(
    ctx: typer.Context,
    pod: Annotated[str | None, typer.Option("--pod", help="Control-plane pod to target.")] = None,
) -> None:
    """Force immediate Vault token renewal via the admin contract."""

    config = load_runtime_config(ctx)
    try:
        response = asyncio.run(
            _request(
                "POST",
                f"{inferred_api_base_url(config)}/api/v1/admin/vault/rotate-token",
                headers=_headers(config),
                json={"pod": pod},
            )
        )
    except Exception as exc:
        exit_with_error(ctx, str(exc))
    result = response.json()
    emit_event(
        ctx,
        stage="vault-rotate-token",
        status="completed",
        message="vault token rotation requested",
        details=result if isinstance(result, dict) else {"pod": pod},
    )
    if not ctx.obj.json_output:
        get_console().print("Vault token rotation requested")
