from __future__ import annotations

from platform.common.exceptions import NotFoundError, ValidationError


class WorkflowNotFoundError(NotFoundError):
    def __init__(self, workflow_id: object) -> None:
        super().__init__("WORKFLOW_NOT_FOUND", f"Workflow '{workflow_id}' was not found")


class WorkflowCompilationError(ValidationError):
    def __init__(
        self,
        message: str,
        *,
        path: str | None = None,
        value: object | None = None,
        code: str = "WORKFLOW_COMPILATION_ERROR",
    ) -> None:
        details: dict[str, object] = {}
        if path is not None:
            details["path"] = path
        if value is not None:
            details["value"] = value
        super().__init__(code, message, details)


class TriggerNotFoundError(NotFoundError):
    def __init__(self, trigger_id: object) -> None:
        super().__init__("TRIGGER_NOT_FOUND", f"Trigger '{trigger_id}' was not found")
