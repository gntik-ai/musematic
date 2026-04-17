"""Concurrent diagnostics runner and auto-remediation hooks."""

from __future__ import annotations

import asyncio
import subprocess
from time import perf_counter

from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.constants import PLATFORM_COMPONENTS
from platform_cli.diagnostics.checks.clickhouse import ClickHouseCheck
from platform_cli.diagnostics.checks.grpc_services import GrpcServiceCheck
from platform_cli.diagnostics.checks.kafka import KafkaCheck
from platform_cli.diagnostics.checks.minio import MinIOCheck
from platform_cli.diagnostics.checks.model_providers import ModelProviderCheck
from platform_cli.diagnostics.checks.neo4j import Neo4jCheck
from platform_cli.diagnostics.checks.opensearch import OpenSearchCheck
from platform_cli.diagnostics.checks.postgresql import PostgreSQLCheck
from platform_cli.diagnostics.checks.qdrant import QdrantCheck
from platform_cli.diagnostics.checks.redis import RedisCheck
from platform_cli.models import (
    AutoFixResult,
    CheckStatus,
    DiagnosticCheck,
    DiagnosticReport,
    utc_now_iso,
)
from platform_cli.paths import helm_chart_path
from platform_cli.secrets.generator import GeneratedSecrets


def _status_rank(status: CheckStatus) -> int:
    order = {
        CheckStatus.HEALTHY: 0,
        CheckStatus.UNKNOWN: 1,
        CheckStatus.DEGRADED: 2,
        CheckStatus.UNHEALTHY: 3,
    }
    return order[status]


def _service_host(config: InstallerConfig, service: str, namespace: str, port: int) -> str:
    if config.deployment_mode == DeploymentMode.LOCAL:
        return f"127.0.0.1:{port}"
    return f"{service}.{namespace}.svc.cluster.local:{port}"


