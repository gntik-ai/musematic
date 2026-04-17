"""Install and uninstall command group."""

# mypy: disable-error-code=untyped-decorator

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Annotated

import typer

from platform_cli.config import DeploymentMode
from platform_cli.constants import PLATFORM_COMPONENTS
from platform_cli.helm.runner import HelmRunner
from platform_cli.installers.base import AbstractInstaller
from platform_cli.installers.docker import DockerComposeInstaller
from platform_cli.installers.incus import IncusInstaller
from platform_cli.installers.kubernetes import KubernetesInstaller
from platform_cli.installers.local import LocalInstaller
from platform_cli.installers.swarm import SwarmInstaller
from platform_cli.output.console import get_console, print_credentials_panel
from platform_cli.runtime import emit_event, exit_with_error, load_runtime_config

install_app = typer.Typer(
    help="Install the platform on Kubernetes, local, Docker, Swarm, or Incus.",
    no_args_is_help=True,
)


async def _run_installer(
    ctx: typer.Context, installer: AbstractInstaller, stage: str
) -> None:
    try:
        emit_event(ctx, stage=stage, status="started", message=f"{stage} started")
        result = await installer.run()
    except Exception as exc:
        exit_with_error(ctx, str(exc))
    emit_event(
        ctx,
        stage=stage,
        status="completed",
        message=f"{stage} completed",
        details=result.model_dump(mode="json"),
    )
    if not ctx.obj.json_output:
        get_console().print(
            f"{stage.title()} completed in {result.duration_seconds:.1f}s",
        )
        if result.admin_email and result.admin_password:
            url = "http://127.0.0.1:8000"
            if result.deployment_mode != DeploymentMode.LOCAL:
                url = f"http://{installer.config.ingress.hostname}"
            print_credentials_panel(result.admin_email, result.admin_password, url)


@install_app.command("kubernetes")
def install_kubernetes(
    ctx: typer.Context,
    namespace: Annotated[
        str | None, typer.Option("--namespace", envvar="PLATFORM_CLI_NAMESPACE")
    ] = None,
    storage_class: Annotated[
        str | None,
        typer.Option("--storage-class", envvar="PLATFORM_CLI_STORAGE_CLASS"),
    ] = None,
    dry_run: bool = False,
    resume: bool = False,
    air_gapped: Annotated[bool | None, typer.Option("--air-gapped")] = None,
    local_registry: Annotated[str | None, typer.Option("--local-registry")] = None,
    image_tag: Annotated[
        str | None, typer.Option("--image-tag", envvar="PLATFORM_CLI_IMAGE_TAG")
    ] = None,
    skip_preflight: bool = False,
    skip_migrations: bool = False,
) -> None:
    """Install the platform on Kubernetes."""

    config = load_runtime_config(
        ctx,
        deployment_mode=DeploymentMode.KUBERNETES,
        namespace=namespace,
        storage_class=storage_class,
        air_gapped=air_gapped,
        local_registry=local_registry,
        image_tag=image_tag,
    )
    installer = KubernetesInstaller(
        config,
        dry_run=dry_run,
        resume=resume,
        skip_preflight=skip_preflight,
        skip_migrations=skip_migrations,
    )
    asyncio.run(_run_installer(ctx, installer, "install-kubernetes"))


@install_app.command("local")
def install_local(
    ctx: typer.Context,
    data_dir: Annotated[
        Path | None, typer.Option("--data-dir", envvar="PLATFORM_CLI_DATA_DIR")
    ] = None,
    port: int = 8000,
    foreground: bool = False,
) -> None:
    """Install the platform locally."""

    config = load_runtime_config(
        ctx,
        deployment_mode=DeploymentMode.LOCAL,
        data_dir=data_dir,
    )
    installer = LocalInstaller(config, port=port, foreground=foreground)
    asyncio.run(_run_installer(ctx, installer, "install-local"))


@install_app.command("docker")
def install_docker(
    ctx: typer.Context,
    compose_file: Annotated[Path | None, typer.Option("--compose-file")] = None,
    project_name: str = "platform",
) -> None:
    """Install the platform via Docker Compose."""

    config = load_runtime_config(ctx, deployment_mode=DeploymentMode.DOCKER)
    installer = DockerComposeInstaller(config, compose_file=compose_file, project_name=project_name)
    asyncio.run(_run_installer(ctx, installer, "install-docker"))


@install_app.command("swarm")
def install_swarm(
    ctx: typer.Context,
    stack_name: str = "platform",
) -> None:
    """Install the platform via Docker Swarm."""

    config = load_runtime_config(ctx, deployment_mode=DeploymentMode.SWARM)
    installer = SwarmInstaller(config, stack_name=stack_name)
    asyncio.run(_run_installer(ctx, installer, "install-swarm"))


@install_app.command("incus")
def install_incus(
    ctx: typer.Context,
    profile: str = "platform",
) -> None:
    """Install the platform via Incus."""

    config = load_runtime_config(ctx, deployment_mode=DeploymentMode.INCUS)
    installer = IncusInstaller(config, profile=profile)
    asyncio.run(_run_installer(ctx, installer, "install-incus"))


@install_app.command("uninstall")
def uninstall(
    ctx: typer.Context,
    deployment_mode: Annotated[
        DeploymentMode,
        typer.Option("--deployment-mode", envvar="PLATFORM_CLI_DEPLOYMENT_MODE"),
    ] = DeploymentMode.KUBERNETES,
    force: bool = False,
) -> None:
    """Remove platform resources from the selected deployment target."""

    config = load_runtime_config(ctx, deployment_mode=deployment_mode)
    emit_event(ctx, stage="uninstall", status="started", message="uninstall started")
    try:
        if deployment_mode == DeploymentMode.KUBERNETES:
            runner = HelmRunner()
            for component in reversed(PLATFORM_COMPONENTS):
                runner.uninstall(f"{config.namespace}-{component.name}", component.namespace)
        elif deployment_mode == DeploymentMode.LOCAL:
            LocalInstaller.stop(config.data_dir)
            if force and config.data_dir.exists():
                shutil.rmtree(config.data_dir)
        elif deployment_mode == DeploymentMode.DOCKER:
            compose_file = Path.cwd() / "docker-compose.yml"
            __import__("subprocess").run(
                ["docker", "compose", "-f", str(compose_file), "down"],
                check=False,
                capture_output=True,
                text=True,
            )
        elif deployment_mode == DeploymentMode.SWARM:
            __import__("subprocess").run(
                ["docker", "stack", "rm", "platform"],
                check=False,
                capture_output=True,
                text=True,
            )
        elif deployment_mode == DeploymentMode.INCUS:
            __import__("subprocess").run(
                ["incus", "delete", "--force", "platform-control-plane"],
                check=False,
                capture_output=True,
                text=True,
            )
    except Exception as exc:
        exit_with_error(ctx, str(exc))
    emit_event(ctx, stage="uninstall", status="completed", message="uninstall completed")
    if not ctx.obj.json_output:
        get_console().print("Uninstall completed")
