"""Observability stack lifecycle commands."""

# mypy: disable-error-code=untyped-decorator

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer

from platform_cli.output.console import get_console, print_table
from platform_cli.runtime import emit_event, exit_with_error, get_state


class ObservabilityPreset(StrEnum):
    minimal = "minimal"
    standard = "standard"
    enterprise = "enterprise"
    e2e = "e2e"


observability_app = typer.Typer(
    help="Manage the observability stack.",
    no_args_is_help=True,
)

_RELEASE_NAME = "observability"
_DEFAULT_NAMESPACE = "platform-observability"
_HEALTH_PROBES = {
    "loki": ("MUSEMATIC_OBS_LOKI_URL", "http://localhost:3100", "/ready"),
    "prometheus": ("MUSEMATIC_OBS_PROM_URL", "http://localhost:9090", "/-/ready"),
    "grafana": ("MUSEMATIC_OBS_GRAFANA_URL", "http://localhost:3000", "/api/health"),
    "jaeger": ("MUSEMATIC_OBS_JAEGER_URL", "http://localhost:14269", "/"),
    "otel": ("MUSEMATIC_OBS_OTEL_URL", "http://localhost:13133", "/"),
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _chart_dir() -> Path:
    return _repo_root() / "deploy" / "helm" / "observability"


def _preset_values(preset: ObservabilityPreset) -> Path:
    path = _chart_dir() / f"values-{preset.value}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"observability preset file not found: {path}")
    return path


def _run(args: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        check=check,
        capture_output=True,
        text=True,
    )


def _kubectl_json(args: Sequence[str]) -> dict[str, Any]:
    result = _run(["kubectl", *args, "-o", "json"], check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return {"items": []}
    return dict(json.loads(result.stdout))


def _preflight_s3_secret(namespace: str, preset: ObservabilityPreset) -> None:
    if preset not in {ObservabilityPreset.standard, ObservabilityPreset.enterprise}:
        return
    result = _run(
        ["kubectl", "get", "secret", "minio-platform-credentials", "-n", namespace],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "standard and enterprise presets require secret "
            f"minio-platform-credentials in namespace {namespace}. Install the platform "
            "chart first or create the generic-S3 secret before installing observability."
        )


def _helm_values_args(preset: ObservabilityPreset, overlays: Sequence[Path]) -> list[str]:
    args = ["-f", str(_preset_values(preset))]
    for overlay in overlays:
        args.extend(["-f", str(overlay)])
    return args


async def _probe_component(
    component: str,
    base_url: str,
    path: str,
    *,
    request_timeout: float,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            response = await client.get(url)
        healthy = 200 <= response.status_code < 300
        return {
            "component": component,
            "healthy": healthy,
            "status": response.status_code,
            "url": url,
            "detail": response.text[:160],
        }
    except Exception as exc:
        return {
            "component": component,
            "healthy": False,
            "status": None,
            "url": url,
            "detail": f"{type(exc).__name__}: {exc}",
        }


async def _probe_observability(request_timeout: float = 5.0) -> list[dict[str, Any]]:
    tasks = []
    for component, (env_name, default_base_url, path) in _HEALTH_PROBES.items():
        base_url = os.getenv(env_name, default_base_url)
        tasks.append(_probe_component(component, base_url, path, request_timeout=request_timeout))
    return list(await asyncio.gather(*tasks))


def _render_health(ctx: typer.Context, probes: list[dict[str, Any]]) -> None:
    if get_state(ctx).json_output:
        typer.echo(json.dumps({"components": probes}, sort_keys=True))
        return
    rows = []
    for probe in probes:
        glyph = "✓" if probe["healthy"] else "✗"
        rows.append(
            [
                probe["component"],
                glyph,
                probe["status"] if probe["status"] is not None else "-",
                probe["url"],
            ]
        )
    print_table(["Component", "Health", "Status", "Endpoint"], rows)


def _helm_install_or_upgrade(
    ctx: typer.Context,
    *,
    command: str,
    preset: ObservabilityPreset,
    namespace: str,
    values: Sequence[Path],
    wait: bool,
) -> None:
    try:
        _preflight_s3_secret(namespace, preset)
    except Exception as exc:
        exit_with_error(ctx, str(exc))

    args = [
        "helm",
        "upgrade",
        "--install" if command == "install" else _RELEASE_NAME,
    ]
    if command == "install":
        args.extend([_RELEASE_NAME, str(_chart_dir())])
    else:
        args.append(str(_chart_dir()))
    args.extend(["-n", namespace, "--create-namespace"])
    args.extend(_helm_values_args(preset, values))
    if wait:
        args.append("--wait")

    emit_event(ctx, stage=f"observability-{command}", status="started", message="helm started")
    result = _run(args, check=False)
    if result.returncode != 0:
        exit_with_error(
            ctx,
            result.stderr.strip() or result.stdout.strip() or f"helm {command} failed",
        )
    emit_event(ctx, stage=f"observability-{command}", status="completed", message="helm completed")
    if not get_state(ctx).json_output:
        get_console().print(result.stdout.strip())

    if wait:
        probes = asyncio.run(_probe_observability())
        _render_health(ctx, probes)
        if any(not probe["healthy"] for probe in probes):
            raise typer.Exit(1)


@observability_app.command("install")
def install(
    ctx: typer.Context,
    preset: Annotated[
        ObservabilityPreset,
        typer.Option("--preset", case_sensitive=False, help="Sizing preset to install."),
    ] = ObservabilityPreset.standard,
    namespace: Annotated[
        str,
        typer.Option("--namespace", envvar="PLATFORM_OBSERVABILITY_NAMESPACE"),
    ] = _DEFAULT_NAMESPACE,
    values: Annotated[
        list[Path] | None,
        typer.Option("--values", "-f", exists=True, dir_okay=False, resolve_path=True),
    ] = None,
    wait: Annotated[bool, typer.Option("--wait", help="Wait for Helm and probe health.")] = False,
) -> None:
    """Install the observability umbrella chart."""

    _helm_install_or_upgrade(
        ctx,
        command="install",
        preset=preset,
        namespace=namespace,
        values=values or [],
        wait=wait,
    )


@observability_app.command("upgrade")
def upgrade(
    ctx: typer.Context,
    preset: Annotated[
        ObservabilityPreset,
        typer.Option("--preset", case_sensitive=False, help="Sizing preset to apply."),
    ] = ObservabilityPreset.standard,
    namespace: Annotated[
        str,
        typer.Option("--namespace", envvar="PLATFORM_OBSERVABILITY_NAMESPACE"),
    ] = _DEFAULT_NAMESPACE,
    values: Annotated[
        list[Path] | None,
        typer.Option("--values", "-f", exists=True, dir_okay=False, resolve_path=True),
    ] = None,
    wait: Annotated[bool, typer.Option("--wait", help="Wait for Helm and probe health.")] = False,
) -> None:
    """Upgrade the observability umbrella chart."""

    _helm_install_or_upgrade(
        ctx,
        command="upgrade",
        preset=preset,
        namespace=namespace,
        values=values or [],
        wait=wait,
    )


def _resources_for_purge(namespace: str) -> list[tuple[str, str, str]]:
    namespaced_kinds = ["pvc", "configmap"]
    resources: list[tuple[str, str, str]] = []
    selector = "app.kubernetes.io/instance=observability,app.kubernetes.io/managed-by=Helm"
    for kind in namespaced_kinds:
        payload = _kubectl_json(["get", kind, "-n", namespace, "-l", selector])
        for item in payload.get("items", []):
            resources.append((kind, namespace, str(item["metadata"]["name"])))
    for kind in ["crd", "validatingwebhookconfiguration", "mutatingwebhookconfiguration"]:
        payload = _kubectl_json(["get", kind, "-l", selector])
        for item in payload.get("items", []):
            resources.append((kind, "", str(item["metadata"]["name"])))
    return resources


@observability_app.command("uninstall")
def uninstall(
    ctx: typer.Context,
    namespace: Annotated[
        str,
        typer.Option("--namespace", envvar="PLATFORM_OBSERVABILITY_NAMESPACE"),
    ] = _DEFAULT_NAMESPACE,
    purge_pvcs: Annotated[
        bool,
        typer.Option("--purge-pvcs", help="Delete Helm-owned residual PVCs and related resources."),
    ] = False,
) -> None:
    """Uninstall the observability chart and optionally purge Helm-owned leftovers."""

    result = _run(["helm", "uninstall", _RELEASE_NAME, "-n", namespace], check=False)
    if result.returncode != 0 and "not found" not in result.stderr.lower():
        exit_with_error(ctx, result.stderr.strip() or "helm uninstall failed")
    resources = _resources_for_purge(namespace)
    if resources and not get_state(ctx).json_output:
        print_table(["Kind", "Namespace", "Name"], resources)
    if not purge_pvcs:
        if resources and not get_state(ctx).json_output:
            get_console().print("Residual Helm-owned resources were listed but not deleted.")
        return
    if resources and not typer.confirm("Delete the listed residual resources?", default=False):
        raise typer.Exit(1)
    for kind, resource_namespace, name in resources:
        args = ["kubectl", "delete", kind, name]
        if resource_namespace:
            args.extend(["-n", resource_namespace])
        _run(args, check=False)


@observability_app.command("status")
def status(
    ctx: typer.Context,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a single JSON status object."),
    ] = False,
) -> None:
    """Probe observability health endpoints and report component status."""

    original_json = get_state(ctx).json_output
    if json_output:
        get_state(ctx).json_output = True
    try:
        probes = asyncio.run(_probe_observability())
        _render_health(ctx, probes)
    finally:
        get_state(ctx).json_output = original_json
    if any(not probe["healthy"] for probe in probes):
        raise typer.Exit(1)
