"""Local single-node installer implementation."""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from time import monotonic

import httpx

from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.diagnostics.checker import DiagnosticRunner
from platform_cli.installers.base import AbstractInstaller, InstallerStep
from platform_cli.locking.file import FileLock
from platform_cli.migrations.runner import MigrationRunner
from platform_cli.paths import CONTROL_PLANE_SRC
from platform_cli.preflight.base import PreflightRunner
from platform_cli.preflight.local import DiskSpaceCheck, PortAvailabilityCheck
from platform_cli.secrets.generator import generate_secrets, store_secrets_local


class LocalInstaller(AbstractInstaller):
    """Install the platform using local fallbacks and subprocesses."""

    def __init__(
        self,
        config: InstallerConfig,
        *,
        port: int = 8000,
        foreground: bool = False,
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
        self.config = config.model_copy(update={"deployment_mode": DeploymentMode.LOCAL})
        self.port = port
        self.foreground = foreground
        self.lock = FileLock(self.config.data_dir / "install.lock")
        self.migration_runner = MigrationRunner()
        self.process: subprocess.Popen[str] | None = None
        self.qdrant_process: subprocess.Popen[str] | None = None

    @property
    def pid_path(self) -> Path:
        return self.config.data_dir / "platform.pid"

    @property
    def sqlite_path(self) -> Path:
        return self.config.data_dir / "db" / "platform.db"

    def build_steps(self) -> list[InstallerStep]:
        return [
            InstallerStep("preflight", "Run local preflight checks", self.preflight),
            InstallerStep("directories", "Create data directories", self.prepare_directories),
            InstallerStep("database", "Initialise SQLite database", self.initialize_database),
            InstallerStep("qdrant", "Start local Qdrant", self.start_qdrant),
            InstallerStep("secrets", "Generate local secrets", self.generate_and_store_secrets),
            InstallerStep("control-plane", "Start control plane", self.start_control_plane),
            InstallerStep("migrate", "Run local migrations", self.migrate),
            InstallerStep("admin", "Create admin user", self.create_admin),
            InstallerStep("verify", "Verify local health", self.verify),
        ]

    async def before_run(self) -> None:
        if not self.lock.acquire():
            raise RuntimeError("another local installation is already running")

    async def after_run(self) -> None:
        self.lock.release()

    async def preflight(self) -> None:
        summary = await PreflightRunner(
            [
                DiskSpaceCheck(self.config.data_dir),
                PortAvailabilityCheck((self.port, 6333)),
            ]
        ).run()
        if not summary.passed:
            first_failure = next(result for _, result in summary.results if not result.passed)
            raise RuntimeError(first_failure.remediation or first_failure.message)

    def prepare_directories(self) -> None:
        for relative in ("db", "storage", "logs"):
            (self.config.data_dir / relative).mkdir(parents=True, exist_ok=True)

    def initialize_database(self) -> None:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.touch(exist_ok=True)

    def start_qdrant(self) -> None:
        binary = shutil.which("qdrant")
        if binary is None:
            return
        self.qdrant_process = subprocess.Popen(
            [binary, "--storage", ":memory:", "--port", "6333"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )

    def generate_and_store_secrets(self) -> None:
        self.generated_secrets = generate_secrets(self.config.secrets)
        store_secrets_local(self.generated_secrets, self.config.data_dir)

    def build_local_env(self) -> dict[str, str]:
        env = os.environ.copy()
        pythonpath_segments = [str(CONTROL_PLANE_SRC)]
        if env.get("PYTHONPATH"):
            pythonpath_segments.append(env["PYTHONPATH"])
        env.update(
            {
                "PYTHONPATH": os.pathsep.join(pythonpath_segments),
                "DATABASE_URL": f"sqlite+aiosqlite:///{self.sqlite_path}",
                "QDRANT_URL": "http://127.0.0.1:6333",
                "REDIS_TEST_MODE": "standalone",
                "KAFKA_MODE": "local",
                "MINIO_ENDPOINT": f"file://{self.config.data_dir / 'storage'}",
            }
        )
        return env

    async def start_control_plane(self) -> None:
        logs_dir = self.config.data_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stdout = (
            None if self.foreground else (logs_dir / "platform.out").open("a", encoding="utf-8")
        )
        stderr = (
            None if self.foreground else (logs_dir / "platform.err").open("a", encoding="utf-8")
        )
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "platform.main:create_app",
                "--factory",
                "--host",
                "0.0.0.0",
                "--port",
                str(self.port),
            ],
            cwd=str(CONTROL_PLANE_SRC),
            env=self.build_local_env(),
            stdout=stdout,
            stderr=stderr,
            text=True,
        )
        self.pid_path.write_text(str(self.process.pid), encoding="utf-8")
        await self.wait_for_health()

    async def wait_for_health(self, timeout_seconds: int = 30) -> None:
        deadline = monotonic() + timeout_seconds
        async with httpx.AsyncClient(timeout=2.0) as client:
            while monotonic() < deadline:
                try:
                    response = await client.get(f"http://127.0.0.1:{self.port}/health")
                    if response.status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.2)
        raise RuntimeError("local control plane did not become healthy in time")

    async def migrate(self) -> None:
        self.migration_runner.run_alembic(f"sqlite+aiosqlite:///{self.sqlite_path}")

    async def create_admin(self) -> None:
        if self.generated_secrets is None:
            raise RuntimeError("secrets must be generated before admin creation")
        await self.migration_runner.create_admin_user(
            f"http://127.0.0.1:{self.port}",
            self.config.admin.email,
            self.generated_secrets.admin_password,
        )

    async def verify(self) -> None:
        runner = DiagnosticRunner(self.config, deployment_mode=DeploymentMode.LOCAL)
        self.diagnostic_report = await runner.run()

    @classmethod
    def stop(cls, data_dir: Path) -> bool:
        """Stop the local platform process tracked by a PID file."""

        pid_path = data_dir / "platform.pid"
        if not pid_path.exists():
            return False
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        os.kill(pid, signal.SIGTERM)
        pid_path.unlink(missing_ok=True)
        return True
