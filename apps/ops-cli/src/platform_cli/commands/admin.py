"""Administrative command group."""

# mypy: disable-error-code=untyped-decorator

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import httpx
import typer

from platform_cli.config import ExitCode
from platform_cli.diagnostics.checker import DiagnosticRunner
from platform_cli.installers.local import LocalInstaller
from platform_cli.output.console import get_console, print_table
from platform_cli.runtime import (
    emit_event,
    exit_with_error,
    inferred_api_base_url,
    load_runtime_config,
)
from platform_cli.secrets.generator import generate_secrets

admin_app = typer.Typer(
    help="Administrative workflows for platform operations.",
    no_args_is_help=True,
)
users_app = typer.Typer(help="Manage platform users.", no_args_is_help=True)


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
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.request(method, url, headers=headers, json=json, params=params)
    response.raise_for_status()
    return response


@users_app.command("list")
def list_users(
    ctx: typer.Context,
    role: str | None = None,
    status: str | None = None,
) -> None:
    """List users or invitations via the control plane API."""

    config = load_runtime_config(ctx)
    api_url = inferred_api_base_url(config)
    try:
        endpoint = (
            "/api/v1/accounts/invitations"
            if config.auth_token
            else "/api/v1/accounts/pending-approvals"
        )
        response = asyncio.run(
            _request(
                "GET",
                f"{api_url}{endpoint}",
                headers=_headers(config),
                params={
                    key: value for key, value in {"role": role, "status": status}.items() if value
                },
            )
        )
    except Exception as exc:
        exit_with_error(ctx, str(exc))
    payload = response.json()
    items = payload.get("items", []) if isinstance(payload, dict) else []
    emit_event(
        ctx,
        stage="admin-users-list",
        status="completed",
        message="users listed",
        details={"items": items},
    )
    if not ctx.obj.json_output:
        rows = [
            (
                item.get("email") or item.get("invitee_email") or "",
                item.get("status") or "pending",
                ",".join(item.get("roles", [])) if isinstance(item.get("roles"), list) else "",
            )
            for item in items
        ]
        print_table(("Email", "Status", "Roles"), rows)


@users_app.command("create")
def create_user(
    ctx: typer.Context,
    email: str,
    role: Annotated[str, typer.Option("--role")],
    password: str | None = None,
) -> None:
    """Create or invite a user through the control plane API."""

    config = load_runtime_config(ctx)
    api_url = inferred_api_base_url(config)
    resolved_password = password or generate_secrets(config.secrets).admin_password
    try:
        if config.auth_token:
            response = asyncio.run(
                _request(
                    "POST",
                    f"{api_url}/api/v1/accounts/invitations",
                    headers=_headers(config),
                    json={"email": email, "roles": [role]},
                )
            )
        else:
            response = asyncio.run(
                _request(
                    "POST",
                    f"{api_url}/api/v1/accounts/register",
                    json={
                        "email": email,
                        "display_name": email.split("@", maxsplit=1)[0],
                        "password": resolved_password,
                    },
                )
            )
    except Exception as exc:
        exit_with_error(ctx, str(exc))
    emit_event(
        ctx,
        stage="admin-users-create",
        status="completed",
        message="user created",
        details={"email": email, "role": role, "response": response.json()},
    )
    if not ctx.obj.json_output:
        get_console().print(f"Created user {email} with role {role}")


@admin_app.command("status")
def admin_status(ctx: typer.Context) -> None:
    """Show overall platform status."""

    config = load_runtime_config(ctx)
    report = asyncio.run(DiagnosticRunner(config).run())
    payload = {
        "deployment_mode": config.deployment_mode.value,
        "component_count": len(report.checks),
        "overall_status": report.overall_status.value,
        "active_checks": len(report.checks),
    }
    emit_event(
        ctx, stage="admin-status", status="completed", message="status retrieved", details=payload
    )
    if not ctx.obj.json_output:
        rows = list(payload.items())
        print_table(("Key", "Value"), rows)


@admin_app.command("stop")
def admin_stop(ctx: typer.Context) -> None:
    """Stop a local-mode platform process."""

    config = load_runtime_config(ctx)
    if not LocalInstaller.stop(config.data_dir):
        raise typer.Exit(int(ExitCode.GENERAL_ERROR.value))
    emit_event(ctx, stage="admin-stop", status="completed", message="local platform stopped")
    if not ctx.obj.json_output:
        get_console().print("Local platform stopped")


admin_app.add_typer(users_app, name="users")
