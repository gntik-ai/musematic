"""Incus installer."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.constants import PLATFORM_COMPONENTS
from platform_cli.diagnostics.checker import DiagnosticRunner
from platform_cli.installers.base import AbstractInstaller, InstallerStep
from platform_cli.migrations.runner import MigrationRunner
from platform_cli.preflight.base import PreflightResult, PreflightRunner
from platform_cli.secrets.generator import generate_secrets, store_secrets_local


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "incus command failed")


class IncusAccessCheck:
    """Basic check that the Incus CLI exists and is responsive."""

    name = "incus-access"
    description = "Verify the incus CLI is available"

    async def check(self) -> PreflightResult:
        result = subprocess.run(
            ["incus", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return PreflightResult(True, result.stdout.strip() or "Incus available")
        return PreflightResult(
            False, "incus command unavailable", "Install Incus and authenticate."
        )


class IncusInstaller(AbstractInstaller):
    """Render and launch a basic Incus deployment profile."""

    def __init__(
        self,
        config: InstallerConfig,
        *,
        profile: str = "platform",
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
        self.config = config.model_copy(update={"deployment_mode": DeploymentMode.INCUS})
        self.profile = profile
        self.profile_file = Path.cwd() / f"{profile}.incus.yml"
        self.migration_runner = MigrationRunner()

    def build_steps(self) -> list[InstallerStep]:
        return [
            InstallerStep("preflight", "Run Incus preflight checks", self.preflight),
            InstallerStep("secrets", "Generate Incus secrets", self.generate_and_store_secrets),
            InstallerStep("profile", "Render Incus profile", self.render_profile),
            InstallerStep("deploy", "Launch Incus containers", self.deploy),
            InstallerStep("migrate", "Run migrations", self.migrate),
            InstallerStep("admin", "Create admin user", self.create_admin),
            InstallerStep("verify", "Verify Incus deployment", self.verify),
        ]

    async def preflight(self) -> None:
        summary = await PreflightRunner([IncusAccessCheck()]).run()
        if not summary.passed:
            first_failure = next(result for _, result in summary.results if not result.passed)
            raise RuntimeError(first_failure.remediation or first_failure.message)

    def generate_and_store_secrets(self) -> None:
        self.generated_secrets = generate_secrets(self.config.secrets)
        store_secrets_local(self.generated_secrets, self.config.data_dir / "incus")

    def render_profile(self) -> None:
        payload = {
            "name": self.profile,
            "components": [component.name for component in PLATFORM_COMPONENTS],
        }
        self.profile_file.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    def deploy(self) -> None:
        _run(["incus", "profile", "create", self.profile])
        for component in PLATFORM_COMPONENTS:
            _run(
                [
                    "incus",
                    "launch",
                    "images:ubuntu/24.04",
                    f"{self.profile}-{component.name}",
                    "--profile",
                    self.profile,
                ]
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
        runner = DiagnosticRunner(self.config, deployment_mode=DeploymentMode.INCUS)
        self.diagnostic_report = await runner.run()
