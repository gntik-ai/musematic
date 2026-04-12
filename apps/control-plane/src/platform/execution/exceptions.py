from __future__ import annotations

from platform.common.exceptions import NotFoundError, ValidationError


class ExecutionNotFoundError(NotFoundError):
    def __init__(self, execution_id: object) -> None:
        super().__init__("EXECUTION_NOT_FOUND", f"Execution '{execution_id}' was not found")


class ExecutionAlreadyRunningError(ValidationError):
    def __init__(self, execution_id: object) -> None:
        super().__init__(
            "EXECUTION_ALREADY_RUNNING",
            f"Execution '{execution_id}' is already running",
        )


class HotChangeIncompatibleError(ValidationError):
    def __init__(self, issues: list[str]) -> None:
        super().__init__(
            "HOT_CHANGE_INCOMPATIBLE",
            "Workflow version is not compatible with the active execution",
            {"issues": issues},
        )


class ApprovalAlreadyDecidedError(ValidationError):
    def __init__(self, execution_id: object, step_id: str) -> None:
        super().__init__(
            "APPROVAL_ALREADY_DECIDED",
            f"Approval for execution '{execution_id}' step '{step_id}' was already decided",
        )
