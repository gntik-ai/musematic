"""Administrative command group."""

# mypy: disable-error-code=untyped-decorator

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer
import yaml

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
from platform_cli.secrets.migration import _vault_cli_path, validate_vault_path

admin_app = typer.Typer(
    help="Administrative workflows for platform operations.",
    no_args_is_help=True,
)
users_app = typer.Typer(help="Manage platform users.", no_args_is_help=True)
oauth_app = typer.Typer(
    help="Export and import OAuth provider configurations.",
    no_args_is_help=True,
)

_OAUTH_EXPORT_FIELDS = (
    "provider_type",
    "display_name",
    "enabled",
    "client_id",
    "redirect_uri",
    "scopes",
    "domain_restrictions",
    "org_restrictions",
    "group_role_mapping",
    "default_role",
    "require_mfa",
    "source",
    "client_secret_vault_path",
)


@dataclass(slots=True)
class OAuthImportDiff:
    provider_type: str
    operation: str
    changed_fields: list[str]


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


def _provider_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        raw_items = payload.get("providers") or payload.get("items") or []
    elif isinstance(payload, list):
        raw_items = payload
    else:
        raw_items = []
    return [item for item in raw_items if isinstance(item, dict)]


def _normalise_provider_for_manifest(provider: dict[str, Any]) -> dict[str, Any]:
    normalised = {
        "provider_type": str(provider.get("provider_type", "")),
        "display_name": str(provider.get("display_name", "")),
        "enabled": bool(provider.get("enabled", False)),
        "client_id": str(provider.get("client_id", "")),
        "redirect_uri": str(provider.get("redirect_uri", "")),
        "scopes": sorted(str(item) for item in provider.get("scopes", []) or []),
        "domain_restrictions": sorted(
            str(item) for item in provider.get("domain_restrictions", []) or []
        ),
        "org_restrictions": sorted(
            str(item) for item in provider.get("org_restrictions", []) or []
        ),
        "group_role_mapping": dict(sorted((provider.get("group_role_mapping") or {}).items())),
        "default_role": str(provider.get("default_role", "member")),
        "require_mfa": bool(provider.get("require_mfa", False)),
        "source": str(provider.get("source", "manual")),
        "client_secret_vault_path": str(
            provider.get("client_secret_vault_path") or provider.get("client_secret_ref") or ""
        ),
    }
    return {key: normalised[key] for key in _OAUTH_EXPORT_FIELDS}


