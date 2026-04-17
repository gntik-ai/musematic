"""Docker Compose installer."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.constants import PLATFORM_COMPONENTS
from platform_cli.diagnostics.checker import DiagnosticRunner
from platform_cli.installers.base import AbstractInstaller, InstallerStep
from platform_cli.migrations.runner import MigrationRunner
from platform_cli.preflight.base import PreflightRunner
from platform_cli.preflight.docker import ComposeVersionCheck, DockerDaemonCheck
from platform_cli.secrets.generator import generate_secrets, store_secrets_env_file


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or result.stdout.strip() or "docker command failed"
        )


class DockerComposeInstaller(AbstractInstaller):
    """Render and run a Docker Compose deployment."""

    def __init__(
        self,
        config: InstallerConfig,
        *,
        compose_file: Path | None = None,
        project_name: str = "platform",
        dry_run: bool = False,
        resume: bool = False,
        skip_preflight: bool = False,
        skip_migrations: bool = False,
    ) -> None:
        super().__init__(
            config,
            dry_run=dry_run,
            resume=resume,
            skip_preflight=skip_preflight,
            skip_migrations=skip_migrations,
        )
        self.config = config.model_copy(update={"deployment_mode": DeploymentMode.DOCKER})
        self.compose_file = compose_file or Path.cwd() / "docker-compose.yml"
        self.project_name = project_name
        self.migration_runner = MigrationRunner()

    def build_steps(self) -> list[InstallerStep]:
        return [
            InstallerStep("preflight", "Run Docker preflight checks", self.preflight),
            InstallerStep(
                "secrets", "Generate Docker env secrets", self.generate_and_store_secrets
            ),
            InstallerStep("compose", "Render docker-compose.yml", self.render_compose),
            InstallerStep("deploy", "Start Compose project", self.deploy),
            InstallerStep("migrate", "Run migrations", self.migrate),
            InstallerStep("admin", "Create admin user", self.create_admin),
            InstallerStep("verify", "Verify Docker deployment", self.verify),
        ]

    async def preflight(self) -> None:
        summary = await PreflightRunner([DockerDaemonCheck(), ComposeVersionCheck()]).run()
        if not summary.passed:
            first_failure = next(result for _, result in summary.results if not result.passed)
            raise RuntimeError(first_failure.remediation or first_failure.message)

    def generate_and_store_secrets(self) -> None:
        self.generated_secrets = generate_secrets(self.config.secrets)
        store_secrets_env_file(self.generated_secrets, self.config.data_dir / ".env")

    def render_compose(self) -> None:
        services: dict[str, object] = {}
        for component in PLATFORM_COMPONENTS:
            image = (
                f"{self.config.image_registry}/musematic/"
                f"{component.name}:{self.config.image_tag}"
            )
            services[component.name] = {
                "image": image,
                "restart": "unless-stopped",
                "environment": {"PLATFORM_COMPONENT": component.name},
            }
        self.compose_file.write_text(
            yaml.safe_dump({"services": services, "version": "3.9"}, sort_keys=True),
            encoding="utf-8",
        )

    def deploy(self) -> None:
        _run(
            ["docker", "compose", "-p", self.project_name, "-f", str(self.compose_file), "up", "-d"]
        )

    async def migrate(self) -> None:
        if self.generated_secrets is None:
            raise RuntimeError("secrets must be generated before migrations")
        await self.migration_runner.run_all(self.config, self.generated_secrets)

    async def create_admin(self) -> None:
        if self.generated_secrets is None:
            raise RuntimeError("secrets must be generated before admin creation")
        await self.migration_runner.create_admin_user(
            "http://127.0.0.1:8000",
            self.config.admin.email,
            self.generated_secrets.admin_password,
        )

    async def verify(self) -> None:
        runner = DiagnosticRunner(self.config, deployment_mode=DeploymentMode.DOCKER)
        self.diagnostic_report = await runner.run()
