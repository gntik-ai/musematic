"""Kubernetes installer implementation."""

from __future__ import annotations

import subprocess
from functools import partial
from uuid import uuid4

from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.constants import PLATFORM_COMPONENTS, PlatformComponent
from platform_cli.diagnostics.checker import DiagnosticRunner
from platform_cli.helm.renderer import render_values, write_values_file
from platform_cli.helm.runner import HelmRunner
from platform_cli.installers.base import AbstractInstaller, InstallerStep
from platform_cli.locking.kubernetes import KubernetesLock
from platform_cli.migrations.runner import MigrationRunner
from platform_cli.paths import helm_chart_path
from platform_cli.preflight.base import PreflightCheck, PreflightRunner
from platform_cli.preflight.kubernetes import (
    IngressControllerCheck,
    KubectlAccessCheck,
    NamespacePermissionCheck,
    StorageClassCheck,
)
from platform_cli.secrets.generator import generate_secrets, store_secrets_kubernetes


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or result.stdout.strip() or "kubectl command failed"
        )


class KubernetesInstaller(AbstractInstaller):
    """Install the platform into a Kubernetes cluster."""

    def __init__(
        self,
        config: InstallerConfig,
        *,
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
        self.config = config.model_copy(update={"deployment_mode": DeploymentMode.KUBERNETES})
        self.helm_runner = HelmRunner()
        self.migration_runner = MigrationRunner()
        self.lock = KubernetesLock()
        self.lock_holder = str(uuid4())
        self.lock_namespace = f"{self.config.namespace}-control"

    def build_steps(self) -> list[InstallerStep]:
        steps = [
            InstallerStep("preflight", "Run Kubernetes preflight checks", self.preflight),
            InstallerStep(
                "secrets", "Generate and store Kubernetes secrets", self.generate_and_store_secrets
            ),
            InstallerStep("namespaces", "Create platform namespaces", self.prepare_namespaces),
        ]
        steps.extend(
            InstallerStep(
                f"deploy-{component.name}",
                f"Deploy {component.display_name}",
                partial(self.deploy_component, component),
            )
            for component in PLATFORM_COMPONENTS
        )
        steps.extend(
            [
                InstallerStep("migrate", "Run store migrations", self.migrate),
                InstallerStep("admin", "Create admin user", self.create_admin),
                InstallerStep("verify", "Verify deployment health", self.verify),
            ]
        )
        return steps

    async def before_run(self) -> None:
        if not self.lock.acquire(self.lock_namespace, self.lock_holder):
            raise RuntimeError("another platform installation is already running")

    async def after_run(self) -> None:
        self.lock.release(self.lock_namespace, self.lock_holder)

    async def preflight(self) -> None:
        checks: list[PreflightCheck] = [
            KubectlAccessCheck(),
            NamespacePermissionCheck(self.lock_namespace),
            StorageClassCheck(self.config.storage_class),
        ]
        if self.config.ingress.enabled:
            checks.append(IngressControllerCheck())
        summary = await PreflightRunner(checks).run()
        if not summary.passed:
            first_failure = next(result for _, result in summary.results if not result.passed)
            raise RuntimeError(first_failure.remediation or first_failure.message)

    def generate_and_store_secrets(self) -> None:
        self.generated_secrets = generate_secrets(self.config.secrets)
        store_secrets_kubernetes(self.generated_secrets, self.lock_namespace)

    def prepare_namespaces(self) -> None:
        for namespace in (
            f"{self.config.namespace}-data",
            f"{self.config.namespace}-execution",
            f"{self.config.namespace}-control",
            f"{self.config.namespace}-simulation",
            f"{self.config.namespace}-edge",
            f"{self.config.namespace}-observability",
        ):
            _run(["kubectl", "create", "namespace", namespace, "--dry-run=client", "-o", "yaml"])
            _run(["kubectl", "create", "namespace", namespace])

    def deploy_component(self, component: PlatformComponent) -> None:
        if self.generated_secrets is None:
            raise RuntimeError("secrets must be generated before deployment")
        chart_path = helm_chart_path(component.helm_chart or component.name)
        rendered = render_values(component, self.config, self.generated_secrets)
        values_dir = self.config.data_dir / "rendered" / "kubernetes"
        values_file = write_values_file(rendered, values_dir / f"{component.name}.values.yaml")
        release_name = f"{self.config.namespace}-{component.name}"
        self.helm_runner.install(
            chart_path,
            release_name,
            component.namespace,
            values_file,
            dry_run=self.dry_run,
        )
        if not self.dry_run:
            self.helm_runner.wait_for_ready(component.name, component.namespace)

    async def migrate(self) -> None:
        if self.generated_secrets is None or self.dry_run:
            return
        await self.migration_runner.run_all(self.config, self.generated_secrets)

    async def create_admin(self) -> None:
        if self.generated_secrets is None or self.dry_run:
            return
        await self.migration_runner.create_admin_user(
            f"http://{self.config.ingress.hostname}"
            if not self.config.ingress.tls_enabled
            else f"https://{self.config.ingress.hostname}",
            self.config.admin.email,
            self.generated_secrets.admin_password,
        )

    async def verify(self) -> None:
        if self.dry_run:
            return
        runner = DiagnosticRunner(self.config, deployment_mode=DeploymentMode.KUBERNETES)
        self.diagnostic_report = await runner.run()