class DiagnosticRunner:
    """Run health checks concurrently and compute an aggregate report."""

    def __init__(
        self,
        config: InstallerConfig,
        *,
        deployment_mode: DeploymentMode | None = None,
        selected_checks: set[str] | None = None,
        secrets: GeneratedSecrets | None = None,
    ) -> None:
        self.config = config.model_copy(
            update={"deployment_mode": deployment_mode or config.deployment_mode}
        )
        self.selected_checks = selected_checks
        self.secrets = secrets

    @classmethod
    def auto_detect_mode(cls, config: InstallerConfig) -> DeploymentMode:
        """Best-effort deployment mode detection."""

        if (config.data_dir / "platform.pid").exists():
            return DeploymentMode.LOCAL
        if (helm_chart_path("control-plane")).exists():
            return DeploymentMode.KUBERNETES
        return config.deployment_mode

    def build_checks(self) -> list[object]:
        """Build the diagnostic check objects for the current mode."""

        namespace = f"{self.config.namespace}-data"
        checks: list[object] = [
            PostgreSQLCheck(
                "postgresql://postgres:password@127.0.0.1:5432/platform"
                if self.config.deployment_mode == DeploymentMode.LOCAL
                else f"postgresql://postgres:password@postgresql.{namespace}.svc.cluster.local:5432/platform"
            ),
            RedisCheck(
                "redis://127.0.0.1:6379/0"
                if self.config.deployment_mode == DeploymentMode.LOCAL
                else f"redis://redis.{namespace}.svc.cluster.local:6379/0"
            ),
            KafkaCheck(
                "127.0.0.1:9092"
                if self.config.deployment_mode == DeploymentMode.LOCAL
                else f"kafka.{namespace}.svc.cluster.local:9092"
            ),
            QdrantCheck(
                "http://127.0.0.1:6333"
                if self.config.deployment_mode == DeploymentMode.LOCAL
                else f"http://qdrant.{namespace}.svc.cluster.local:6333"
            ),
            Neo4jCheck(
                "bolt://127.0.0.1:7687"
                if self.config.deployment_mode == DeploymentMode.LOCAL
                else f"bolt://neo4j.{namespace}.svc.cluster.local:7687",
                password=(self.secrets.neo4j_password if self.secrets else "password"),
            ),
            ClickHouseCheck(
                "127.0.0.1"
                if self.config.deployment_mode == DeploymentMode.LOCAL
                else f"clickhouse.{namespace}.svc.cluster.local"
            ),
            OpenSearchCheck(
                "http://127.0.0.1:9200"
                if self.config.deployment_mode == DeploymentMode.LOCAL
                else f"http://opensearch.{namespace}.svc.cluster.local:9200"
            ),
            MinIOCheck(
                "http://127.0.0.1:9000"
                if self.config.deployment_mode == DeploymentMode.LOCAL
                else f"http://minio.{namespace}.svc.cluster.local:9000",
                access_key=self.secrets.minio_access_key if self.secrets else "minio",
                secret_key=self.secrets.minio_secret_key if self.secrets else "minio-secret",
            ),
            GrpcServiceCheck(
                "127.0.0.1"
                if self.config.deployment_mode == DeploymentMode.LOCAL
                else "runtime-controller.platform-execution.svc.cluster.local",
                50051,
                "runtime-controller",
                "Runtime Controller",
            ),
            GrpcServiceCheck(
                "127.0.0.1"
                if self.config.deployment_mode == DeploymentMode.LOCAL
                else "reasoning-engine.platform-execution.svc.cluster.local",
                50052,
                "reasoning-engine",
                "Reasoning Engine",
            ),
        ]
        if helm_chart_path("sandbox-manager").exists():
            checks.append(
                GrpcServiceCheck(
                    "127.0.0.1"
                    if self.config.deployment_mode == DeploymentMode.LOCAL
                    else "sandbox-manager.platform-execution.svc.cluster.local",
                    50053,
                    "sandbox-manager",
                    "Sandbox Manager",
                )
            )
        if helm_chart_path("simulation-controller").exists():
            checks.append(
                GrpcServiceCheck(
                    "127.0.0.1"
                    if self.config.deployment_mode == DeploymentMode.LOCAL
                    else "simulation-controller.platform-simulation.svc.cluster.local",
                    50055,
                    "simulation-controller",
                    "Simulation Controller",
                )
            )
        checks.extend(ModelProviderCheck(url) for url in self.config.model_provider_urls)
        if not self.selected_checks:
            return checks
        return [check for check in checks if getattr(check, "name", "") in self.selected_checks]

    async def _run_one(self, check: object, timeout_per_check: int) -> DiagnosticCheck:
        try:
            return await asyncio.wait_for(check.run(), timeout=timeout_per_check)  # type: ignore[attr-defined]
        except TimeoutError:
            name = getattr(check, "name", "unknown")
            component = next((item for item in PLATFORM_COMPONENTS if item.name == name), None)
            return DiagnosticCheck(
                component=name,
                display_name=component.display_name if component else name,
                category=component.category if component else PLATFORM_COMPONENTS[0].category,
                status=CheckStatus.UNKNOWN,
                error="timed out",
                remediation="Investigate slow response or network issues.",
            )

    async def run(self, timeout_per_check: int = 5) -> DiagnosticReport:
        """Run all configured checks concurrently."""

        started = perf_counter()
        checks = self.build_checks()
        results = await asyncio.gather(
            *[self._run_one(check, timeout_per_check) for check in checks],
        )
        overall = (
            max(results, key=lambda item: _status_rank(item.status)).status
            if results
            else CheckStatus.UNKNOWN
        )
        return DiagnosticReport(
            deployment_mode=self.config.deployment_mode,
            checked_at=utc_now_iso(),
            duration_seconds=round(perf_counter() - started, 3),
            overall_status=overall,
            checks=list(results),
        )

    async def auto_fix(self, report: DiagnosticReport) -> list[AutoFixResult]:
        """Attempt simple best-effort remediations for a report."""

        results: list[AutoFixResult] = []
        component_map = {component.name: component for component in PLATFORM_COMPONENTS}
        for check in report.checks:
            if check.status == CheckStatus.HEALTHY:
                continue
            component = component_map.get(check.component)
            if component is not None and self.config.deployment_mode == DeploymentMode.KUBERNETES:
                command = [
                    "kubectl",
                    "rollout",
                    "restart",
                    f"deployment/{component.name}",
                    "-n",
                    component.namespace,
                ]
                process = subprocess.run(command, capture_output=True, text=True, check=False)
                success = process.returncode == 0
                results.append(
                    AutoFixResult(
                        component=check.component,
                        action="rollout_restart",
                        success=success,
                        message=process.stderr.strip()
                        or process.stdout.strip()
                        or "restart attempted",
                    )
                )
        return results
