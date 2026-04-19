from __future__ import annotations

from platform.common.exceptions import NotFoundError, PlatformError, ValidationError


class ExecutionNotFoundError(NotFoundError):
    """Raise when execution not found."""

    def __init__(self, execution_id: object) -> None:
        super().__init__("EXECUTION_NOT_FOUND", f"Execution '{execution_id}' was not found")


class ExecutionAlreadyRunningError(ValidationError):
    """Raise when execution already running."""

    def __init__(self, execution_id: object) -> None:
        super().__init__(
            "EXECUTION_ALREADY_RUNNING",
            f"Execution '{execution_id}' is already running",
        )


class HotChangeIncompatibleError(ValidationError):
    """Raise when hot change incompatible."""

    def __init__(self, issues: list[str]) -> None:
        super().__init__(
            "HOT_CHANGE_INCOMPATIBLE",
            "Workflow version is not compatible with the active execution",
            {"issues": issues},
        )


class ApprovalAlreadyDecidedError(ValidationError):
    """Raise when approval already decided."""

    def __init__(self, execution_id: object, step_id: str) -> None:
        super().__init__(
            "APPROVAL_ALREADY_DECIDED",
            f"Approval for execution '{execution_id}' step '{step_id}' was already decided",
        )


class CheckpointSizeLimitExceededError(ValidationError):
    """Raise when checkpoint payload exceeds the configured size limit."""

    def __init__(self, size_bytes: int, limit_bytes: int) -> None:
        super().__init__(
            "CHECKPOINT_SIZE_LIMIT_EXCEEDED",
            "Checkpoint snapshot exceeds the configured size limit",
            {"size_bytes": size_bytes, "limit_bytes": limit_bytes},
        )


CheckpointSizeLimitExceeded = CheckpointSizeLimitExceededError


class RollbackNotEligibleError(PlatformError):
    """Raise when an execution cannot be rolled back in its current state."""

    status_code = 409

    def __init__(self, execution_id: object, status: object) -> None:
        super().__init__(
            "ROLLBACK_NOT_ELIGIBLE",
            f"Execution '{execution_id}' in status '{status}' cannot be rolled back",
            {"execution_id": str(execution_id), "status": str(status)},
        )


class CheckpointRetentionExpiredError(PlatformError):
    """Raise when a checkpoint is outside the rollback retention window."""

    status_code = 410

    def __init__(self, execution_id: object, checkpoint_number: int) -> None:
        super().__init__(
            "CHECKPOINT_RETENTION_EXPIRED",
            (
                f"Checkpoint '{checkpoint_number}' for execution '{execution_id}' "
                "is outside the rollback retention window"
            ),
            {
                "execution_id": str(execution_id),
                "checkpoint_number": checkpoint_number,
            },
        )


class RollbackFailedError(PlatformError):
    """Raise when rollback persistence fails and the execution is quarantined."""

    status_code = 500

    def __init__(self, execution_id: object, checkpoint_number: int, reason: str) -> None:
        super().__init__(
            "ROLLBACK_FAILED",
            (
                f"Rollback for execution '{execution_id}' to checkpoint "
                f"'{checkpoint_number}' failed"
            ),
            {
                "execution_id": str(execution_id),
                "checkpoint_number": checkpoint_number,
                "reason": reason,
            },
        )


class CheckpointNotFoundError(NotFoundError):
    """Raise when a checkpoint number is missing for an execution."""

    def __init__(self, execution_id: object, checkpoint_number: int) -> None:
        super().__init__(
            "CHECKPOINT_NOT_FOUND",
            f"Checkpoint '{checkpoint_number}' for execution '{execution_id}' was not found",
        )


class ReprioritizationTriggerNotFoundError(NotFoundError):
    """Raise when a reprioritization trigger does not exist."""

    def __init__(self, trigger_id: object) -> None:
        super().__init__(
            "REPRIORITIZATION_TRIGGER_NOT_FOUND",
            f"Reprioritization trigger '{trigger_id}' was not found",
        )