def _manifest_digest(manifest_body: dict[str, Any]) -> str:
    payload = json.dumps(manifest_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _build_oauth_manifest(environment: str, providers: list[dict[str, Any]]) -> dict[str, Any]:
    entries = sorted(
        (_normalise_provider_for_manifest(provider) for provider in providers),
        key=lambda item: item["provider_type"],
    )
    body = {"schema_version": 1, "environment": environment, "providers": entries}
    return body | {"sha256": _manifest_digest(body)}


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("OAuth import manifest must be a YAML mapping.")
    return payload


def _validate_manifest_digest(payload: dict[str, Any]) -> None:
    expected = payload.get("sha256")
    if expected is None:
        return
    body = {key: value for key, value in payload.items() if key != "sha256"}
    observed = _manifest_digest(body)
    if str(expected) != observed:
        raise ValueError("OAuth import manifest sha256 does not match its provider payload.")


def _provider_payload_for_api(entry: dict[str, Any]) -> dict[str, Any]:
    vault_path = str(entry.get("client_secret_vault_path") or "")
    _validate_oauth_vault_path(vault_path)
    return {
        "display_name": str(entry.get("display_name", "")),
        "enabled": bool(entry.get("enabled", False)),
        "client_id": str(entry.get("client_id", "")),
        "client_secret_ref": vault_path,
        "redirect_uri": str(entry.get("redirect_uri", "")),
        "scopes": list(entry.get("scopes") or []),
        "domain_restrictions": list(entry.get("domain_restrictions") or []),
        "org_restrictions": list(entry.get("org_restrictions") or []),
        "group_role_mapping": dict(entry.get("group_role_mapping") or {}),
        "default_role": str(entry.get("default_role", "member")),
        "require_mfa": bool(entry.get("require_mfa", False)),
        "source": "imported",
    }


def _validate_oauth_vault_path(path: str) -> None:
    validate_vault_path(path)
    parts = path.split("/")
    if len(parts) < 6 or parts[4] != "oauth":
        raise ValueError(f"OAuth provider secret must use an oauth Vault path: {path}")


def _list_vault_versions(path: str) -> list[int]:
    _validate_oauth_vault_path(path)
    completed = subprocess.run(
        ["vault", "kv", "metadata", "get", "-format=json", _vault_cli_path(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return []
    payload = json.loads(completed.stdout or "{}")
    versions = payload.get("data", {}).get("versions", {})
    if isinstance(versions, dict):
        return sorted(int(version) for version in versions.keys())
    return []


def _validate_import_vault_paths(entries: list[dict[str, Any]]) -> None:
    missing: list[str] = []
    for entry in entries:
        path = str(entry.get("client_secret_vault_path") or "")
        versions = _list_vault_versions(path)
        if not versions:
            missing.append(path)
    if missing:
        raise ValueError(
            "Missing OAuth client secret Vault path(s): " + ", ".join(sorted(set(missing)))
        )


def _diff_import_entries(
    current_providers: list[dict[str, Any]],
    imported_entries: list[dict[str, Any]],
) -> list[OAuthImportDiff]:
    current_by_type = {
        str(provider.get("provider_type")): _normalise_provider_for_manifest(provider)
        for provider in current_providers
    }
    diffs: list[OAuthImportDiff] = []
    for entry in imported_entries:
        imported = _normalise_provider_for_manifest(entry)
        provider_type = imported["provider_type"]
        current = current_by_type.get(provider_type)
        if current is None:
            diffs.append(
                OAuthImportDiff(
                    provider_type=provider_type,
                    operation="create",
                    changed_fields=list(_OAUTH_EXPORT_FIELDS),
                )
            )
            continue
        changed = [
            field
            for field in _OAUTH_EXPORT_FIELDS
            if field != "source" and current.get(field) != imported.get(field)
        ]
        diffs.append(
            OAuthImportDiff(
                provider_type=provider_type,
                operation="update" if changed else "unchanged",
                changed_fields=changed,
            )
        )
    return diffs


def _diffs_to_dicts(diffs: list[OAuthImportDiff]) -> list[dict[str, Any]]:
    return [
        {
            "provider_type": diff.provider_type,
            "operation": diff.operation,
            "changed_fields": diff.changed_fields,
        }
        for diff in diffs
    ]


@oauth_app.command("export")
def export_oauth_config(
    ctx: typer.Context,
    environment: Annotated[str, typer.Option("--env", help="Environment label for the manifest.")],
    output: Annotated[
        Path,
        typer.Option("--output", dir_okay=False, resolve_path=True, help="YAML output path."),
    ],
) -> None:
    """Export OAuth provider configuration without secret values."""

    config = load_runtime_config(ctx)
    api_url = inferred_api_base_url(config)
    try:
        response = asyncio.run(
            _request(
                "GET",
                f"{api_url}/api/v1/admin/oauth/providers",
                headers=_headers(config),
            )
        )
        manifest = _build_oauth_manifest(environment, _provider_items(response.json()))
        _write_yaml(output, manifest)
    except Exception as exc:
        exit_with_error(ctx, str(exc))
    emit_event(
        ctx,
        stage="admin-oauth-export",
        status="completed",
        message="oauth provider configuration exported",
        details={"output": str(output), "manifest": manifest},
    )
    if not ctx.obj.json_output:
        get_console().print(f"Wrote {output}")
        print_table(
            ("Provider", "Source", "Vault path"),
            [
                (
                    provider["provider_type"],
                    provider["source"],
                    provider["client_secret_vault_path"],
                )
                for provider in manifest["providers"]
            ],
        )


@oauth_app.command("import")
def import_oauth_config(
    ctx: typer.Context,
    input_path: Annotated[
        Path,
        typer.Option(
            "--input",
            exists=True,
            dir_okay=False,
            resolve_path=True,
            help="YAML manifest produced by admin oauth export.",
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--no-dry-run", help="Preview the import without applying."),
    ] = True,
    apply: Annotated[bool, typer.Option("--apply", help="Apply the import after preview.")] = False,
    dry_run_first: Annotated[
        bool,
        typer.Option(
            "--dry-run-first",
            help="Required with --apply to confirm the operator reviewed the diff preview.",
        ),
    ] = False,
) -> None:
    """Validate and optionally import OAuth provider configuration."""

    if apply and not dry_run_first:
        exit_with_error(
            ctx,
            "--apply requires --dry-run-first so the provider diff is reviewed before mutation.",
        )
    if not dry_run and not apply:
        exit_with_error(ctx, "--no-dry-run requires --apply.")

    config = load_runtime_config(ctx)
    api_url = inferred_api_base_url(config)
    try:
        manifest = _read_yaml(input_path)
        _validate_manifest_digest(manifest)
        entries = _provider_items(manifest.get("providers", []))
        if not entries:
            raise ValueError("OAuth import manifest contains no providers.")
        payloads = {
            str(entry.get("provider_type")): _provider_payload_for_api(entry) for entry in entries
        }
        _validate_import_vault_paths(entries)
        response = asyncio.run(
            _request(
                "GET",
                f"{api_url}/api/v1/admin/oauth/providers",
                headers=_headers(config),
            )
        )
        diffs = _diff_import_entries(_provider_items(response.json()), entries)
        if apply:
            for provider_type, payload in sorted(payloads.items()):
                asyncio.run(
                    _request(
                        "PUT",
                        f"{api_url}/api/v1/admin/oauth/providers/{provider_type}",
                        headers=_headers(config),
                        json=payload,
                    )
                )
    except Exception as exc:
        exit_with_error(ctx, str(exc))

    details = {
        "input": str(input_path),
        "applied": apply,
        "diffs": _diffs_to_dicts(diffs),
    }
    emit_event(
        ctx,
        stage="admin-oauth-import",
        status="completed",
        message="oauth provider configuration imported" if apply else "oauth import dry-run ready",
        details=details,
    )
    if not ctx.obj.json_output:
        print_table(
            ("Provider", "Operation", "Changed fields"),
            [
                (
                    diff.provider_type,
                    diff.operation,
                    ", ".join(diff.changed_fields) if diff.changed_fields else "-",
                )
                for diff in diffs
            ],
        )
        if apply:
            get_console().print("OAuth provider configuration import applied")


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
admin_app.add_typer(oauth_app, name="oauth")
