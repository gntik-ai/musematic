from __future__ import annotations

from datetime import datetime
from platform.common.exceptions import NotFoundError, PlatformError, ValidationError
from platform.multi_region_ops.constants import ACTIVE_ACTIVE_RUNBOOK_PATH
from typing import Any
from uuid import UUID


class RegionNotFoundError(NotFoundError):
    def __init__(self, region_id: UUID | str) -> None:
        super().__init__(
            "REGION_NOT_FOUND",
            f"Region {region_id} not found",
            {"region_id": str(region_id)},
        )


class ActiveActiveConfigurationRefusedError(ValidationError):
    def __init__(self) -> None:
        super().__init__(
            "ACTIVE_ACTIVE_CONFIGURATION_REFUSED",
            (
                "Only one enabled primary region is supported by default. Review the "
                "active-active considerations runbook before changing that posture."
            ),
            {"runbook": ACTIVE_ACTIVE_RUNBOOK_PATH},
        )


class FailoverPlanNotFoundError(NotFoundError):
    def __init__(self, plan_id: UUID | str) -> None:
        super().__init__(
            "FAILOVER_PLAN_NOT_FOUND",
            f"Failover plan {plan_id} not found",
            {"plan_id": str(plan_id)},
        )


class FailoverRunNotFoundError(NotFoundError):
    def __init__(self, run_id: UUID | str) -> None:
        super().__init__(
            "FAILOVER_RUN_NOT_FOUND",
            f"Failover plan run {run_id} not found",
            {"run_id": str(run_id)},
        )


class FailoverInProgressError(PlatformError):
    status_code = 409

    def __init__(
        self, *, from_region: str, to_region: str, running_run_id: str | None = None
    ) -> None:
        super().__init__(
            "FAILOVER_IN_PROGRESS",
            f"A failover is already running for {from_region} -> {to_region}",
            {
                "from_region": from_region,
                "to_region": to_region,
                "running_run_id": running_run_id,
            },
        )


class FailoverStepHaltedError(Exception):
    def __init__(self, step_name: str, reason: str) -> None:
        super().__init__(reason)
        self.step_name = step_name
        self.reason = reason


class MaintenanceWindowNotFoundError(NotFoundError):
    def __init__(self, window_id: UUID | str) -> None:
        super().__init__(
            "MAINTENANCE_WINDOW_NOT_FOUND",
            f"Maintenance window {window_id} not found",
            {"window_id": str(window_id)},
        )


class MaintenanceWindowOverlapError(PlatformError):
    status_code = 409

    def __init__(self, conflicting_window_id: UUID | str) -> None:
        super().__init__(
            "MAINTENANCE_WINDOW_OVERLAP",
            "Maintenance window overlaps with an existing scheduled or active window",
            {"conflicting_window_id": str(conflicting_window_id)},
        )


class MaintenanceWindowInPastError(ValidationError):
    def __init__(self) -> None:
        super().__init__(
            "MAINTENANCE_WINDOW_IN_PAST",
            "Maintenance windows must start in the future",
        )


class MaintenanceModeBlockedError(PlatformError):
    status_code = 503

    def __init__(
        self,
        *,
        reason: str | None,
        ends_at: datetime,
        announcement: str | None,
    ) -> None:
        super().__init__(
            "MAINTENANCE_IN_PROGRESS",
            "Maintenance mode is active",
            {
                "reason": reason,
                "ends_at": ends_at.isoformat(),
                "announcement": announcement,
            },
        )


class MaintenanceDisableFailedError(Exception):
    def __init__(self, reason: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}
