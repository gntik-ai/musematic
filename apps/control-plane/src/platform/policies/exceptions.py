from __future__ import annotations

from platform.common.exceptions import (
    AuthorizationError,
    NotFoundError,
    PlatformError,
    ValidationError,
)
from uuid import UUID


class PoliciesError(PlatformError):
    status_code = 400


class PolicyNotFoundError(NotFoundError):
    def __init__(self, policy_id: UUID | str) -> None:
        super().__init__("POLICY_NOT_FOUND", f"Policy '{policy_id}' was not found.")


class PolicyViolationError(AuthorizationError):
    def __init__(self, message: str, *, code: str = "POLICY_VIOLATION") -> None:
        super().__init__(code, message)


class PolicyCompilationError(ValidationError):
    def __init__(self, message: str) -> None:
        super().__init__("POLICY_COMPILATION_ERROR", message)


class PolicyAttachmentError(ValidationError):
    def __init__(self, message: str, *, code: str = "POLICY_ATTACHMENT_INVALID") -> None:
        super().__init__(code, message)
