"""Abstract installer orchestration shared by all deployment modes."""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter

from platform_cli.checkpoint.manager import CheckpointManager, InstallStepStatus
from platform_cli.config import InstallerConfig
from platform_cli.models import CheckStatus, DiagnosticReport, InstallerResult
from platform_cli.secrets.generator import GeneratedSecrets

StepHandler = Callable[[], Awaitable[None] | None]


@dataclass(slots=True)
class InstallerStep:
    """One tracked installer step."""

    name: str
    description: str
    handler: StepHandler


class AbstractInstaller(ABC):
    """Base class for resumable installers."""

    def __init__(
        self,
        config: InstallerConfig,
        *,
        dry_run: bool = False,
        resume: bool = False,
        skip_preflight: bool = False,
        skip_migrations: bool = False,
        checkpoint_manager: CheckpointManager | None = None,
    ) -> None:
        self.config = config
        self.dry_run = dry_run
        self.resume = resume
        self.skip_preflight = skip_preflight
        self.skip_migrations = skip_migrations
        self.checkpoint_manager = checkpoint_manager or CheckpointManager(
            config.data_dir / "checkpoints"
        )
        self.generated_secrets: GeneratedSecrets | None = None
        self.diagnostic_report: DiagnosticReport | None = None

    @abstractmethod
    def build_steps(self) -> list[InstallerStep]:
        """Return the ordered steps for this installer."""

    async def before_run(self) -> None:
        """Optional setup hook executed before the step loop."""

        return None

    async def after_run(self) -> None:
        """Optional teardown hook executed after the step loop."""

        return None

    async def _call_step(self, step: InstallerStep) -> None:
        result = step.handler()
        if inspect.isawaitable(result):
            await result

    def _load_or_create_checkpoint(self, steps: list[InstallerStep]) -> None:
        config_hash = self.checkpoint_manager.compute_config_hash(self.config)
        if self.resume and self.checkpoint_manager.load_latest(config_hash) is not None:
            return
        self.checkpoint_manager.create(self.config, [step.name for step in steps])

    async def run(self) -> InstallerResult:
        """Run the installer flow end-to-end with checkpoint tracking."""

        started = perf_counter()
        steps = self.build_steps()
        config_hash = self.checkpoint_manager.compute_config_hash(self.config)
        checkpoint = self.checkpoint_manager.load_latest(config_hash) if self.resume else None
        if checkpoint is None:
            self.checkpoint_manager.create(self.config, [step.name for step in steps])
            checkpoint = self.checkpoint_manager.checkpoint
        await self.before_run()
        try:
            for step in steps:
                if self.resume and checkpoint is not None:
                    matched = next(
                        (item for item in checkpoint.steps if item.name == step.name),
                        None,
                    )
                    if matched is not None and matched.status == InstallStepStatus.COMPLETED:
                        continue

                if step.name == "preflight" and self.skip_preflight:
                    self.checkpoint_manager.update_step(step.name, InstallStepStatus.SKIPPED)
                    continue
                if step.name == "migrate" and self.skip_migrations:
                    self.checkpoint_manager.update_step(step.name, InstallStepStatus.SKIPPED)
                    continue

                self.checkpoint_manager.update_step(step.name, InstallStepStatus.IN_PROGRESS)
                try:
                    await self._call_step(step)
                except Exception as exc:
                    self.checkpoint_manager.update_step(
                        step.name,
                        InstallStepStatus.FAILED,
                        error=str(exc),
                    )
                    raise
                self.checkpoint_manager.update_step(step.name, InstallStepStatus.COMPLETED)
        finally:
            await self.after_run()

        verification_status: CheckStatus | None = None
        if self.diagnostic_report is not None:
            verification_status = self.diagnostic_report.overall_status
        checkpoint_path = (
            str(self.checkpoint_manager.checkpoint_path)
            if self.checkpoint_manager.checkpoint_path is not None
            else None
        )
        return InstallerResult(
            deployment_mode=self.config.deployment_mode,
            duration_seconds=round(perf_counter() - started, 3),
            admin_email=self.config.admin.email,
            admin_password=(
                self.generated_secrets.admin_password
                if self.generated_secrets is not None
                else None
            ),
            verification_status=verification_status,
            checkpoint_path=checkpoint_path,
        )
